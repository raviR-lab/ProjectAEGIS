"""Rank live Jira stories against a GitHub PR (files + title)."""

from __future__ import annotations

import re

from aegis.graph import schema
from aegis.graph.sync import canonicalize_domain

_STOP = {
    "the", "and", "for", "with", "from", "this", "that", "into", "onto",
    "feat", "chore", "fix", "add", "via", "src", "svc", "demo",
}
_WORD = re.compile(r"[a-z0-9]+")


def _tokens(*parts: str) -> set[str]:
    out: set[str] = set()
    for part in parts:
        for word in _WORD.findall((part or "").lower()):
            if len(word) >= 3 and word not in _STOP:
                out.add(word)
    return out


def score_story(
    story: dict,
    *,
    domains: set[str],
    haystack: set[str],
    linked_keys: set[str],
) -> tuple[int, list[str]]:
    key = str(story.get("key") or "")
    title = str(story.get("title") or "")
    epic = str(story.get("epic") or "").strip().lower()
    status = str(story.get("status") or "").strip().lower()
    score = 0
    reasons: list[str] = []

    inferred = canonicalize_domain(title) or canonicalize_domain(epic)
    if epic and epic in domains:
        score += 50
        reasons.append(f"epic '{epic}' matches the files' product area")
    elif inferred and inferred in domains:
        score += 40
        reasons.append(f"ticket is about {inferred}, the same area as the changed files")
    elif domains and (epic or inferred) and (epic not in domains) and (inferred not in domains):
        score -= 25
        reasons.append(
            f"ticket area '{epic or inferred}' does not match the files "
            f"({', '.join(sorted(domains))})"
        )

    overlap = haystack & _tokens(title, epic, key)
    if overlap:
        score += min(30, 10 * len(overlap))
        reasons.append("shared words: " + ", ".join(sorted(overlap)[:6]))

    if status in {"in_progress", "in-progress", "to_do", "todo", "selected_for_development"}:
        score += 8
        reasons.append("ticket is still in progress")
    elif status in {"done", "closed", "resolved"}:
        score -= 4

    if key in linked_keys:
        score += 5
        reasons.append("already mentioned on this PR")

    return score, reasons


def rank_jira_stories(
    stories: list[dict],
    *,
    pr_title: str,
    files: list[dict],
    linked_keys: list[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    """Return the best Jira stories for this PR, highest score first."""
    domains = {
        str(f.get("domain") or "").strip().lower()
        for f in files or []
        if f.get("domain")
    }
    services = [str(f.get("microservice") or "") for f in files or []]
    paths = [str(f.get("path") or "") for f in files or []]
    haystack = _tokens(pr_title, *paths, *services, *domains)
    linked = {str(k) for k in (linked_keys or []) if k}

    ranked: list[dict] = []
    for story in stories or []:
        key = str(story.get("key") or "").strip()
        if not key:
            continue
        score, reasons = score_story(
            story, domains=domains, haystack=haystack, linked_keys=linked,
        )
        if score < 10:
            continue
        ranked.append({
            "key": key,
            "title": story.get("title") or key,
            "epic": story.get("epic"),
            "status": story.get("status"),
            "score": score,
            "reasons": reasons,
        })
    ranked.sort(key=lambda row: (-int(row["score"]), str(row["key"])))
    return ranked[:limit]


def load_jira_stories(cig) -> list[dict]:
    rows = cig.run(
        f"MATCH (s:{schema.JIRA_STORY}) "
        "RETURN s.key AS key, s.title AS title, s.epic AS epic, s.status AS status "
        "ORDER BY s.key"
    )
    return [dict(r) for r in rows]


def suggest_jira_for_pr(cig, context: dict) -> list[dict]:
    """Rank Jira issues in the CIG against a gathered PR context."""
    pr = context.get("pr") or {}
    files = context.get("story_alignment", {}).get("files") or context.get("files") or []
    linked = [
        str(s.get("key") or "")
        for s in (context.get("stories") or [])
        if s.get("key")
    ]
    return rank_jira_stories(
        load_jira_stories(cig),
        pr_title=str(pr.get("title") or ""),
        files=files,
        linked_keys=linked,
    )
