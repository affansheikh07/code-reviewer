"""Fetch the diff of a pull request from the GitHub REST API."""

from __future__ import annotations

from dataclasses import dataclass

import requests

GITHUB_API = "https://api.github.com"
# GitHub paginates the files endpoint; 100 is the maximum page size.
PER_PAGE = 100


@dataclass
class ChangedFile:
    """A single file changed in a pull request."""

    filename: str
    status: str  # added | modified | removed | renamed
    additions: int
    deletions: int
    changes: int
    patch: str  # the unified diff hunk(s); empty for binary/too-large files


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_pr_files(
    owner: str,
    repo: str,
    pull_number: int,
    token: str,
    session: requests.Session | None = None,
) -> list[ChangedFile]:
    """Fetch the list of files changed in a PR, with their diff patches.

    Uses ``GET /repos/{owner}/{repo}/pulls/{pull_number}/files`` and follows
    pagination so large PRs are fully covered.
    """
    session = session or requests.Session()
    files: list[ChangedFile] = []
    page = 1

    while True:
        url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pull_number}/files"
        resp = session.get(
            url,
            headers=_headers(token),
            params={"per_page": PER_PAGE, "page": page},
            timeout=30,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break

        for item in batch:
            files.append(
                ChangedFile(
                    filename=item.get("filename", ""),
                    status=item.get("status", ""),
                    additions=item.get("additions", 0),
                    deletions=item.get("deletions", 0),
                    changes=item.get("changes", 0),
                    # Binary files and very large diffs have no "patch" field.
                    patch=item.get("patch", "") or "",
                )
            )

        if len(batch) < PER_PAGE:
            break
        page += 1

    return files


def build_diff_text(files: list[ChangedFile]) -> str:
    """Combine changed files into a single readable diff blob for the prompt."""
    parts: list[str] = []
    for f in files:
        if not f.patch:
            continue
        parts.append(f"### File: {f.filename} ({f.status})\n{f.patch}")
    return "\n\n".join(parts)
