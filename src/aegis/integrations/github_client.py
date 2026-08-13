"""GitHub integration via MCP only (no in-app REST).

Uses `@modelcontextprotocol/server-github` tools for live access.
Infrastructure page only needs connection_status(); other methods are
kept so later PR sync can reuse this client without changing analysis.
"""

from __future__ import annotations

from typing import Any

import os

from aegis import config
from aegis.integrations.mcp_runtime import McpError, call_github_tool


class GitHubError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _cfg(name: str, default: str | None = None) -> str:
    getter = getattr(config, "get", None)
    if callable(getter):
        val = getter(name, default)
    else:
        val = getattr(config, name, None) or os.getenv(name, default)
    return (val or "").strip()


def github_configured() -> bool:
    return bool(_cfg("GITHUB_TOKEN") and _cfg("GITHUB_REPO_OWNER") and _cfg("GITHUB_REPO_NAME"))


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
        self.token = token or _cfg("GITHUB_TOKEN")
        self.owner = owner or _cfg("GITHUB_REPO_OWNER")
        self.repo = repo or _cfg("GITHUB_REPO_NAME")
        if not self.token or not self.owner or not self.repo:
            raise GitHubError(
                "Missing GitHub config. Set GITHUB_TOKEN, GITHUB_REPO_OWNER, "
                "GITHUB_REPO_NAME in .env (token is passed to GitHub MCP server only)."
            )

    def myself(self) -> dict:
        data = _mcp(
            "search_repositories",
            {"query": f"user:{self.owner}", "perPage": 1},
        )
        items = []
        if isinstance(data, dict):
            items = data.get("items") or []
        return {"login": self.owner, "mcp": True, "via": "github-mcp", "sample_repos": len(items)}

    def get_repo(self) -> dict:
        data = _mcp(
            "search_repositories",
            {"query": f"repo:{self.owner}/{self.repo}", "perPage": 1},
        )
        if isinstance(data, dict):
            items = data.get("items") or []
            if items:
                return items[0]
            return {
                "full_name": f"{self.owner}/{self.repo}",
                "html_url": f"https://github.com/{self.owner}/{self.repo}",
                "private": None,
                "default_branch": "main",
                "name": self.repo,
                "owner": {"login": self.owner},
            }
        if isinstance(data, list) and data:
            return data[0]
        return {
            "full_name": f"{self.owner}/{self.repo}",
            "html_url": f"https://github.com/{self.owner}/{self.repo}",
        }

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
        return {
            "configured": False,
            "ok": False,
            "transport": "mcp",
            "error": "Set GITHUB_TOKEN, GITHUB_REPO_OWNER, GITHUB_REPO_NAME in .env",
        }
    try:
        client = GitHubClient()
        me = client.myself()
        repo = client.get_repo()
        return {
            "configured": True,
            "ok": True,
            "transport": "mcp",
            "mcp_server": _cfg("MCP_GITHUB_PACKAGE", "@modelcontextprotocol/server-github")
            or "@modelcontextprotocol/server-github",
            "login": me.get("login"),
            "owner": client.owner,
            "repo": client.repo,
            "full_name": repo.get("full_name") or f"{client.owner}/{client.repo}",
            "html_url": repo.get("html_url"),
            "private": repo.get("private"),
            "default_branch": repo.get("default_branch"),
        }
    except GitHubError as exc:
        return {
            "configured": True,
            "ok": False,
            "transport": "mcp",
            "error": str(exc),
            "status": exc.status,
            "body": exc.body,
        }
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "transport": "mcp",
            "error": str(exc),
        }
