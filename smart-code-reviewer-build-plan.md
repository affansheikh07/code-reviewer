# Smart Code Reviewer — Build Plan

**Goal:** A GitHub Action that automatically reviews pull requests for readability,
structure, and maintainability, and posts feedback as PR comments — before a
human reviewer looks at the code.

**Stack (100% free):**
- GitHub Actions — free for public repos (2,000 min/month free for private repos too)
- Google Gemini API (free tier via Google AI Studio) — no credit card required
- GitHub REST API — to post PR comments (uses the built-in `GITHUB_TOKEN`, no extra setup)

> Note: GitHub's own "GitHub Models" free API is being retired July 30, 2026, so it's
> intentionally not used here. Gemini's free tier is currently the most generous
> no-cost option and works well for this.

---

## Phase 1 — Setup

1. Create a new GitHub repo (or use an existing one) for the project.
2. Go to https://aistudio.google.com/apikey and generate a free Gemini API key.
3. In your repo: **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `GEMINI_API_KEY`
   - Value: (paste the key)

---

## Phase 2 — Project structure

```
smart-code-reviewer/
├── .github/
│   └── workflows/
│       └── code-review.yml       # triggers the review on PRs
├── reviewer/
│   ├── get_diff.py               # fetches PR diff from GitHub
│   ├── review.py                 # sends diff to Gemini, gets structured feedback
│   ├── post_comments.py          # posts feedback back to the PR
│   └── prompts.py                # the review rubric/prompt
├── requirements.txt
└── README.md
```

---

## Phase 3 — Prompt the reviewer needs (give this exact rubric to Cursor)

The core of the tool is the prompt sent to Gemini. It should ask for **structured
JSON output** (not free text) so it can be parsed and turned into PR comments.

Review categories:
1. **Readability** — naming, comments, complexity, formatting
2. **Structure** — function/file size, separation of concerns, duplication
3. **Maintainability** — hardcoded values, error handling, test coverage gaps, coupling

Output format (ask Gemini to return only this JSON, nothing else):
```json
{
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
}
```

---

## Phase 4 — Steps to give Cursor (in order)

Send these to Cursor one at a time, or as one big spec — either works, but doing
it step by step gives you a chance to test each piece.

**Step 1:** "Create a Python script `reviewer/get_diff.py` that takes a GitHub
repo, PR number, and GitHub token, and fetches the PR's diff using the GitHub
REST API (`GET /repos/{owner}/{repo}/pulls/{pull_number}/files`). Return a list
of changed files with their patch/diff text."

**Step 2:** "Create `reviewer/prompts.py` with a function `build_review_prompt(diff_text)`
that returns a prompt instructing Gemini to review the diff for readability,
structure, and maintainability, and to respond ONLY in this JSON format: [paste
the JSON schema from Phase 3]."

**Step 3:** "Create `reviewer/review.py` that takes the diff, calls the Gemini
API (`gemini-2.0-flash` or similar free-tier model) using the prompt from
`prompts.py`, and parses the JSON response. Handle cases where Gemini wraps the
JSON in markdown code fences. Skip files that are too large for one request by
chunking per file."

**Step 4:** "Create `reviewer/post_comments.py` that takes the parsed review
JSON and posts it to the PR: one summary comment with the overall_summary and
score, plus individual inline review comments on the relevant file/line using
`POST /repos/{owner}/{repo}/pulls/{pull_number}/comments`."

**Step 5:** "Create `.github/workflows/code-review.yml` that triggers on
`pull_request` (opened, synchronize), checks out the repo, sets up Python,
installs `requirements.txt`, and runs a main script that chains get_diff →
review → post_comments, passing in `GEMINI_API_KEY` and `GITHUB_TOKEN` as env
vars."

**Step 6:** "Create a `reviewer/main.py` that orchestrates the whole pipeline
and reads PR number/repo from GitHub Actions' environment variables
(`GITHUB_REPOSITORY`, `GITHUB_EVENT_PATH` for PR number)."

**Step 7:** "Add error handling: if the Gemini API fails or rate-limits, post a
single fallback comment saying the automated review couldn't complete, instead
of failing the whole workflow silently."

**Step 8:** "Write a README explaining setup: adding the GEMINI_API_KEY secret,
what the bot does, and how to customize the review rubric in prompts.py."

---

## Phase 5 — Testing

1. Open a test PR in the repo with a few obvious code smells (long function,
   bad naming, no error handling).
2. Confirm the Action runs (**Actions** tab in GitHub).
3. Confirm comments appear on the PR.
4. Iterate on the prompt in `prompts.py` if feedback is too vague or too noisy.

---

## Phase 6 — Nice-to-haves (once the basic version works)

- Only review changed lines, not the whole file, to reduce noise on large PRs.
- Add a severity threshold (e.g. skip "low" severity comments) via a config file.
- Cache/skip re-reviewing files that haven't changed since the last run.
- Add a repo-level config file (`.reviewer.yml`) so teams can turn categories on/off.

---

## Free-tier limits to keep in mind

Gemini's free tier has rate limits (requests per minute/day) and Google may use
free-tier prompts to improve their models — don't send proprietary/sensitive
code through it if that's a concern. If you outgrow the free tier, the same
code works with a paid Gemini key or can be swapped to another provider by
changing only `review.py`.
