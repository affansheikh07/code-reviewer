"""Orchestrate the review pipeline: get_diff -> review -> post_comments.

Reads configuration from the environment variables that GitHub Actions
provides so it can run unattended inside a workflow.
"""

from __future__ import annotations

import json
import os
import sys

import requests

from .get_diff import get_pr_files
from .post_comments import post_failure_comment, post_review
from .review import ReviewError, review_diff


def _read_pr_context() -> tuple[str, str, int]:
    """Return (owner, repo, pr_number) from GitHub Actions env vars."""
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" not in repository:
        raise RuntimeError("GITHUB_REPOSITORY is not set (expected 'owner/repo').")
    owner, repo = repository.split("/", 1)

    # Prefer the number GitHub writes into the event payload.
    pr_number: int | None = None
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and os.path.exists(event_path):
        with open(event_path, "r", encoding="utf-8") as fh:
            event = json.load(fh)
        if isinstance(event.get("pull_request"), dict):
            pr_number = event["pull_request"].get("number")
        pr_number = pr_number or event.get("number")

    # Fallback for manual/local runs.
    if pr_number is None:
        env_pr = os.environ.get("PR_NUMBER")
        if env_pr and env_pr.isdigit():
            pr_number = int(env_pr)

    if pr_number is None:
        raise RuntimeError("Could not determine the pull request number.")

    return owner, repo, int(pr_number)


def main() -> int:
    github_token = os.environ.get("GITHUB_TOKEN", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")

    if not github_token:
        print("::error::GITHUB_TOKEN is not set.", file=sys.stderr)
        return 1
    if not gemini_key:
        print("::error::GEMINI_API_KEY is not set.", file=sys.stderr)
        return 1

    try:
        owner, repo, pr_number = _read_pr_context()
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1

    print(f"Reviewing {owner}/{repo}#{pr_number}")
    session = requests.Session()

    try:
        files = get_pr_files(owner, repo, pr_number, github_token, session)
    except requests.RequestException as exc:
        print(f"::error::Failed to fetch PR diff: {exc}", file=sys.stderr)
        # Can't fetch the diff, so we also can't reliably comment — fail soft.
        return 0

    if not files:
        print("No changed files found; nothing to review.")
        return 0

    try:
        review = review_diff(files, gemini_key, session=session)
    except ReviewError as exc:
        print(f"::warning::Gemini review failed: {exc}", file=sys.stderr)
        post_failure_comment(
            owner, repo, pr_number, github_token, str(exc), session
        )
        # Don't fail the workflow just because the model was unavailable.
        return 0

    try:
        post_review(owner, repo, pr_number, github_token, review, session)
    except requests.RequestException as exc:
        print(f"::warning::Failed to post review comments: {exc}", file=sys.stderr)
        return 0

    print(
        f"Review posted: score={review.score or 'n/a'}, "
        f"issues={len(review.issues)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
