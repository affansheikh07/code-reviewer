# Smart Code Reviewer

A GitHub Action that automatically reviews pull requests for **readability**,
**structure**, and **maintainability**, then posts feedback as PR comments —
before a human reviewer looks at the code.

It uses Google's **Gemini** free tier for the analysis and the built-in
`GITHUB_TOKEN` to post comments, so it costs nothing to run on public repos
(and stays within the free Actions minutes on private repos).

---

## How it works

On every pull request (opened / updated / reopened) the Action:

1. **Fetches the diff** of the PR via the GitHub REST API (`get_diff.py`).
2. **Sends the diff to Gemini** with a structured review rubric and parses the
   JSON response (`review.py` + `prompts.py`). Large PRs are chunked per file.
3. **Posts the feedback** back to the PR (`post_comments.py`):
   - one **summary comment** with an overall score and summary, and
   - **inline comments** on the relevant file/line for each issue.

If Gemini is unavailable or rate-limited, a single fallback comment is posted
and the workflow still succeeds (it won't block your PR).

---

## Setup

### 1. Get a free Gemini API key

Go to <https://aistudio.google.com/apikey> and create a key. No credit card
required.

### 2. Add the key as a repository secret

In your repo: **Settings → Secrets and variables → Actions → New repository
secret**

- **Name:** `GEMINI_API_KEY`
- **Value:** *(paste your key)*

That's it — `GITHUB_TOKEN` is provided automatically by GitHub Actions.

### 3. Add the files to your repo

Copy this project's `reviewer/`, `requirements.txt`, and
`.github/workflows/code-review.yml` into your repository. Open a pull request
and the review runs automatically. Check the **Actions** tab to watch it run.

---

## Project structure

```
smart-code-reviewer/
├── .github/
│   └── workflows/
│       └── code-review.yml   # triggers the review on PRs
├── reviewer/
│   ├── get_diff.py           # fetches PR diff from GitHub
│   ├── prompts.py            # the review rubric / prompt
│   ├── review.py             # sends diff to Gemini, parses feedback
│   ├── post_comments.py      # posts feedback back to the PR
│   └── main.py               # orchestrates the pipeline
├── requirements.txt
└── README.md
```

---

## Customizing the review

### Change the rubric

Edit `RUBRIC` in [`reviewer/prompts.py`](reviewer/prompts.py) to change what the
reviewer focuses on or how strict it is. If you change the output shape, keep
`JSON_SCHEMA` in sync with what `review.py` and `post_comments.py` expect.

### Change the model

Set the `REVIEW_MODEL` environment variable in the workflow (defaults to
`gemini-2.5-flash`). For example, `gemini-2.5-flash-lite` for faster/cheaper
runs.

> **Important:** the model must be one that still has free-tier quota. Older
> models like `gemini-2.0-flash` were deprecated in 2026 and their free-tier
> quota is `0`, so they return `429` on every request. If you see a "no
> free-tier quota (limit: 0)" error, switch to a current Flash model. You can
> check which models your key can use, and their live limits, in
> **Google AI Studio → Dashboard**.

### Tune chunking

`MAX_CHARS_PER_REQUEST` in `review.py` controls how much diff text goes into a
single Gemini request. Lower it if you hit token limits on very large PRs.

---

## Running locally

You can run the pipeline outside Actions for testing:

```bash
pip install -r requirements.txt

export GITHUB_TOKEN=ghp_your_token
export GEMINI_API_KEY=your_gemini_key
export GITHUB_REPOSITORY=owner/repo
export PR_NUMBER=123

python -m reviewer.main
```

---

## Notes on the free tier

Gemini's free tier has rate limits (requests per minute/day), and Google may use
free-tier prompts to improve their models — **don't send proprietary or
sensitive code through it** if that's a concern. If you outgrow the free tier,
the same code works with a paid Gemini key, or you can swap providers by editing
only `review.py`.
