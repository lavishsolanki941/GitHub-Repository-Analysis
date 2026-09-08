"""GitHub Repository Analyzer - Streamlit entry point."""

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="GitHub Repository Analyzer",
    page_icon=":mag:",
    layout="wide",
)

with st.sidebar:
    st.header("GitHub Repository Analyzer")
    repo_url = st.text_input("Repository URL", placeholder="https://github.com/owner/repo")
    github_token = st.text_input("GitHub token (optional)", type="password")
    ai_key = st.text_input("AI API key (optional)", type="password")
    analyze_clicked = st.button("Analyze", type="primary")

st.title("GitHub Repository Analyzer")
st.write(
    "Enter a public GitHub repository URL in the sidebar and click **Analyze** "
    "to get an overview, health score, and optional AI insights."
)

if analyze_clicked:
    st.info("Analysis logic hasn't been built yet — coming in Phase 2.")
