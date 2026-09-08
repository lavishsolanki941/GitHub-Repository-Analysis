"""Repo tree / file structure analysis."""

from __future__ import annotations

import posixpath
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
