"""Repo tree / file structure analysis."""

from __future__ import annotations

import posixpath
import re
from collections import Counter


def analyze_file_structure(tree: dict, top_n: int = 10) -> dict:
    """Summarize a GitHub git-tree payload into file structure stats.

    Args:
        tree: payload from GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1,
            with a "tree" list of {path, type, size, ...} and a "truncated" flag.
        top_n: how many entries to keep in the extension and largest-files
            breakdowns.

    Returns:
        dict with file/dir counts, extension breakdown, largest files, max
        depth, and whether GitHub truncated the tree (very large repos).
    """
    entries = tree.get("tree", [])
    files = [e for e in entries if e.get("type") == "blob"]
    dirs = [e for e in entries if e.get("type") == "tree"]

    ext_counter: Counter[str] = Counter()
    for f in files:
        _, ext = posixpath.splitext(f["path"])
        ext_counter[ext.lower() if ext else "(no extension)"] += 1

    largest_files = sorted(
        (f for f in files if "size" in f), key=lambda f: f["size"], reverse=True
    )[:top_n]

    max_depth = max((e["path"].count("/") for e in entries), default=0)

    return {
        "file_count": len(files),
        "dir_count": len(dirs),
        "max_depth": max_depth,
        "extensions": ext_counter.most_common(top_n),
        "largest_files": [{"path": f["path"], "size": f["size"]} for f in largest_files],
        "truncated": tree.get("truncated", False),
    }


def detect_project_files(tree: dict) -> dict:
    """Detect presence of common community-health files in a repo tree.

    Args:
        tree: payload from GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1.

    Returns:
        dict of booleans: has_readme, has_contributing, has_ci.
    """
    paths = [e["path"].lower() for e in tree.get("tree", []) if e.get("type") == "blob"]
    return {
        "has_readme": any(p.rsplit("/", 1)[-1].startswith("readme") for p in paths),
        "has_contributing": any(p.rsplit("/", 1)[-1].startswith("contributing") for p in paths),
        "has_ci": any(p.startswith(".github/workflows/") for p in paths),
    }


_TEST_FILE_PATTERNS = [
    re.compile(r"(?:^|/)test_[^/]+\.py$", re.I),
    re.compile(r"(?:^|/)[^/]+_test\.py$", re.I),
    re.compile(r"(?:^|/)[^/]+\.test\.[jt]sx?$", re.I),
    re.compile(r"(?:^|/)[^/]+\.spec\.[jt]sx?$", re.I),
    re.compile(r"(?:^|/)[^/]+_spec\.rb$", re.I),
    re.compile(r"(?:^|/)spec_[^/]+\.rb$", re.I),
    re.compile(r"(?:^|/)[^/]+Test\.java$"),
    re.compile(r"(?:^|/)[^/]+_test\.go$", re.I),
    re.compile(r"(?:^|/)Test[^/]+\.php$"),
    re.compile(r"(?:^|/)[^/]+Test\.php$"),
]

_TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs"}


def detect_test_signals(tree: dict) -> dict:
    """Detect test-related signals from a repo tree.

    Args:
        tree: payload from GET /repos/{owner}/{repo}/git/trees/{sha}?recursive=1.

    Returns:
        dict with has_test_dir (bool) and test_file_count (int), the raw
        material for the Testing health-score category.
    """
    entries = tree.get("tree", [])
    files = [e["path"] for e in entries if e.get("type") == "blob"]
    dirs = [e["path"] for e in entries if e.get("type") == "tree"]

    test_file_count = sum(
        1 for path in files if any(pattern.search(path) for pattern in _TEST_FILE_PATTERNS)
    )
    has_test_dir = any(
        segment.lower() in _TEST_DIR_NAMES for path in dirs for segment in path.split("/")
    )

    return {"has_test_dir": has_test_dir, "test_file_count": test_file_count}


_DEPENDENCY_FILENAMES = {
    "requirements.txt",
    "requirements-dev.txt",
    "requirements_dev.txt",
    "pyproject.toml",
    "pipfile",
    "setup.py",
    "package.json",
    "gemfile",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "go.mod",
    "composer.json",
}

_IGNORED_DIR_SEGMENTS = {"node_modules", "vendor", "dist", "build", ".venv", "venv"}


def find_dependency_files(tree: dict, limit: int = 5) -> list[str]:
    """Find likely dependency-manifest paths in a repo tree.

    Skips vendored/build directories so a stray `package.json` under
    `node_modules/` doesn't get picked over the project's own manifest.
    Shallower matches are preferred.
    """
    matches = []
    for e in tree.get("tree", []):
        if e.get("type") != "blob":
            continue
        segments = e["path"].split("/")
        if any(seg.lower() in _IGNORED_DIR_SEGMENTS for seg in segments[:-1]):
            continue
        if segments[-1].lower() in _DEPENDENCY_FILENAMES:
            matches.append(e["path"])
    matches.sort(key=lambda p: p.count("/"))
    return matches[:limit]


_TEST_TOOLING_KEYWORDS = {
    "pytest": "pytest",
    "unittest": "unittest",
    "nose": "nose",
    "tox": "tox",
    "jest": "jest",
    "mocha": "mocha",
    "vitest": "vitest",
    "junit": "junit",
    "rspec": "rspec",
    "phpunit": "phpunit",
}


def detect_test_tooling(dependency_contents: dict[str, str | None]) -> list[str]:
    """Scan dependency-file contents for well-known test tooling names.

    Args:
        dependency_contents: {path: file text or None} for manifests found
            by find_dependency_files.

    Returns:
        Sorted list of recognized tool names found (e.g. ["jest", "pytest"]).
    """
    found = set()
    for content in dependency_contents.values():
        if not content:
            continue
        lowered = content.lower()
        for tool, keyword in _TEST_TOOLING_KEYWORDS.items():
            if keyword in lowered:
                found.add(tool)
    return sorted(found)


def summarize_languages(languages: dict, top_n: int = 6) -> list[dict]:
    """Convert a {language: bytes} payload into a percentage breakdown.

    Languages past `top_n` are folded into an "Other" bucket so the chart
    stays readable.
    """
    total = sum(languages.values())
    if not total:
        return []

    ranked = sorted(languages.items(), key=lambda kv: kv[1], reverse=True)
    top, rest = ranked[:top_n], ranked[top_n:]

    breakdown = [
        {"language": lang, "bytes": count, "percent": round(count / total * 100, 1)}
        for lang, count in top
    ]
    if rest:
        other_bytes = sum(count for _, count in rest)
        breakdown.append(
            {"language": "Other", "bytes": other_bytes, "percent": round(other_bytes / total * 100, 1)}
        )
    return breakdown
