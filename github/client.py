"""Thin client around the GitHub REST API, plus a cached fetch wrapper."""

from __future__ import annotations

import base64
import time

import requests
import streamlit as st

GITHUB_API_BASE = "https://api.github.com"
REQUEST_TIMEOUT = 10  # seconds


class GitHubAPIError(Exception):
    """Base error for GitHub API failures. Message is safe to show to users."""


class RepoNotFoundError(GitHubAPIError):
    """Repo doesn't exist, is private, or the name/owner is misspelled."""


class RateLimitError(GitHubAPIError):
    """GitHub's rate limit was hit for this token/IP."""


class GitHubClient:
    """Wraps the subset of the GitHub REST API this app needs.

    Has no Streamlit dependency, so it can be unit tested on its own.
    """

    def __init__(self, token: str | None = None):
        self.token = token or None

    def _headers(self) -> dict:
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        """Issue a GET request against the GitHub API and translate errors."""
        url = f"{GITHUB_API_BASE}{path}"
        try:
            response = requests.get(
                url, headers=self._headers(), params=params, timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.RequestException as exc:
            raise GitHubAPIError(f"Network error while contacting GitHub: {exc}") from exc

        if response.status_code == 404:
            raise RepoNotFoundError(
                "Repository not found. It may be private, misspelled, or deleted."
            )
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimitError(
                "GitHub API rate limit exceeded. Add a GitHub token in the "
                "sidebar to raise the limit from 60 to 5,000 requests/hour."
            )
        if response.status_code == 401:
            raise GitHubAPIError("GitHub token was rejected. Check that it's valid.")
        if not response.ok:
            raise GitHubAPIError(f"GitHub API error ({response.status_code}): {response.reason}")

        return response.json()

    def get_repo(self, owner: str, repo: str) -> dict:
        """GET /repos/{owner}/{repo} - core repository metadata."""
        return self._get(f"/repos/{owner}/{repo}")

    def get_languages(self, owner: str, repo: str) -> dict:
        """GET /repos/{owner}/{repo}/languages - bytes of code per language."""
        return self._get(f"/repos/{owner}/{repo}/languages")

    def get_contributors(self, owner: str, repo: str, limit: int = 10) -> list:
        """GET /repos/{owner}/{repo}/contributors - top contributors by commit count."""
        return self._get(f"/repos/{owner}/{repo}/contributors", params={"per_page": limit})

    def get_commit_activity(self, owner: str, repo: str) -> list:
        """GET /repos/{owner}/{repo}/stats/commit_activity - weekly commits, last 52 weeks.

        GitHub computes this asynchronously: a 202 with an empty body means
        "still computing" - retry a few times with a short delay before
        giving up and returning an empty list.
        """
        for attempt in range(3):
            data = self._get(f"/repos/{owner}/{repo}/stats/commit_activity")
            if data:
                return data
            if attempt < 2:
                time.sleep(1.5)
        return []

    def get_issue_counts(self, owner: str, repo: str) -> dict:
        """Open/closed issue and PR counts via the Search API.

        Uses total_count from search results rather than paginating the
        full issue list, so each figure costs one request.
        """
        counts = {}
        queries = {
            "open_issues": "is:issue is:open",
            "closed_issues": "is:issue is:closed",
            "open_prs": "is:pr is:open",
            "closed_prs": "is:pr is:closed",
        }
        for key, query in queries.items():
            result = self._get(
                "/search/issues",
                params={"q": f"repo:{owner}/{repo} {query}", "per_page": 1},
            )
            counts[key] = result.get("total_count", 0)
        return counts

    def get_tree(self, owner: str, repo: str, branch: str) -> dict:
        """GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1 - full file tree."""
        return self._get(
            f"/repos/{owner}/{repo}/git/trees/{branch}", params={"recursive": "1"}
        )

    def get_file_content(self, owner: str, repo: str, path: str) -> str | None:
        """GET /repos/{owner}/{repo}/contents/{path} - decoded text content.

        Returns None if the file doesn't exist rather than raising, since
        callers use this to opportunistically probe for optional manifests.
        """
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
        try:
            response = requests.get(url, headers=self._headers(), timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as exc:
            raise GitHubAPIError(f"Network error while contacting GitHub: {exc}") from exc

        if response.status_code == 404:
            return None
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            raise RateLimitError(
                "GitHub API rate limit exceeded. Add a GitHub token in the "
                "sidebar to raise the limit from 60 to 5,000 requests/hour."
            )
        if not response.ok:
            raise GitHubAPIError(f"GitHub API error ({response.status_code}): {response.reason}")

        data = response.json()
        if data.get("encoding") != "base64" or "content" not in data:
            return None
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_repo(owner: str, repo: str, token: str | None = None) -> dict:
    """Cached fetch of repository metadata.

    Cached per (owner, repo, token) for 5 minutes so re-running the app
    (e.g. from widget interactions) doesn't burn extra API calls.
    """
    return GitHubClient(token).get_repo(owner, repo)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_languages(owner: str, repo: str, token: str | None = None) -> dict:
    """Cached fetch of the repo's language byte-count breakdown."""
    return GitHubClient(token).get_languages(owner, repo)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_contributors(
    owner: str, repo: str, token: str | None = None, limit: int = 10
) -> list:
    """Cached fetch of the repo's top contributors."""
    return GitHubClient(token).get_contributors(owner, repo, limit)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_commit_activity(owner: str, repo: str, token: str | None = None) -> list:
    """Cached fetch of weekly commit activity for the last year."""
    return GitHubClient(token).get_commit_activity(owner, repo)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_issue_counts(owner: str, repo: str, token: str | None = None) -> dict:
    """Cached fetch of open/closed issue and PR counts."""
    return GitHubClient(token).get_issue_counts(owner, repo)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_tree(owner: str, repo: str, branch: str, token: str | None = None) -> dict:
    """Cached fetch of the full repository file tree for a branch."""
    return GitHubClient(token).get_tree(owner, repo, branch)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_file_content(
    owner: str, repo: str, path: str, token: str | None = None
) -> str | None:
    """Cached fetch of a single file's decoded text content, or None if missing."""
    return GitHubClient(token).get_file_content(owner, repo, path)
