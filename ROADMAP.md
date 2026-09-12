# Development Roadmap — GitHub Repository Analyzer

This file documents the phased build plan for the project. It exists so any
contributor (or AI assistant) can see the intended scope of each phase and
not guess wrong. Status reflects the current state of the repo.

## Tech Stack
- Python 3.11+
- Streamlit (frontend + backend in one process)
- GitHub REST API (via `requests`)
- Pandas (data processing)
- Plotly (charts)
- An LLM API (optional AI insights)
- python-dotenv (environment variables)

No React, Node.js, or separate frontend/backend. Streamlit runs the whole app.

## Project Structure
```
github-analyzer/
├── app.py                      # Streamlit UI + orchestration
├── requirements.txt
├── README.md
├── ROADMAP.md
├── .gitignore
├── .env.example
├── github/
│   ├── __init__.py
│   ├── client.py               # GitHub REST API calls (cached)
│   └── parser.py               # parse owner/repo from a URL
├── analyzer/
│   ├── __init__.py
│   ├── health_score.py         # deterministic 0–100 score
│   ├── activity.py             # commit trend, contributors, issue/PR stats
│   └── code_analysis.py        # file/lang/test/project-file analysis
├── ai/
│   ├── __init__.py
│   └── insights.py             # optional LLM insights + Q&A
└── utils/
    └── __init__.py, helpers.py
```

## Phases

### Phase 1 — Project setup ✅ Done
- Folder structure, `requirements.txt`, `.gitignore`, `.env.example`
- Basic bootable Streamlit app with stubbed sidebar

### Phase 2 — Repository overview ✅ Done
- Parse `owner`/`repo` from a GitHub URL (`github/parser.py`)
- GitHub API client (`github/client.py`)
- Fetch and display repo overview: name, owner, description, stars, forks,
  watchers, open issues, created/updated dates, default branch, license, URL

### Phase 3 — Analysis layer ✅ Done
- **Activity** (`analyzer/activity.py`): commit trend (weekly counts + direction),
  top contributors, issue/PR close-rate
- **Code structure** (`analyzer/code_analysis.py`): file/dir counts, extension
  breakdown, largest files, language percentages (small languages folded into "Other")
- New client methods: `get_languages`, `get_contributors`, `get_commit_activity`,
  `get_issue_counts`, `get_tree`, each with a cached `fetch_*` wrapper
- Activity and Code Structure tabs with Plotly charts

### Phase 4 — Repository Health Score ✅ Done
- Deterministic 0–100 score (no AI in the number), with letter grade (A–F)
- 7 weighted categories summing to 100:
  - Maintenance & recency — 25
  - Issue & PR responsiveness — 15
  - Testing — 15
  - Contributor diversity (bus-factor) — 15
  - Popularity — 15
  - Documentation & CI — 10
  - License — 5
- Each category returns a sub-score **and** a human-readable explanation
- `detect_project_files()` (README/CONTRIBUTING/CI) and `detect_test_signals()`
  (test files, test dirs, test tooling in dependency manifests)
- Health Score tab: overall score/grade (color-coded) + per-category bar chart
- Verified it discriminates: flask Testing 15/15, awesome Testing 0/15

### Phase 5 — Complete dashboard + visualizations 🔨 In progress
- Consolidate and polish the full main-page layout (audit, don't rebuild):
  1. Repository overview
  2. Health score (overall + grade)
  3. Score breakdown (per-category + explanations)
  4. Languages
  5. Activity
  6. Repository structure
  7. Strengths and weaknesses (stub — AI fills in Phase 6)
- Tighten Plotly charts: clear titles, axis labels, consistent palette,
  readable in light and dark
- No new features beyond the plan

### Phase 6 — Optional AI insights ✅ Done
- Send **structured analysis only** (never source code) to Google Gemini
  (`gemini-flash-latest`, via `google-generativeai`)
- Generate: 3 strengths, 3 weaknesses, 3 recommendations, short overall assessment
- Strict JSON response schema, parsed with a plain-text fallback if parsing fails
- App works without an API key; shows: "AI insights unavailable. Add an API key
  to enable this feature."
- Key read from the sidebar field or `GEMINI_API_KEY` env var (sidebar wins)
- AI result cached per repo in session state so it doesn't re-call on every re-run

### Phase 7 — Ask about this repository ⏳ Planned
- Optional Q&A using the collected analysis as context
- Handles missing API key gracefully

### Phase 8 — Error handling, testing, README ✅ Done
- Handle: invalid URLs, repo not found, private repos, rate limits (primary +
  secondary/abuse), missing keys, network errors (timeout vs. connection
  failure), empty repos, low-activity repos, pagination
- Fixed a real crash: `stats/commit_activity`'s async 202-with-empty-body
  response was calling `.json()` unguarded, raising an uncaught
  `JSONDecodeError` instead of a friendly message
- Added `EmptyRepositoryError` for the 409 GitHub returns on `git/trees` for
  a repo with no commits, shown as `st.info` rather than `st.error`
- Rate limit messages now show remaining/limit and a reset time
- Friendly Streamlit error messages throughout (no raw stack traces)
- Tested against pallets/flask (large/active), sindresorhus/awesome
  (docs-only), octocat/Spoon-Knife (small/inactive), and an invalid URL
- Finalized a professional README

## Design Rules
- GitHub API logic, analysis logic, and AI logic stay in separate modules
- The health score is **deterministic Python** — fully explainable, no AI
- API keys come from environment variables; `.env` is never committed
- Use `st.cache_data` to avoid re-hitting the API on Streamlit re-runs
- No unnecessary dependencies

## Known API Quirks Handled
- `stats/commit_activity` returns an empty `202` while GitHub computes stats
  asynchronously — the client retries a few times, then shows "no data yet"
- `get_file_content` returns `None` on 404 instead of raising, so a missing
  `requirements.txt` (etc.) doesn't crash the analysis
