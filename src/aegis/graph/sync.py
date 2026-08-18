"""Push live GitHub / Jira state into Neo4j (no wipe).

Callers:
  - PR analysis (blocking, one PR)
  - PR picker (debounced title refresh)
  - scripts/seed_graph.py (optional wipe, then this apply path)
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from aegis.graph import ingest, schema
from aegis.integrations.github_client import GitHubClient, GitHubError, github_configured
from aegis.integrations.jira_client import JiraClient, JiraError, jira_configured, project_key

STORY_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")
LANG_BY_EXT = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".rs": "rust",
}

_TITLE_SYNC_AT = 0.0
_TITLE_SYNC_EVERY_S = 5.0
_JIRA_SYNC_AT = 0.0
_JIRA_SYNC_EVERY_S = 60.0
_PR_FETCH_CACHE: dict[int, tuple[float, dict]] = {}
_PR_FETCH_TTL_S = 45.0
_GH_JSON_FIELDS = (
    "number,title,author,baseRefName,headRefName,state,body,files"
)


class SyncError(RuntimeError):
    pass


def canonicalize_domain(text: str | None) -> str | None:
    t = (text or "").strip().lower()
    if not t:
        return None
    if any(token in t for token in ("pay", "bill", "refund", "gateway")):
        return "payments"
    if any(token in t for token in (
        "auth", "platform", "admin", "notif", "infra",
        "token", "signing", "jwt", "oauth", "session",
    )):
        return "platform"
    if any(token in t for token in ("order", "invent", "commerce", "checkout", "cart")):
        return "commerce"
    return None


def domain_for_service(name: str) -> str:
    return canonicalize_domain(name) or name.replace("-svc", "").replace("_svc", "").lower()


def language_for_path(path: str) -> str:
    return LANG_BY_EXT.get(Path(path).suffix.lower(), Path(path).suffix.lstrip(".") or "unknown")


def service_for_path(path: str) -> str:
    first = path.split("/", 1)[0].strip()
    if first and first not in {".", ".."} and not first.startswith("."):
        return first
    return "repo"


def story_keys_in_text(*parts: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for match in STORY_KEY_RE.findall(part or ""):
            if match not in seen:
                seen.add(match)
                found.append(match)
    return found


def _login(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("login") or obj.get("name") or "")
    return str(obj or "")


def _ref(obj: Any) -> str:
    if isinstance(obj, dict):
        return str(obj.get("ref") or obj.get("label") or "")
    return str(obj or "")


def normalize_pr(raw: dict) -> dict:
    user = raw.get("user") or raw.get("author") or {}
    return {
        "number": int(raw.get("number") or 0),
        "title": str(raw.get("title") or ""),
        "body": str(raw.get("body") or ""),
        "author": _login(user),
        "base": _ref(raw.get("base")) or str(raw.get("baseRefName") or "main"),
        "head": _ref(raw.get("head")) or str(raw.get("headRefName") or ""),
        "state": str(raw.get("state") or "open").lower(),
    }


def normalize_files(raw_files: list[dict]) -> list[dict]:
    out = []
    for item in raw_files:
        path = item.get("filename") or item.get("path") or item.get("name")
        if not path:
            continue
        out.append({
            "path": str(path),
            "additions": int(item.get("additions") or 0),
            "deletions": int(item.get("deletions") or 0),
        })
    return out


def _gh_repo() -> str:
    from aegis import config

    owner = config.setting("GITHUB_REPO_OWNER")
    repo = config.setting("GITHUB_REPO_NAME")
    if not owner or not repo:
        raise SyncError("Set GITHUB_REPO_OWNER and GITHUB_REPO_NAME in .env")
    return f"{owner}/{repo}"


def _gh_available() -> bool:
    return bool(shutil.which("gh"))


def _run_gh(args: list[str]) -> str:
    listed = subprocess.run(args, check=True, capture_output=True, text=True)
    return listed.stdout or "[]"


def prs_from_github_payload(raw_list: list[dict]) -> list[dict]:
    """Normalize GitHub REST / gh / MCP PR objects (with optional file lists)."""
    out = []
    for raw in raw_list or []:
        if not isinstance(raw, dict):
            continue
        pr = normalize_pr(raw)
        if not pr["number"]:
            continue
        files = raw.get("files")
        if files is None:
            pr["files"] = []
        else:
            pr["files"] = normalize_files(files if isinstance(files, list) else [])
        out.append(pr)
    return out


def fetch_github_pr_stubs() -> list[dict]:
    """Titles and metadata — prefers `gh` so Streamlit does not wait on npx."""
    if not github_configured():
        raise SyncError("GitHub is not configured")
    if _gh_available():
        try:
            return _fetch_pr_stubs_via_gh()
        except (subprocess.CalledProcessError, OSError, json.JSONDecodeError):
            pass
    try:
        client = GitHubClient()
        pulls = [normalize_pr(p) for p in client.list_pull_requests(state="all") if p]
        return [p for p in pulls if p["number"]]
    except (GitHubError, Exception) as exc:
        if _gh_available():
            return _fetch_pr_stubs_via_gh()
        raise SyncError(f"GitHub PR list failed: {exc}") from exc


def _fetch_pr_stubs_via_gh() -> list[dict]:
    spec = _gh_repo()
    raw = json.loads(_run_gh([
        "gh", "pr", "list", "--repo", spec, "--state", "all", "--limit", "50",
        "--json", "number,title,author,baseRefName,headRefName,state,body",
    ]))
    return prs_from_github_payload(raw if isinstance(raw, list) else [])


def fetch_github_pr(number: int) -> dict:
    cached = _PR_FETCH_CACHE.get(int(number))
    if cached and (time.time() - cached[0]) < _PR_FETCH_TTL_S:
        return cached[1]
    if not github_configured():
        raise SyncError("GitHub is not configured")
    pr = None
    errors: list[str] = []
    if _gh_available():
        try:
            pr = _fetch_github_pr_via_gh(int(number))
        except Exception as exc:
            errors.append(f"gh: {exc}")
    if pr is None:
        try:
            client = GitHubClient()
            raw, files = client.get_pull_request_bundle(int(number))
            if isinstance(raw, dict) and (raw.get("number") or raw.get("title") or files):
                pr = normalize_pr(raw)
                pr["number"] = pr["number"] or int(number)
                pr["files"] = normalize_files(files)
        except (GitHubError, Exception) as exc:
            errors.append(f"mcp: {exc}")
    if pr is None or not pr.get("number"):
        detail = "; ".join(errors) or "unknown error"
        raise SyncError(f"GitHub PR #{number} could not be loaded: {detail}")
    _PR_FETCH_CACHE[int(pr["number"])] = (time.time(), pr)
    return pr


def _fetch_github_pr_via_gh(number: int) -> dict:
    spec = _gh_repo()
    raw = json.loads(_run_gh([
        "gh", "pr", "view", str(number), "--repo", spec,
        "--json", _GH_JSON_FIELDS,
    ]))
    if not isinstance(raw, dict):
        raise SyncError(f"GitHub PR #{number} not found")
    prs = prs_from_github_payload([raw])
    if not prs:
        raise SyncError(f"GitHub PR #{number} not found")
    pr = prs[0]
    pr["number"] = pr["number"] or int(number)
    return pr


def fetch_github_prs() -> list[dict]:
    if not github_configured():
        raise SyncError("GitHub is not configured")
    if _gh_available():
        try:
            spec = _gh_repo()
            raw = json.loads(_run_gh([
                "gh", "pr", "list", "--repo", spec, "--state", "all", "--limit", "50",
                "--json", _GH_JSON_FIELDS,
            ]))
            pulls = prs_from_github_payload(raw if isinstance(raw, list) else [])
            if pulls:
                now = time.time()
                for pr in pulls:
                    _PR_FETCH_CACHE[pr["number"]] = (now, pr)
                return pulls
        except (subprocess.CalledProcessError, OSError, json.JSONDecodeError):
            pass
    try:
        bundles = GitHubClient().list_pull_requests_with_files(state="all")
        out = []
        now = time.time()
        for raw, files in bundles:
            pr = normalize_pr(raw)
            if not pr["number"]:
                continue
            pr["files"] = normalize_files(files)
            _PR_FETCH_CACHE[pr["number"]] = (now, pr)
            out.append(pr)
        if out:
            return out
    except (GitHubError, Exception):
        pass
    stubs = fetch_github_pr_stubs()
    out = []
    for stub in stubs:
        try:
            out.append(fetch_github_pr(stub["number"]))
        except (SyncError, subprocess.CalledProcessError, GitHubError):
            stub["files"] = stub.get("files") or []
            out.append(stub)
    return out


def _field_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("value") or value.get("name") or value.get("summary") or "")
    return str(value)


def epic_for_issue(fields: dict) -> str:
    parent = fields.get("parent") or {}
    parent_fields = parent.get("fields") or {}
    components = fields.get("components") or []
    labels = fields.get("labels") or []
    candidates = [
        _field_text(fields.get("customfield_10011")),
        _field_text(parent_fields.get("summary")),
        _field_text(parent.get("key")),
        _field_text(components[0] if components else None),
        _field_text(labels[0] if labels else None),
        _field_text(fields.get("summary")),
        _field_text((fields.get("issuetype") or {}).get("name")),
    ]
    for raw in candidates:
        known = canonicalize_domain(raw)
        if known:
            return known
    for raw in candidates:
        if raw.strip():
            return raw.strip().lower()
    return "uncategorized"


def story_points(fields: dict) -> int | None:
    raw = fields.get("customfield_10016")
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def _story_from_issue(issue: dict) -> dict | None:
    fields = issue.get("fields") or {}
    issue_key = str(issue.get("key") or "").strip()
    if not issue_key:
        return None
    status = ((fields.get("status") or {}).get("name") or "").strip().lower().replace(" ", "_")
    return {
        "key": issue_key,
        "title": str(fields.get("summary") or issue_key),
        "status": status or None,
        "points": story_points(fields),
        "epic": epic_for_issue(fields),
    }


def fetch_jira_stories() -> list[dict]:
    if not jira_configured():
        raise SyncError("Jira is not configured")
    key = project_key()
    try:
        client = JiraClient.from_config()
        issues = client.search_issues(f"project = {key} ORDER BY key ASC", max_results=100)
    except JiraError as exc:
        raise SyncError(f"Jira search failed: {exc}") from exc
    stories = []
    for issue in issues:
        story = _story_from_issue(issue)
        if story:
            stories.append(story)
    return stories


def _story_in_graph(cig, key: str) -> bool:
    rows = cig.run(
        f"MATCH (s:{schema.JIRA_STORY} {{key: $key}}) RETURN s.key AS key",
        key=key,
    )
    return bool(rows)


def ensure_jira_story(cig, key: str) -> bool:
    """Ingest a single Jira issue if it is not already in the graph."""
    if _story_in_graph(cig, key):
        return True
    if not jira_configured():
        return False
    try:
        issue = JiraClient.from_config().get_issue(key)
    except JiraError:
        return False
    if not isinstance(issue, dict):
        return False
    story = _story_from_issue(issue)
    if not story:
        return False
    ingest.ingest_jira_story(
        cig, story["key"], story["title"],
        status=story["status"], points=story["points"], epic=story["epic"],
    )
    return True


def apply_pull_request(cig, pr: dict, *, relink_stories: bool = True) -> None:
    """Write one live GitHub PR into Neo4j (title, files, Jira keys from title/body)."""
    number = int(pr.get("number") or 0)
    if not number:
        return
    title = str(pr.get("title") or "")
    ingest.ingest_pull_request(
        cig, number, title, pr.get("author") or "unknown",
        base=pr.get("base") or "main", head=pr.get("head") or "",
        state=pr.get("state") or "open",
    )
    for change in pr.get("files") or []:
        path = change.get("path")
        if not path:
            continue
        svc = service_for_path(path)
        ingest.ingest_microservice(cig, svc, domain=domain_for_service(svc))
        ingest.ingest_code_file(
            cig, path, language=language_for_path(path), microservice=svc,
        )
    if "files" in pr:
        ingest.replace_pr_changes(cig, number, pr.get("files") or [])
    if not relink_stories:
        return
    keys = story_keys_in_text(title, pr.get("body") or "")
    ingest.unlink_pr_stories(cig, number)
    for key in keys:
        if ensure_jira_story(cig, key):
            ingest.link_pr_to_story(cig, number, key)


def refresh_pr_titles(cig, *, force: bool = False) -> int:
    """Update every PR title in Neo4j from GitHub. Debounced for Streamlit reruns."""
    global _TITLE_SYNC_AT
    if not github_configured():
        return 0
    now = time.time()
    if not force and (now - _TITLE_SYNC_AT) < _TITLE_SYNC_EVERY_S:
        return 0
    _TITLE_SYNC_AT = now
    pulls = fetch_github_pr_stubs()
    for pr in pulls:
        ingest.ingest_pull_request(
            cig, pr["number"], pr["title"], pr.get("author") or "unknown",
            base=pr.get("base") or "main", head=pr.get("head") or "",
            state=pr.get("state") or "open",
        )
    return len(pulls)


def refresh_jira_stories(cig, *, force: bool = False) -> int:
    """Pull live Jira issues into Neo4j so suggestions and alignment stay current."""
    global _JIRA_SYNC_AT
    if not jira_configured():
        return 0
    now = time.time()
    if not force and (now - _JIRA_SYNC_AT) < _JIRA_SYNC_EVERY_S:
        return 0
    stories = fetch_jira_stories()
    for story in stories:
        ingest.ingest_jira_story(
            cig, story["key"], story["title"],
            status=story["status"], points=story["points"], epic=story["epic"],
        )
    _JIRA_SYNC_AT = now
    return len(stories)


def refresh_pull_request(cig, pr_number: int) -> dict:
    """Blocking GitHub → Neo4j sync for one PR (title, files, story links)."""
    pr = fetch_github_pr(int(pr_number))
    apply_pull_request(cig, pr, relink_stories=True)
    return pr


def seed(cig, *, wipe: bool = True) -> dict:
    pulls = fetch_github_prs()
    stories = fetch_jira_stories()
    if wipe:
        ingest.reset_graph(cig)
    else:
        schema.install_schema(cig)

    for story in stories:
        ingest.ingest_jira_story(
            cig, story["key"], story["title"],
            status=story["status"], points=story["points"], epic=story["epic"],
        )
    for pr in pulls:
        apply_pull_request(cig, pr, relink_stories=True)

    services = sorted({
        service_for_path(change["path"])
        for pr in pulls
        for change in pr.get("files") or []
        if change.get("path")
    })
    linked = sum(
        1
        for pr in pulls
        for key in story_keys_in_text(pr.get("title") or "", pr.get("body") or "")
        if any(s["key"] == key for s in stories)
    )
    skipped = [
        f"PR #{pr['number']} cites {key} (not in Jira)"
        for pr in pulls
        for key in story_keys_in_text(pr.get("title") or "", pr.get("body") or "")
        if not any(s["key"] == key for s in stories)
    ]
    return {
        "github_prs": len(pulls),
        "jira_stories": len(stories),
        "services": services,
        "story_links": linked,
        "unmatched_jira_citations": skipped,
        "prs": [
            {
                "number": pr["number"],
                "title": pr["title"],
                "files": [f["path"] for f in pr.get("files") or []],
                "jira": story_keys_in_text(pr.get("title") or "", pr.get("body") or ""),
            }
            for pr in pulls
        ],
        "stories": stories,
    }
