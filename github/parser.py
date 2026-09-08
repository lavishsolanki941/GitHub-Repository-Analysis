"""Parsing of GitHub repository references from user input."""

from __future__ import annotations

import re
from dataclasses import dataclass


class InvalidRepoURLError(ValueError):
    """Raised when a string can't be parsed as a GitHub repo reference."""


@dataclass(frozen=True)
class RepoRef:
    """A resolved reference to a GitHub repository."""

    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


_OWNER = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_NAME = r"[A-Za-z0-9_.-]+"

_GITHUB_URL_RE = re.compile(
    rf"^(?:https?://)?(?:www\.)?github\.com/({_OWNER})/({_NAME}?)(?:\.git)?/?$"
)
_SHORTHAND_RE = re.compile(rf"^({_OWNER})/({_NAME})$")


def parse_repo_url(text: str) -> RepoRef:
    """Parse a GitHub URL or an 'owner/repo' shorthand into a RepoRef.

    Args:
        text: Raw user input, e.g. "https://github.com/pandas-dev/pandas".

    Returns:
        A RepoRef with the owner and repo name.

    Raises:
        InvalidRepoURLError: if the text isn't a recognizable GitHub
            repository reference.
    """
    text = text.strip()
    if not text:
        raise InvalidRepoURLError("Please enter a repository URL.")

    match = _GITHUB_URL_RE.match(text) or _SHORTHAND_RE.match(text)
    if not match or not match.group(2):
        raise InvalidRepoURLError(
            "Couldn't parse that as a GitHub repository. Use a URL like "
            "https://github.com/owner/repo, or just 'owner/repo'."
        )

    return RepoRef(owner=match.group(1), name=match.group(2))
