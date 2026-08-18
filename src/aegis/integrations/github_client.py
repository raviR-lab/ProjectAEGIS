"""GitHub integration via MCP only (no in-app REST).

Uses `@modelcontextprotocol/server-github` tools for live access.
Infrastructure page only needs connection_status(); other methods are
kept so later PR sync can reuse this client without changing analysis.
"""

from __future__ import annotations

from typing import Any

from aegis import config
from aegis.integrations.mcp_runtime import (
    GITHUB_MCP_PACKAGE,
    McpError,
    call_github_tool,
    call_github_tools,
    mcp_status_failed,
    mcp_status_unconfigured,
)


class GitHubError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def github_configured() -> bool:
    return bool(
        config.setting("GITHUB_TOKEN")
        and config.setting("GITHUB_REPO_OWNER")
        and config.setting("GITHUB_REPO_NAME")
    )


def _as_list(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("items", "files", "pulls", "data", "result"):
            val = data.get(key)
            if isinstance(val, list):
                return val
    return []


def _mcp(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    try:
        return call_github_tool(tool, arguments)
    except McpError as exc:
        raise GitHubError(str(exc), body=exc.body) from exc


class GitHubClient:
    """MCP-backed GitHub client. Interface matches the sibling AEGIS project."""

    def __init__(
        self,
        *,
        token: str | None = None,
        owner: str | None = None,
        repo: str | None = None,
        **_ignored: Any,
    ) -> None:
        self.token = token or config.setting("GITHUB_TOKEN")
        self.owner = owner or config.setting("GITHUB_REPO_OWNER")
        self.repo = repo or config.setting("GITHUB_REPO_NAME")
        if not self.token or not self.owner or not self.repo:
            raise GitHubError(
                "Missing GitHub config. Set GITHUB_TOKEN, GITHUB_REPO_OWNER, "
                "GITHUB_REPO_NAME in .env (token is passed to GitHub MCP server only)."
            )

    def _search_repos(self, query: str) -> Any:
        return _mcp("search_repositories", {"query": query, "perPage": 1})

    def myself(self) -> dict:
        data = self._search_repos(f"user:{self.owner}")
        items = data.get("items") or [] if isinstance(data, dict) else []
        return {"login": self.owner, "mcp": True, "via": "github-mcp", "sample_repos": len(items)}

    def get_repo(self) -> dict:
        data = self._search_repos(f"repo:{self.owner}/{self.repo}")
        stub = {
            "full_name": f"{self.owner}/{self.repo}",
            "html_url": f"https://github.com/{self.owner}/{self.repo}",
            "private": None,
            "default_branch": "main",
            "name": self.repo,
            "owner": {"login": self.owner},
        }
        if isinstance(data, dict):
            items = data.get("items") or []
            return items[0] if items else stub
        if isinstance(data, list) and data:
            return data[0]
        return stub

    def list_pull_requests(self, state: str = "open") -> list[dict]:
        data = _mcp(
            "list_pull_requests",
            {"owner": self.owner, "repo": self.repo, "state": state},
        )
        return _as_list(data)

    def get_pull_request(self, pull_number: int) -> dict:
        data = _mcp(
            "get_pull_request",
            {
                "owner": self.owner,
                "repo": self.repo,
                "pull_number": int(pull_number),
            },
        )
        return data if isinstance(data, dict) else {}

    def get_pull_request_files(self, pull_number: int) -> list[dict]:
        data = _mcp(
            "get_pull_request_files",
            {
                "owner": self.owner,
                "repo": self.repo,
                "pull_number": int(pull_number),
            },
        )
        return _as_list(data)

    def get_pull_request_bundle(self, pull_number: int) -> tuple[dict, list[dict]]:
        """PR metadata + files in a single MCP server spawn."""
        n = int(pull_number)
        args = {"owner": self.owner, "repo": self.repo, "pull_number": n}
        try:
            raw_pr, raw_files = call_github_tools(
                [("get_pull_request", args), ("get_pull_request_files", args)]
            )
        except McpError as exc:
            raise GitHubError(str(exc), body=exc.body) from exc
        pr = raw_pr if isinstance(raw_pr, dict) else {}
        return pr, _as_list(raw_files)

    def list_pull_requests_with_files(self, state: str = "all") -> list[tuple[dict, list[dict]]]:
        """List PRs, then fetch files for each, using two MCP spawns total."""
        stubs = self.list_pull_requests(state=state)
        numbers = []
        for raw in stubs:
            try:
                n = int(raw.get("number") or 0)
            except (TypeError, ValueError):
                n = 0
            if n:
                numbers.append(n)
        if not numbers:
            return []
        calls: list[tuple[str, dict]] = []
        for n in numbers:
            args = {"owner": self.owner, "repo": self.repo, "pull_number": n}
            calls.append(("get_pull_request", args))
            calls.append(("get_pull_request_files", args))
        try:
            results = call_github_tools(calls)
        except McpError as exc:
            raise GitHubError(str(exc), body=exc.body) from exc
        out = []
        for i, n in enumerate(numbers):
            raw_pr = results[2 * i] if 2 * i < len(results) else {}
            raw_files = results[2 * i + 1] if 2 * i + 1 < len(results) else []
            pr = raw_pr if isinstance(raw_pr, dict) else {"number": n}
            if not pr.get("number"):
                pr = {**pr, "number": n}
            out.append((pr, _as_list(raw_files)))
        return out

    def create_issue_comment(self, issue_number: int, body: str) -> dict:
        data = _mcp(
            "add_issue_comment",
            {
                "owner": self.owner,
                "repo": self.repo,
                "issue_number": int(issue_number),
                "body": body,
            },
        )
        return data if isinstance(data, dict) else {"body": body, "raw": data}

    def create_pull_review_comment_summary(self, number: int, body: str) -> dict:
        data = _mcp(
            "create_pull_request_review",
            {
                "owner": self.owner,
                "repo": self.repo,
                "pull_number": int(number),
                "body": body,
                "event": "COMMENT",
            },
        )
        return data if isinstance(data, dict) else {"body": body, "raw": data}


def connection_status() -> dict[str, Any]:
    if not github_configured():
        return mcp_status_unconfigured(
            "Set GITHUB_TOKEN, GITHUB_REPO_OWNER, GITHUB_REPO_NAME in .env"
        )
    try:
        client = GitHubClient()
        me = client.myself()
        repo = client.get_repo()
        return {
            "configured": True,
            "ok": True,
            "transport": "mcp",
            "mcp_server": config.setting("MCP_GITHUB_PACKAGE", GITHUB_MCP_PACKAGE)
            or GITHUB_MCP_PACKAGE,
            "login": me.get("login"),
            "owner": client.owner,
            "repo": client.repo,
            "full_name": repo.get("full_name") or f"{client.owner}/{client.repo}",
            "html_url": repo.get("html_url"),
            "private": repo.get("private"),
            "default_branch": repo.get("default_branch"),
        }
    except Exception as exc:
        return mcp_status_failed(exc)
