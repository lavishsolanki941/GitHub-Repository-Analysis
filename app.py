"""GitHub Repository Analyzer - Streamlit entry point."""

import os

import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from analyzer.activity import summarize_commit_activity, summarize_contributors, summarize_issues
from analyzer.code_analysis import (
    analyze_file_structure,
    detect_project_files,
    detect_test_signals,
    detect_test_tooling,
    find_dependency_files,
    summarize_languages,
)
from analyzer.health_score import compute_health_score
from ai.insights import InsightsError, answer_question, generate_insights, get_api_key
from github.client import (
    EmptyRepositoryError,
    GitHubAPIError,
    fetch_commit_activity,
    fetch_contributors,
    fetch_file_content,
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

github_token = os.getenv("GITHUB_TOKEN") or None
ai_key = os.getenv("GEMINI_API_KEY") or None

with st.sidebar:
    st.header("GitHub Repository Analyzer")
    repo_url = st.text_input("Repository URL", placeholder="https://github.com/owner/repo")
    analyze_clicked = st.button("Analyze", type="primary")
    st.caption("AI insights enabled" if ai_key else "AI insights off")

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
        fig = px.bar(
            df,
            x="Week",
            y="Commits",
            color_discrete_sequence=[SEQUENTIAL_BLUE],
            title="Weekly commit activity (last 52 weeks)",
        )
        fig.update_layout(showlegend=False, margin=dict(t=40, b=10))
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")
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
            title="Top contributors by commits",
        )
        fig.update_layout(showlegend=False, margin=dict(t=40, b=10))
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")
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


def render_languages(ref, token: str | None) -> None:
    """Render the Languages tab: a breakdown of code by language."""
    try:
        languages_raw = fetch_languages(ref.owner, ref.name, token)
    except GitHubAPIError as exc:
        st.error(str(exc))
        languages_raw = {}
    languages = summarize_languages(languages_raw)

    if languages:
        df = pd.DataFrame(languages)
        fig = px.pie(
            df,
            names="language",
            values="bytes",
            color_discrete_sequence=CATEGORICAL_COLORS,
            title="Share of code by language",
        )
        fig.update_traces(textinfo="percent", textposition="inside")
        fig.update_layout(margin=dict(t=40, b=10))
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")
    else:
        st.info("No language data available.")


def render_repo_structure(repo: dict, ref, token: str | None) -> None:
    """Render the Repository Structure tab: file tree stats."""
    try:
        with st.spinner("Fetching file tree..."):
            tree = fetch_tree(ref.owner, ref.name, repo["default_branch"], token)
    except EmptyRepositoryError as exc:
        st.info(str(exc))
        return
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

    table_col1, table_col2 = st.columns(2)
    with table_col1:
        if structure["extensions"]:
            st.write("**File types**")
            ext_df = pd.DataFrame(structure["extensions"], columns=["Extension", "Files"])
            st.dataframe(ext_df, hide_index=True, use_container_width=True)
    with table_col2:
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
            tree = fetch_tree(ref.owner, ref.name, repo["default_branch"], token)
            project_files = detect_project_files(tree)
            test_signals = detect_test_signals(tree)
            dependency_contents = {
                path: fetch_file_content(ref.owner, ref.name, path, token)
                for path in find_dependency_files(tree)
            }
            test_tooling = detect_test_tooling(dependency_contents)
    except EmptyRepositoryError as exc:
        st.info(f"{exc} A health score can't be computed until it has some content.")
        return
    except GitHubAPIError as exc:
        st.error(str(exc))
        return

    result = compute_health_score(
        repo,
        commit_activity,
        contributors,
        issue_summary,
        project_files,
        test_signals,
        test_tooling,
    )

    status = st.success if result["score"] >= 80 else st.warning if result["score"] >= 60 else st.error
    status(f"Health score: {result['score']}/100 (grade {result['grade']})")

    chart_col, detail_col = st.columns([3, 2])

    with chart_col:
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
            title="Score by category",
        )
        fig.update_layout(showlegend=False, margin=dict(t=40, b=10))
        st.plotly_chart(fig, use_container_width=True, theme="streamlit")

    with detail_col:
        st.write("**Category details**")
        for item in result["breakdown"]:
            st.markdown(f"**{item['category']}** — {item['score']}/{item['max']}")
            st.caption(item["explanation"])


def build_analysis(repo: dict, ref, token: str | None) -> dict:
    """Gather structured, non-source-code data to send to the AI for insights.

    Reuses the same cached fetches the other tabs use, so this costs no
    extra GitHub API calls within the cache TTL.
    """
    commit_activity = summarize_commit_activity(fetch_commit_activity(ref.owner, ref.name, token))
    contributors = fetch_contributors(ref.owner, ref.name, token, limit=10)
    issue_summary = summarize_issues(fetch_issue_counts(ref.owner, ref.name, token))
    tree = fetch_tree(ref.owner, ref.name, repo["default_branch"], token)
    project_files = detect_project_files(tree)
    test_signals = detect_test_signals(tree)
    dependency_contents = {
        path: fetch_file_content(ref.owner, ref.name, path, token)
        for path in find_dependency_files(tree)
    }
    test_tooling = detect_test_tooling(dependency_contents)
    structure = analyze_file_structure(tree)
    languages = summarize_languages(fetch_languages(ref.owner, ref.name, token))

    health = compute_health_score(
        repo, commit_activity, contributors, issue_summary, project_files, test_signals, test_tooling
    )

    return {
        "repo_overview": {
            "full_name": repo["full_name"],
            "description": repo.get("description"),
            "stars": repo["stargazers_count"],
            "forks": repo["forks_count"],
            "watchers": repo["watchers_count"],
            "open_issues": repo["open_issues_count"],
            "license": (repo.get("license") or {}).get("name"),
            "created_at": repo["created_at"][:10],
            "updated_at": repo["updated_at"][:10],
        },
        "health_score": {
            "score": health["score"],
            "grade": health["grade"],
            "breakdown": health["breakdown"],
        },
        "languages": languages,
        "activity": {
            "commits_last_year": commit_activity["total_last_year"],
            "commits_last_4_weeks": commit_activity["total_last_4_weeks"],
            "trend": commit_activity["trend"],
            "known_contributor_count": len(contributors),
            "open_issues": issue_summary["open_issues"],
            "closed_issues": issue_summary["closed_issues"],
            "open_prs": issue_summary["open_prs"],
            "closed_prs": issue_summary["closed_prs"],
            "issue_close_rate": issue_summary["issue_close_rate"],
            "pr_close_rate": issue_summary["pr_close_rate"],
        },
        "structure": {
            "file_count": structure["file_count"],
            "dir_count": structure["dir_count"],
            "max_depth": structure["max_depth"],
            "top_extensions": structure["extensions"],
        },
        "project_files": project_files,
        "test_signals": {**test_signals, "test_tooling": test_tooling},
    }


def render_strengths_weaknesses(repo: dict, ref, token: str | None, ai_key: str) -> None:
    """Render the Strengths & Weaknesses tab using AI insights (Phase 6)."""
    api_key = get_api_key(ai_key)
    if not api_key:
        st.info("AI insights unavailable. Add an API key to enable this feature.")
        return

    cache_key = f"ai_insights::{repo['full_name']}"
    if cache_key not in st.session_state:
        try:
            with st.spinner("Generating AI insights..."):
                analysis = build_analysis(repo, ref, token)
                result = generate_insights(analysis, api_key)
        except InsightsError as exc:
            st.session_state[cache_key] = {"error": str(exc)}
        except GitHubAPIError as exc:
            st.session_state[cache_key] = {"error": str(exc)}
        else:
            st.session_state[cache_key] = {"result": result}

    cached = st.session_state[cache_key]
    if "error" in cached:
        st.error(f"Couldn't generate AI insights: {cached['error']}")
        return

    result = cached["result"]
    if not result["ok"]:
        st.warning("The AI response wasn't valid JSON, so here's the raw output instead:")
        st.text(result["raw_text"])
        return

    st.write("**Overall assessment**")
    st.write(result["overall_assessment"])

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.write("**Strengths**")
        for item in result["strengths"]:
            st.markdown(f"- {item}")
    with col2:
        st.write("**Weaknesses**")
        for item in result["weaknesses"]:
            st.markdown(f"- {item}")

    st.divider()
    st.write("**Recommendations**")
    for item in result["recommendations"]:
        st.markdown(f"- {item}")


def render_ask_section(repo: dict, ref, token: str | None, ai_key: str) -> None:
    """Render the 'Ask about this repository' Q&A section (Phase 7)."""
    api_key = get_api_key(ai_key)
    if not api_key:
        st.info("Ask feature unavailable. Add an API key to enable this.")
        return

    st.write(
        "Ask a question about this repository. Example: "
        "*\"Why is the health score low?\"*, *\"Is this repo actively maintained?\"*, "
        "*\"What should I improve first?\"*"
    )

    answer_key = f"qa_answer::{repo['full_name']}"
    question = st.text_input("Your question", key=f"qa_question::{repo['full_name']}")
    if st.button("Ask", key=f"qa_submit::{repo['full_name']}"):
        if not question.strip():
            st.warning("Enter a question first.")
        else:
            try:
                with st.spinner("Thinking..."):
                    analysis = build_analysis(repo, ref, token)
                    answer = answer_question(analysis, question, api_key)
            except (InsightsError, GitHubAPIError) as exc:
                st.session_state[answer_key] = {"question": question, "error": str(exc)}
            else:
                st.session_state[answer_key] = {"question": question, "answer": answer}

    if answer_key in st.session_state:
        cached = st.session_state[answer_key]
        st.divider()
        st.write(f"**Q: {cached['question']}**")
        if "error" in cached:
            st.error(f"Couldn't get an answer: {cached['error']}")
        else:
            st.write(cached["answer"])


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

    (
        overview_tab,
        health_tab,
        languages_tab,
        activity_tab,
        structure_tab,
        strengths_tab,
        ask_tab,
    ) = st.tabs(
        [
            "Overview",
            "Health Score",
            "Languages",
            "Activity",
            "Repository Structure",
            "Strengths & Weaknesses",
            "Ask about this repository",
        ]
    )
    with overview_tab:
        render_overview(repo_data)
    with health_tab:
        render_health_score(repo_data, ref, token)
    with languages_tab:
        render_languages(ref, token)
    with activity_tab:
        render_activity(ref, token)
    with structure_tab:
        render_repo_structure(repo_data, ref, token)
    with strengths_tab:
        render_strengths_weaknesses(repo_data, ref, token, ai_key)
    with ask_tab:
        render_ask_section(repo_data, ref, token, ai_key)
