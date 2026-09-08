"""GitHub Repository Analyzer - Streamlit entry point."""

import os

import streamlit as st
from dotenv import load_dotenv

from github.client import GitHubAPIError, fetch_repo
from github.parser import InvalidRepoURLError, parse_repo_url

load_dotenv()

st.set_page_config(
    page_title="GitHub Repository Analyzer",
    page_icon=":mag:",
    layout="wide",
)

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
    render_overview(st.session_state["repo_data"])
