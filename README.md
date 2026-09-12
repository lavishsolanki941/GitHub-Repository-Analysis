# GitHub Repository Analyzer

A Streamlit app that takes a public GitHub repository URL and produces an
overview, a deterministic health score, and optional AI-generated insights —
all from GitHub's public REST API, with no cloning or source-code access.

## The problem it solves

Judging the health of an unfamiliar repository usually means manually
checking half a dozen things: is it still maintained, does it have tests,
how many people actually work on it, are issues getting closed. This app
automates that check into a single dashboard, and backs it with a
transparent, explainable score rather than a black-box AI opinion — so you
can see exactly why a repo scored the way it did.

## Features

- **Repository overview** — name, description, stars, forks, watchers, open
  issues, owner, license, default branch, creation/update dates.
- **Health score** — a deterministic 0–100 score (letter grade A–F) built
  from 7 weighted categories, each with a plain-language explanation.
- **Languages** — a percentage breakdown of code by language.
- **Activity** — weekly commit trend for the last year, top contributors,
  and issue/PR close rates.
- **Repository structure** — file/directory counts, extension breakdown,
  largest files, and max directory depth.
- **AI-generated strengths & weaknesses** *(optional, requires a Gemini API
  key)* — 3 strengths, 3 weaknesses, 3 recommendations, and a short overall
  assessment, generated from the structured analysis above.
- **Ask about this repository** *(optional, same key)* — free-form Q&A
  answered from the same structured analysis.
- **Graceful degradation** — the app works fully without a GitHub token or
  Gemini key, and every failure (bad URL, missing repo, rate limits, empty
  repos, network errors) shows a plain-language message instead of a stack
  trace.

## Architecture

This is a single-process Streamlit app — there's no separate frontend or
backend. Streamlit reruns `app.py` top to bottom on every user interaction
(clicking Analyze, switching tabs, submitting a question); each rerun calls
into plain Python functions that fetch data, transform it, and render UI
widgets in the same call. State that needs to survive a rerun (the fetched
repo, AI answers) lives in `st.session_state`; data that's expensive to
re-fetch (GitHub API responses) is memoized with `st.cache_data`.

The code is split by responsibility rather than by frontend/backend:

```
app.py                      Streamlit UI + orchestration (the only file that imports streamlit for logic)
github/
  client.py                 GitHub REST API calls, error translation, caching
  parser.py                 Parses a URL or "owner/repo" into a RepoRef
analyzer/
  health_score.py           Deterministic 0-100 score
  activity.py                Commit trend, contributor, and issue/PR summaries
  code_analysis.py          File tree, language, test, and dependency analysis
ai/
  insights.py                Optional Gemini insights + Q&A
```

`github/client.py` has no Streamlit dependency (so it's independently
testable); `analyzer/*` is pure functions over plain dicts/lists; `ai/insights.py`
only ever receives the already-computed structured analysis, never raw
source code.

## Tech stack

- **Python 3.11+**
- **Streamlit** — UI framework and app server
- **requests** — GitHub REST API calls
- **pandas** — shaping data for charts and tables
- **Plotly** — interactive charts
- **google-generativeai** — Gemini API client for optional AI features
- **python-dotenv** — loads `GITHUB_TOKEN` / `GEMINI_API_KEY` from `.env`

## How the GitHub API is used

All calls go to `https://api.github.com` and are cached client-side for 5
minutes via `st.cache_data` to avoid re-hitting the API on every Streamlit
rerun. Endpoints used:

| Endpoint | Purpose |
|---|---|
| `GET /repos/{owner}/{repo}` | Core repo metadata (stars, forks, license, dates, default branch) |
| `GET /repos/{owner}/{repo}/languages` | Bytes of code per language |
| `GET /repos/{owner}/{repo}/contributors` | Top contributors by commit count (`per_page` capped at 10) |
| `GET /repos/{owner}/{repo}/stats/commit_activity` | Weekly commit counts for the last 52 weeks |
| `GET /search/issues` | Open/closed issue and PR counts, via `total_count` (4 targeted queries, no full pagination needed) |
| `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1` | Full file tree, for structure/test/doc detection |
| `GET /repos/{owner}/{repo}/contents/{path}` | Raw content of dependency manifests (e.g. `requirements.txt`, `package.json`), to detect test tooling |

Without a token, GitHub allows 60 requests/hour per IP; with a personal
access token (no scopes needed for public repos), that rises to 5,000/hour.

## How the health score works

The health score is **100% deterministic Python arithmetic — no AI is
involved in computing it**. It sums 7 weighted categories to a 0–100 score,
then maps that to a letter grade (A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, else F):

| Category | Weight | What it measures |
|---|---|---|
| Maintenance & recency | 25 | Days since last update, nudged by recent commit trend |
| Issue & PR responsiveness | 15 | Average close rate across issues and PRs |
| Testing | 15 | Presence of a test directory, test file count, known test tooling in dependency manifests |
| Contributor diversity | 15 | Bus-factor risk — how concentrated commits are in the top contributor |
| Popularity | 15 | Star count, tiered |
| Documentation & CI | 10 | README, CONTRIBUTING guide, CI workflow presence |
| License | 5 | Whether a license is detected |

Every category returns both a numeric sub-score and a human-readable
explanation (e.g. "Highly concentrated - top contributor holds 82% of
commits"), shown alongside the score breakdown chart.

## AI functionality

Two optional features call **Google Gemini** (`gemini-flash-latest`):

- **Strengths & Weaknesses** — sends the already-computed structured
  analysis (repo overview, health score breakdown, language %, activity
  stats, file structure, test/doc signals) as JSON and asks for exactly 3
  strengths, 3 weaknesses, 3 recommendations, and a short assessment, in a
  strict JSON schema. If the model's response doesn't parse as valid JSON,
  the app falls back to showing the raw text rather than crashing.
- **Ask about this repository** — same structured data, plus a free-form
  question, answered in 2–5 plain-text sentences.

**Source code is never sent to the model** — only the structured metrics
the app has already computed. Both features require a Gemini API key
(sidebar field, or `GEMINI_API_KEY` env var); without one, the app shows
"AI insights unavailable. Add an API key to enable this feature." and every
other tab keeps working normally.

## Installation

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

pip install -r requirements.txt
```

## Environment variables

Copy `.env.example` to `.env` and fill in what you want — both are optional:

| Variable | Required? | Effect without it |
|---|---|---|
| `GITHUB_TOKEN` | No | App works, but limited to 60 GitHub API requests/hour instead of 5,000 |
| `GEMINI_API_KEY` | No | Strengths & Weaknesses and Ask tabs show an "unavailable" message; everything else works |

Either can also be entered directly in the sidebar at runtime, which takes
priority over the `.env` value.

## Running locally

```bash
.venv\Scripts\python.exe -m streamlit run app.py    # Windows
# .venv/bin/streamlit run app.py                    # macOS/Linux
```

Then open the URL Streamlit prints (default `http://localhost:8501`).

## Example usage

1. Paste a repository URL into the sidebar, e.g. `https://github.com/pallets/flask`
   (a full URL or `owner/repo` shorthand both work).
2. Optionally add a GitHub token and/or Gemini API key in the sidebar.
3. Click **Analyze**.
4. Browse the tabs: Overview → Health Score → Languages → Activity →
   Repository Structure → Strengths & Weaknesses → Ask about this repository.

## Future improvements

- Migrate from the deprecated `google-generativeai` SDK to `google.genai`.
- Cache AI insights across sessions (currently cached only per-session in
  `st.session_state`).
- Add a lightweight test suite for the pure-function `analyzer/` and
  `github/parser.py` modules (both have no Streamlit dependency, so they're
  straightforward to unit test).
- Support GitHub Enterprise / custom API base URLs.
- Compare two repositories side by side.
