"""Commit/contributor/issue activity analysis."""

from __future__ import annotations

from datetime import datetime, timezone


def summarize_commit_activity(weekly_activity: list[dict]) -> dict:
    """Turn raw weekly commit_activity stats into a chart-ready summary.

    Args:
        weekly_activity: list of {"week": unix_ts, "total": int, "days": [...]},
            oldest week first, as returned by GitHub's stats/commit_activity.

    Returns:
        dict with per-week dates/counts and a simple recent-trend read
        (last 4 weeks vs. the 4 weeks before that).
    """
    if not weekly_activity:
        return {
            "weeks": [],
            "counts": [],
            "total_last_year": 0,
            "total_last_4_weeks": 0,
            "total_prior_4_weeks": 0,
            "trend": "unknown",
        }

    weeks = [
        datetime.fromtimestamp(w["week"], tz=timezone.utc).date().isoformat()
        for w in weekly_activity
    ]
    counts = [w["total"] for w in weekly_activity]

    last_4 = sum(counts[-4:])
    prior_4 = sum(counts[-8:-4]) if len(counts) >= 8 else 0

    if prior_4 == 0:
        trend = "increasing" if last_4 > 0 else "quiet"
    elif last_4 > prior_4 * 1.1:
        trend = "increasing"
    elif last_4 < prior_4 * 0.9:
        trend = "decreasing"
    else:
        trend = "steady"

    return {
        "weeks": weeks,
        "counts": counts,
        "total_last_year": sum(counts),
        "total_last_4_weeks": last_4,
        "total_prior_4_weeks": prior_4,
        "trend": trend,
    }


def summarize_contributors(contributors: list[dict], limit: int = 10) -> list[dict]:
    """Reduce raw contributor payloads to the fields the UI needs, ranked by commits."""
    ranked = sorted(contributors, key=lambda c: c.get("contributions", 0), reverse=True)
    return [
        {
            "login": c["login"],
            "contributions": c["contributions"],
            "avatar_url": c.get("avatar_url"),
            "html_url": c.get("html_url"),
        }
        for c in ranked[:limit]
    ]


def summarize_issues(counts: dict) -> dict:
    """Derive open/closed totals and close rates from raw issue and PR counts."""
    open_issues = counts.get("open_issues", 0)
    closed_issues = counts.get("closed_issues", 0)
    open_prs = counts.get("open_prs", 0)
    closed_prs = counts.get("closed_prs", 0)

    total_issues = open_issues + closed_issues
    total_prs = open_prs + closed_prs

    return {
        "open_issues": open_issues,
        "closed_issues": closed_issues,
        "open_prs": open_prs,
        "closed_prs": closed_prs,
        "issue_close_rate": closed_issues / total_issues if total_issues else None,
        "pr_close_rate": closed_prs / total_prs if total_prs else None,
    }
