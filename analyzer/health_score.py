"""Deterministic repository health score.

Combines signals already gathered for the Overview/Activity/Code Structure
tabs into a single 0-100 score with a per-category breakdown, entirely from
arithmetic on API data - no AI involved (that's Phases 6-7).
"""

from __future__ import annotations

from datetime import datetime, timezone

_GRADE_THRESHOLDS = [(90, "A"), (80, "B"), (70, "C"), (60, "D")]


def _grade(score: int) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


def _score_maintenance(repo: dict, commit_activity: dict) -> tuple[int, str]:
    """Recency of the last update, nudged by the recent commit trend."""
    updated_at = datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00"))
    days_since_update = (datetime.now(timezone.utc) - updated_at).days

    if days_since_update <= 7:
        score = 25
    elif days_since_update <= 30:
        score = 20
    elif days_since_update <= 90:
        score = 13
    elif days_since_update <= 365:
        score = 7
    else:
        score = 0

    trend = commit_activity.get("trend")
    if trend == "decreasing":
        score = max(0, score - 5)
    elif trend == "increasing":
        score = min(25, score + 5)

    explanation = f"Last updated {days_since_update} days ago"
    if trend not in (None, "unknown"):
        explanation += f"; commit trend is {trend}"
    return score, explanation


def _score_license(repo: dict) -> tuple[int, str]:
    license_info = repo.get("license")
    if license_info:
        return 5, f"Licensed under {license_info['name']}"
    return 0, "No license detected"


def _score_documentation(project_files: dict) -> tuple[int, str]:
    score = 0
    notes = []
    if project_files.get("has_readme"):
        score += 4
        notes.append("README present")
    else:
        notes.append("no README")
    if project_files.get("has_contributing"):
        score += 3
        notes.append("CONTRIBUTING guide present")
    else:
        notes.append("no CONTRIBUTING guide")
    if project_files.get("has_ci"):
        score += 3
        notes.append("CI workflow present")
    else:
        notes.append("no CI workflow")
    return score, "; ".join(notes)


def _score_issue_health(issue_summary: dict) -> tuple[int, str]:
    max_points = 15
    rates = [
        r
        for r in (issue_summary.get("issue_close_rate"), issue_summary.get("pr_close_rate"))
        if r is not None
    ]
    if not rates:
        return max_points // 2, "No issue/PR history to measure"
    avg_rate = sum(rates) / len(rates)
    return round(avg_rate * max_points), f"{avg_rate:.0%} average issue/PR close rate"


def _score_contributor_diversity(contributors: list[dict]) -> tuple[int, str]:
    max_points = 15
    total = sum(c.get("contributions", 0) for c in contributors)
    if not contributors or total == 0:
        return 0, "No contributor data available"
    if len(contributors) == 1:
        return 3, "Single known contributor - high bus-factor risk"

    top_share = contributors[0].get("contributions", 0) / total
    if top_share < 0.4:
        return max_points, f"Well distributed - top contributor holds {top_share:.0%} of commits"
    if top_share < 0.7:
        return 8, f"Moderately concentrated - top contributor holds {top_share:.0%} of commits"
    return 3, f"Highly concentrated - top contributor holds {top_share:.0%} of commits"


def _score_testing(test_signals: dict, test_tooling: list[str]) -> tuple[int, str]:
    """Test directory, test-file count, and known test tooling in dependency files."""
    score = 0
    notes = []

    if test_signals.get("has_test_dir"):
        score += 5
        notes.append("test directory present")
    else:
        notes.append("no dedicated test directory")

    count = test_signals.get("test_file_count", 0)
    if count >= 20:
        score += 7
        notes.append(f"{count} test files (healthy coverage)")
    elif count >= 5:
        score += 5
        notes.append(f"{count} test files")
    elif count >= 1:
        score += 3
        notes.append(f"{count} test file(s)")
    else:
        notes.append("no test files detected")

    if test_tooling:
        score += 3
        notes.append(f"test tooling detected: {', '.join(test_tooling)}")
    else:
        notes.append("no test tooling detected in dependency files")

    return score, "; ".join(notes)


def _score_popularity(repo: dict) -> tuple[int, str]:
    stars = repo.get("stargazers_count", 0)
    for threshold, points in [(10000, 15), (1000, 12), (100, 8), (10, 4), (0, 1)]:
        if stars >= threshold:
            return points, f"{stars:,} stars"
    return 0, "No stars yet"


def compute_health_score(
    repo: dict,
    commit_activity: dict,
    contributors: list[dict],
    issue_summary: dict,
    project_files: dict,
    test_signals: dict,
    test_tooling: list[str],
) -> dict:
    """Combine repo signals into a single deterministic 0-100 health score.

    Args:
        repo: raw repo payload from GET /repos/{owner}/{repo}.
        commit_activity: output of analyzer.activity.summarize_commit_activity.
        contributors: raw contributor list from GET /repos/{owner}/{repo}/contributors,
            ranked by contributions (most first).
        issue_summary: output of analyzer.activity.summarize_issues.
        project_files: output of analyzer.code_analysis.detect_project_files.
        test_signals: output of analyzer.code_analysis.detect_test_signals.
        test_tooling: output of analyzer.code_analysis.detect_test_tooling.

    Returns:
        dict with "score" (0-100), "grade" (A-F), and a "breakdown" list of
        per-category {"category", "score", "max", "explanation"} entries.
    """
    categories = [
        ("Maintenance & recency", 25, _score_maintenance(repo, commit_activity)),
        ("Issue & PR responsiveness", 15, _score_issue_health(issue_summary)),
        ("Testing", 15, _score_testing(test_signals, test_tooling)),
        ("Contributor diversity", 15, _score_contributor_diversity(contributors)),
        ("Popularity", 15, _score_popularity(repo)),
        ("Documentation & CI", 10, _score_documentation(project_files)),
        ("License", 5, _score_license(repo)),
    ]

    breakdown = [
        {"category": name, "score": score, "max": max_points, "explanation": explanation}
        for name, max_points, (score, explanation) in categories
    ]
    total = sum(item["score"] for item in breakdown)

    return {"score": total, "grade": _grade(total), "breakdown": breakdown}
