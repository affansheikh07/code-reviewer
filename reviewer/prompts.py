"""The review rubric / prompt sent to the model.

Customize the rubric below to tune what the reviewer focuses on. The output
schema must stay in sync with what ``review.py`` and ``post_comments.py``
expect.
"""

from __future__ import annotations

# The JSON schema the model MUST return. Kept as a string so it can be embedded
# verbatim in the prompt.
JSON_SCHEMA = """{
  "overall_summary": "string",
  "score": "1-10",
  "issues": [
    {
      "file": "path/to/file.py",
      "line": 42,
      "category": "readability | structure | maintainability",
      "severity": "low | medium | high",
      "comment": "string explaining the issue",
      "suggestion": "string with a concrete fix"
    }
  ]
}"""

RUBRIC = """You are a senior software engineer performing a pre-review of a pull request.
Review ONLY the changed code shown in the diff. Focus on three categories:

1. Readability — naming, comments, complexity, formatting.
2. Structure — function/file size, separation of concerns, duplication.
3. Maintainability — hardcoded values, error handling, test coverage gaps, coupling.

Guidelines:
- Be concrete and actionable. Every issue must include a specific suggested fix.
- Only flag things that genuinely matter; do not invent problems or nitpick style
  that a linter/formatter would already catch.
- Use the file path exactly as it appears in the diff header (### File: <path>).
- The "line" field must be a line number that appears in the diff for that file
  (prefer the new-file line number of an added/changed line). If you cannot map an
  issue to a specific line, use null.
- "score" is an overall quality score from 1 (poor) to 10 (excellent) for this PR.
- If the diff has no meaningful issues, return an empty "issues" array and say so
  in "overall_summary"."""


def build_review_prompt(diff_text: str) -> str:
    """Build the full prompt instructing the model to review ``diff_text``.

    The model is told to respond ONLY with JSON matching ``JSON_SCHEMA``.
    """
    return f"""{RUBRIC}

Respond with ONLY a single JSON object, no prose, no markdown code fences,
matching exactly this schema:

{JSON_SCHEMA}

Here is the pull request diff to review:

{diff_text}
"""
