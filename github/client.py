"""Thin client around the GitHub REST API, plus a cached fetch wrapper."""

from __future__ import annotations

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


@st.cache_data(ttl=300, show_spinner=False)
def fetch_repo(owner: str, repo: str, token: str | None = None) -> dict:
    """Cached fetch of repository metadata.

    Cached per (owner, repo, token) for 5 minutes so re-running the app
    (e.g. from widget interactions) doesn't burn extra API calls.
    """
    client = GitHubClient(token)
    return client.get_repo(owner, repo)
