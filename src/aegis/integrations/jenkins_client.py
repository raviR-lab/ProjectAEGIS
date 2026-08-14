"""Jenkins integration via MCP only (no in-app REST).

Uses `@kud/mcp-jenkins` tools for live access. Infrastructure page only
needs connection_status(); request() is kept so later pipeline sync can
reuse this client without changing analysis.
"""

from __future__ import annotations

from typing import Any

from aegis import config
from aegis.integrations.mcp_runtime import (
    JENKINS_MCP_PACKAGE,
    McpError,
    call_jenkins_tool,
    mcp_status_failed,
    mcp_status_unconfigured,
)


class JenkinsError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def jenkins_configured() -> bool:
    return bool(
        config.setting("JENKINS_URL")
        and config.setting("JENKINS_USER")
        and config.setting("JENKINS_API_TOKEN")
    )


def _mcp(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    try:
        return call_jenkins_tool(tool, arguments)
    except McpError as exc:
        raise JenkinsError(str(exc), body=exc.body) from exc


class JenkinsClient:
    """MCP-backed Jenkins client."""

    def __init__(
        self,
        *,
        url: str | None = None,
        user: str | None = None,
        token: str | None = None,
        **_ignored: Any,
    ) -> None:
        self.url = (url or config.setting("JENKINS_URL")).rstrip("/")
        self.user = user or config.setting("JENKINS_USER")
        self.token = token or config.setting("JENKINS_API_TOKEN")
        if not self.url or not self.user or not self.token:
            raise JenkinsError(
                "Missing Jenkins config. Set JENKINS_URL, JENKINS_USER, "
                "JENKINS_API_TOKEN in .env (token is passed to Jenkins MCP server only)."
            )

    def get_all_items(self) -> list[dict]:
        data = _mcp("get_all_items")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            items = data.get("jobs") or data.get("items") or []
            return items if isinstance(items, list) else [items]
        return []


def connection_status() -> dict[str, Any]:
    if not jenkins_configured():
        return mcp_status_unconfigured(
            "Set JENKINS_URL, JENKINS_USER, JENKINS_API_TOKEN in .env"
        )
    try:
        client = JenkinsClient()
        jobs = client.get_all_items()
        return {
            "configured": True,
            "ok": True,
            "transport": "mcp",
            "mcp_server": config.setting("MCP_JENKINS_PACKAGE", JENKINS_MCP_PACKAGE)
            or JENKINS_MCP_PACKAGE,
            "base_url": client.url,
            "user": client.user,
            "job_count": len(jobs),
            "sample_jobs": [j.get("name") or j.get("fullname") for j in jobs[:5]],
        }
    except Exception as exc:
        return mcp_status_failed(exc)