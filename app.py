"""GitHub Repository Analyzer - Streamlit entry point."""

import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from analyzer.activity import summarize_commit_activity, summarize_contributors, summarize_issues
from analyzer.code_analysis import analyze_file_structure, detect_project_files, summarize_languages
from analyzer.health_score import compute_health_score
from github.client import (
    GitHubAPIError,
    fetch_commit_activity,
    fetch_contributors,
    fetch_issue_counts,
    fetch_languages,
    fetch_repo,
    fetch_tree,
)
from github.parser import InvalidRepoURLError, parse_repo_url

load_dotenv()

st.set_page_config(
    page_title="GitHub Repository Analyzer",
    page_icon=":mag:",
    layout="wide",
)

# Sequential (magnitude) and categorical (identity) colors from the project's
# validated data-viz palette - dark-surface steps, since the app runs dark.
SEQUENTIAL_BLUE = "#3987e5"
CATEGORICAL_COLORS = [
    "#3987e5",  # blue
    "#d95926",  # orange
    "#199e70",  # aqua
    "#c98500",  # yellow
    "#d55181",  # magenta
    "#008300",  # green
    "#898781",  # muted gray, reserved for "Other"
]

with st.sidebar:
    st.header("GitHub Repository Analyzer")
    repo_url = st.text_input("Repository URL", placeholder="https://github.com/owner/repo")
    github_token = st.text_input(
        "GitHub token (optional)", type="password", value=os.getenv("GITHUB_TOKEN", "")
    )
    st.caption(
        "Token detected — 5,000 requests/hour." if github_token
        else "No token — limited to 60 requests/hour."
    )
    ai_key = st.text_input(
        "AI API key (optional)", type="password", value=os.getenv("ANTHROPIC_API_KEY", "")
    )
    st.caption("AI key detected — AI features enabled." if ai_key else "No AI key — AI features disabled.")
    analyze_clicked = st.button("Analyze", type="primary")

st.title("GitHub Repository Analyzer")
st.write(
    "Enter a public GitHub repository URL in the sidebar and click **Analyze** "
    "to get an overview, health score, and optional AI insights."
)


def render_overview(repo: dict) -> None:
    """Render the repo overview section: metrics, description, and key facts."""
    st.subheader(repo["full_name"])
    if repo.get("description"):
        st.caption(repo["description"])

    metric_cols = st.columns(4)
    metric_cols[0].metric("Stars", f"{repo['stargazers_count']:,}")
    metric_cols[1].metric("Forks", f"{repo['forks_count']:,}")
    metric_cols[2].metric("Watchers", f"{repo['watchers_count']:,}")
    metric_cols[3].metric("Open Issues", f"{repo['open_issues_count']:,}")

    info_cols = st.columns(3)
    info_cols[0].write(f"**Owner:** {repo['owner']['login']}")
    info_cols[0].write(f"**Default branch:** {repo['default_branch']}")
    info_cols[1].write(f"**Created:** {repo['created_at'][:10]}")
    info_cols[1].write(f"**Last updated:** {repo['updated_at'][:10]}")
    license_name = (repo.get("license") or {}).get("name", "No license")
    info_cols[2].write(f"**License:** {license_name}")
    info_cols[2].write(f"[View on GitHub]({repo['html_url']})")


def render_activity(ref, token: str | None) -> None:
    """Render the Activity tab: commit trend, top contributors, issue/PR health."""
    try:
        with st.spinner("Fetching commit activity..."):
            weekly = fetch_commit_activity(ref.owner, ref.name, token)
    except GitHubAPIError as exc:
        st.error(str(exc))
        weekly = []
    activity = summarize_commit_activity(weekly)

    if activity["weeks"]:
        trend_labels = {
            "increasing": "Increasing",
            "decreasing": "Decreasing",
            "steady": "Steady",
            "quiet": "No recent commits",
        }
        cols = st.columns(3)
        cols[0].metric("Commits (last year)", f"{activity['total_last_year']:,}")
        cols[1].metric("Commits (last 4 weeks)", activity["total_last_4_weeks"])
        cols[2].metric("Trend", trend_labels.get(activity["trend"], activity["trend"]))

        df = pd.DataFrame({"Week": activity["weeks"], "Commits": activity["counts"]})
        fig = px.bar(df, x="Week", y="Commits", color_discrete_sequence=[SEQUENTIAL_BLUE])
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No commit activity data available for this repository.")

    st.divider()

    try:
        contributors_raw = fetch_contributors(ref.owner, ref.name, token, limit=10)
    except GitHubAPIError as exc:
        st.error(str(exc))
        contributors_raw = []
    contributors = summarize_contributors(contributors_raw)

    st.subheader("Top contributors")
    if contributors:
        df = pd.DataFrame(contributors)[["login", "contributions"]].iloc[::-1]
        fig = px.bar(
            df,
            x="contributions",
            y="login",
            orientation="h",
            color_discrete_sequence=[SEQUENTIAL_BLUE],
            labels={"contributions": "Commits", "login": ""},
        )
        fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No contributor data available.")

    st.divider()

    try:
        counts = fetch_issue_counts(ref.owner, ref.name, token)
    except GitHubAPIError as exc:
        st.error(str(exc))
        counts = {}
    issues = summarize_issues(counts)

    st.subheader("Issues & pull requests")
    cols = st.columns(4)
    cols[0].metric("Open issues", issues["open_issues"])
    cols[1].metric("Closed issues", issues["closed_issues"])
    cols[2].metric("Open PRs", issues["open_prs"])
    cols[3].metric("Closed PRs", issues["closed_prs"])
    if issues["issue_close_rate"] is not None:
        st.caption(f"Issue close rate: {issues['issue_close_rate']:.0%}")


def render_code_structure(repo: dict, ref, token: str | None) -> None:
    """Render the Code Structure tab: language breakdown and file tree stats."""
    try:
        languages_raw = fetch_languages(ref.owner, ref.name, token)
    except GitHubAPIError as exc:
        st.error(str(exc))
        languages_raw = {}
    languages = summarize_languages(languages_raw)

    st.subheader("Language breakdown")
    if languages:
        df = pd.DataFrame(languages)
        fig = px.pie(df, names="language", values="bytes", color_discrete_sequence=CATEGORICAL_COLORS)
        fig.update_traces(textinfo="label+percent")
        fig.update_layout(margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No language data available.")

    st.divider()

    try:
        with st.spinner("Fetching file tree..."):
            tree = fetch_tree(ref.owner, ref.name, repo["default_branch"], token)
    except GitHubAPIError as exc:
        st.error(str(exc))
        tree = {}
    structure = analyze_file_structure(tree)

    st.subheader("File structure")
    cols = st.columns(3)
    cols[0].metric("Files", f"{structure['file_count']:,}")
    cols[1].metric("Directories", f"{structure['dir_count']:,}")
    cols[2].metric("Max depth", structure["max_depth"])
    if structure["truncated"]:
        st.caption("This repository is large — GitHub truncated the file listing.")

    if structure["extensions"]:
        st.write("**File types**")
        ext_df = pd.DataFrame(structure["extensions"], columns=["Extension", "Files"])
        st.dataframe(ext_df, hide_index=True, use_container_width=True)

    if structure["largest_files"]:
        st.write("**Largest files**")
        largest_df = pd.DataFrame(structure["largest_files"])
        largest_df["size"] = largest_df["size"].apply(lambda n: f"{n / 1024:.1f} KB")
        largest_df = largest_df.rename(columns={"path": "Path", "size": "Size"})
        st.dataframe(largest_df, hide_index=True, use_container_width=True)


def render_health_score(repo: dict, ref, token: str | None) -> None:
    """Render the Health Score tab: a deterministic 0-100 score with a breakdown."""
    try:
        with st.spinner("Scoring repository health..."):
            commit_activity = summarize_commit_activity(fetch_commit_activity(ref.owner, ref.name, token))
            contributors = fetch_contributors(ref.owner, ref.name, token, limit=10)
            issue_summary = summarize_issues(fetch_issue_counts(ref.owner, ref.name, token))
            project_files = detect_project_files(
                fetch_tree(ref.owner, ref.name, repo["default_branch"], token)
            )
    except GitHubAPIError as exc:
        st.error(str(exc))
        return

    result = compute_health_score(repo, commit_activity, contributors, issue_summary, project_files)

    status = st.success if result["score"] >= 80 else st.warning if result["score"] >= 60 else st.error
    status(f"Health score: {result['score']}/100 (grade {result['grade']})")

    df = pd.DataFrame(result["breakdown"])
    df["percent"] = df["score"] / df["max"] * 100
    fig = px.bar(
        df.iloc[::-1],
        x="percent",
        y="category",
        orientation="h",
        range_x=[0, 100],
        color_discrete_sequence=[SEQUENTIAL_BLUE],
        labels={"percent": "Score (%)", "category": ""},
    )
    fig.update_layout(showlegend=False, margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    for item in result["breakdown"]:
        st.write(f"**{item['category']}** — {item['score']}/{item['max']}: {item['explanation']}")


if analyze_clicked:
    if not repo_url:
        st.warning("Enter a repository URL first.")
    else:
        try:
            ref = parse_repo_url(repo_url)
        except InvalidRepoURLError as exc:
            st.error(str(exc))
        else:
            try:
                with st.spinner(f"Fetching {ref.full_name}..."):
                    repo_data = fetch_repo(ref.owner, ref.name, github_token or None)
            except GitHubAPIError as exc:
                st.error(str(exc))
            else:
                st.session_state["repo_data"] = repo_data
                st.session_state["repo_ref"] = ref

if "repo_data" in st.session_state:
    repo_data = st.session_state["repo_data"]
    ref = st.session_state["repo_ref"]
    token = github_token or None

    overview_tab, activity_tab, code_tab, health_tab = st.tabs(
        ["Overview", "Activity", "Code Structure", "Health Score"]
    )
    with overview_tab:
        render_overview(repo_data)
    with activity_tab:
        render_activity(ref, token)
    with code_tab:
        render_code_structure(repo_data, ref, token)
    with health_tab:
        render_health_score(repo_data, ref, token)
