"""Send the diff to the Gemini API and parse the structured review back."""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import dataclass, field

import requests

from .get_diff import ChangedFile
from .prompts import build_review_prompt

# Free-tier friendly model. Override with the REVIEW_MODEL env var if desired.
# NOTE: gemini-2.0-flash was deprecated/shut down in 2026 and has a free-tier
# quota of 0, so it always 429s. Use a currently supported Flash model.
DEFAULT_MODEL = "gemini-2.5-flash"
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)

# Rough character budget per request to stay well under model/token limits.
# Files whose diff exceeds this are reviewed in their own request.
MAX_CHARS_PER_REQUEST = 12000


class ReviewError(Exception):
    """Raised when the model cannot be reached or returns unusable output."""


@dataclass
class Review:
    """Parsed review result."""

    overall_summary: str = ""
    score: str = ""
    issues: list[dict] = field(default_factory=list)


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` (or plain ```) wrappers the model may add."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    return text


def _extract_json(text: str) -> dict:
    """Parse a JSON object out of the model's raw text response."""
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Fall back to grabbing the outermost {...} span.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ReviewError(f"Could not parse JSON from model: {exc}") from exc
        raise ReviewError("Model response contained no JSON object")


def _is_hard_quota_zero(body: str) -> bool:
    """True if a 429 body indicates a permanent quota of 0 (deprecated/free=0).

    Retrying such a request is pointless — it will never succeed until the
    model or billing tier changes.
    """
    return "limit: 0" in body or "limit:0" in body


def _retry_delay_from_body(body: str) -> float | None:
    """Extract Gemini's suggested retry delay (e.g. "retryDelay": "17s")."""
    match = re.search(r'"?retryDelay"?\s*:?\s*"?(\d+(?:\.\d+)?)s', body)
    if match:
        return float(match.group(1))
    return None


def _call_gemini(
    prompt: str,
    api_key: str,
    model: str,
    session: requests.Session,
    max_retries: int = 3,
) -> str:
    """Call the Gemini generateContent endpoint and return the raw text reply."""
    url = GEMINI_ENDPOINT.format(model=model)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = session.post(url, headers=headers, json=payload, timeout=60)
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(2 ** attempt + random.uniform(0, 1))
            continue

        # Retry on rate limit / transient server errors with backoff.
        if resp.status_code in (429, 500, 502, 503, 504):
            body = resp.text
            # A hard quota of 0 (e.g. deprecated model) will never recover.
            if resp.status_code == 429 and _is_hard_quota_zero(body):
                raise ReviewError(
                    f"Model '{model}' has no free-tier quota (limit: 0). It may be "
                    "deprecated or require billing. Set REVIEW_MODEL to a supported "
                    f"model such as 'gemini-2.5-flash'. Details: {body[:200]}"
                )
            last_exc = ReviewError(f"Gemini returned {resp.status_code}: {body[:200]}")
            # Honor server-suggested delay when present, else exponential backoff.
            delay = _retry_delay_from_body(body) or (2 ** attempt)
            time.sleep(delay + random.uniform(0, 1))
            continue

        if resp.status_code != 200:
            raise ReviewError(
                f"Gemini request failed ({resp.status_code}): {resp.text[:300]}"
            )

        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ReviewError(f"Unexpected Gemini response shape: {data}") from exc

    raise ReviewError(f"Gemini call failed after {max_retries} retries: {last_exc}")


def _chunk_files(files: list[ChangedFile]) -> list[list[ChangedFile]]:
    """Group changed files into batches under the per-request character budget.

    Files larger than the budget on their own get a batch to themselves.
    """
    chunks: list[list[ChangedFile]] = []
    current: list[ChangedFile] = []
    current_size = 0

    for f in files:
        if not f.patch:
            continue
        size = len(f.patch) + len(f.filename)
        if size > MAX_CHARS_PER_REQUEST:
            if current:
                chunks.append(current)
                current, current_size = [], 0
            chunks.append([f])
            continue
        if current_size + size > MAX_CHARS_PER_REQUEST and current:
            chunks.append(current)
            current, current_size = [], 0
        current.append(f)
        current_size += size

    if current:
        chunks.append(current)
    return chunks


def _diff_text_for(files: list[ChangedFile]) -> str:
    parts = [f"### File: {f.filename} ({f.status})\n{f.patch}" for f in files if f.patch]
    return "\n\n".join(parts)


def review_diff(
    files: list[ChangedFile],
    api_key: str,
    model: str | None = None,
    session: requests.Session | None = None,
) -> Review:
    """Review all changed files, chunking per size, and merge the results."""
    model = model or os.environ.get("REVIEW_MODEL", DEFAULT_MODEL)
    session = session or requests.Session()

    chunks = _chunk_files(files)
    if not chunks:
        return Review(
            overall_summary="No reviewable text changes were found in this PR.",
            score="",
            issues=[],
        )

    summaries: list[str] = []
    scores: list[int] = []
    all_issues: list[dict] = []

    for chunk in chunks:
        prompt = build_review_prompt(_diff_text_for(chunk))
        raw = _call_gemini(prompt, api_key, model, session)
        parsed = _extract_json(raw)

        summary = str(parsed.get("overall_summary", "")).strip()
        if summary:
            summaries.append(summary)

        score_raw = str(parsed.get("score", "")).strip()
        match = re.search(r"\d+", score_raw)
        if match:
            scores.append(int(match.group()))

        issues = parsed.get("issues", [])
        if isinstance(issues, list):
            all_issues.extend(i for i in issues if isinstance(i, dict))

    avg_score = str(round(sum(scores) / len(scores))) if scores else ""
    return Review(
        overall_summary=" ".join(summaries),
        score=avg_score,
        issues=all_issues,
    )
