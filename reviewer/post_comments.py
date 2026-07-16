"""Post the parsed review back to the pull request as GitHub comments."""

from __future__ import annotations

import requests

from .get_diff import GITHUB_API, _headers
from .review import Review

# Marker so we can identify (and later update) our own summary comment.
SUMMARY_MARKER = "<!-- smart-code-reviewer:summary -->"

SEVERITY_EMOJI = {"high": "🔴", "medium": "🟠", "low": "🟡"}


def _get_head_sha(
    owner: str, repo: str, pull_number: int, token: str, session: requests.Session
) -> str:
    """Return the SHA of the PR head commit (needed for inline comments)."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}"
    resp = session.get(url, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()["head"]["sha"]


def _build_summary_body(review: Review, posted: int, skipped: list[dict]) -> str:
    score_line = f"**Score:** {review.score}/10\n\n" if review.score else ""
    lines = [
        SUMMARY_MARKER,
        "## Automated Code Review",
        "",
        score_line + (review.overall_summary or "No summary provided."),
        "",
        f"Found **{len(review.issues)}** issue(s); posted {posted} inline comment(s).",
    ]

    if skipped:
        lines.append("")
        lines.append("<details><summary>Issues not attached to a line</summary>")
        lines.append("")
        for issue in skipped:
            lines.append(_format_issue_line(issue))
        lines.append("")
        lines.append("</details>")

    return "\n".join(lines)


def _format_issue_line(issue: dict) -> str:
    emoji = SEVERITY_EMOJI.get(str(issue.get("severity", "")).lower(), "⚪")
    category = issue.get("category", "general")
    file = issue.get("file", "?")
    line = issue.get("line")
    loc = f"`{file}`" + (f":{line}" if line else "")
    comment = issue.get("comment", "")
    suggestion = issue.get("suggestion", "")
    text = f"- {emoji} **{category}** — {loc}\n  {comment}"
    if suggestion:
        text += f"\n  _Suggestion:_ {suggestion}"
    return text


def _build_inline_body(issue: dict) -> str:
    emoji = SEVERITY_EMOJI.get(str(issue.get("severity", "")).lower(), "⚪")
    category = issue.get("category", "general")
    severity = issue.get("severity", "")
    header = f"{emoji} **{category}** ({severity})"
    body = f"{header}\n\n{issue.get('comment', '')}"
    suggestion = issue.get("suggestion", "")
    if suggestion:
        body += f"\n\n**Suggestion:** {suggestion}"
    return body


def _post_summary(
    owner: str,
    repo: str,
    pull_number: int,
    token: str,
    body: str,
    session: requests.Session,
) -> None:
    # Issue-comments endpoint works for PRs too and posts a top-level comment.
    url = f"{GITHUB_API}/repos/{owner}/{repo}/issues/{pull_number}/comments"
    resp = session.post(url, headers=_headers(token), json={"body": body}, timeout=30)
    resp.raise_for_status()


def _post_inline(
    owner: str,
    repo: str,
    pull_number: int,
    token: str,
    commit_id: str,
    issue: dict,
    session: requests.Session,
) -> bool:
    """Attempt to post one inline comment. Return True on success."""
    line = issue.get("line")
    path = issue.get("file")
    if not path or not line:
        return False

    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
    payload = {
        "body": _build_inline_body(issue),
        "commit_id": commit_id,
        "path": path,
        "line": int(line),
        "side": "RIGHT",
    }
    resp = session.post(url, headers=_headers(token), json=payload, timeout=30)
    # 422 == line not part of the diff; caller will fold it into the summary.
    return resp.status_code == 201


def post_review(
    owner: str,
    repo: str,
    pull_number: int,
    token: str,
    review: Review,
    session: requests.Session | None = None,
) -> None:
    """Post the full review: inline comments where possible, plus a summary."""
    session = session or requests.Session()

    try:
        head_sha = _get_head_sha(owner, repo, pull_number, token, session)
    except requests.RequestException:
        head_sha = ""

    posted = 0
    skipped: list[dict] = []
    for issue in review.issues:
        success = False
        if head_sha:
            try:
                success = _post_inline(
                    owner, repo, pull_number, token, head_sha, issue, session
                )
            except requests.RequestException:
                success = False
        if success:
            posted += 1
        else:
            skipped.append(issue)

    body = _build_summary_body(review, posted, skipped)
    _post_summary(owner, repo, pull_number, token, body, session)


def post_failure_comment(
    owner: str,
    repo: str,
    pull_number: int,
    token: str,
    message: str,
    session: requests.Session | None = None,
) -> None:
    """Post a single fallback comment when the review pipeline fails."""
    session = session or requests.Session()
    body = (
        f"{SUMMARY_MARKER}\n## Automated Code Review\n\n"
        f"The automated review could not complete: {message}\n\n"
        "_A human reviewer should proceed as usual._"
    )
    try:
        _post_summary(owner, repo, pull_number, token, body, session)
    except requests.RequestException:
        # Never let the fallback itself break the workflow.
        pass
