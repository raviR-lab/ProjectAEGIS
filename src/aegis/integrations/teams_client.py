"""Microsoft Teams integration via MCP only (no in-app REST).

Uses `@floriscornel/teams-mcp` tools. Authentication is a one-time
interactive OAuth login (`npx @floriscornel/teams-mcp authenticate`);
the server runs read-only by default.
"""

from __future__ import annotations

from typing import Any

from aegis import config
from aegis.integrations.mcp_runtime import (
    TEAMS_MCP_PACKAGE,
    McpError,
    call_teams_tool,
    mcp_status_failed,
    mcp_status_unconfigured,
)


class TeamsError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def teams_configured() -> bool:
    # Teams uses OAuth login instead of a PAT; treat "configured" as the
    # server being spawnable. Actual auth is verified by connection_status().
    return bool(config.setting("MCP_TEAMS_PACKAGE") or TEAMS_MCP_PACKAGE)


def _mcp(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    try:
        return call_teams_tool(tool, arguments)
    except McpError as exc:
        raise TeamsError(str(exc), body=exc.body) from exc


class TeamsClient:
    """MCP-backed Teams client."""

    def __init__(self, **_ignored: Any) -> None:
        self.read_only = (config.setting("TEAMS_MCP_READ_ONLY", "true") or "true").lower() != "false"

    def auth_status(self) -> dict:
        data = _mcp("auth_status")
        if isinstance(data, dict):
            return data
        return {"authenticated": bool(data), "raw": data}

    def get_current_user(self) -> dict:
        data = _mcp("get_current_user")
        if isinstance(data, dict):
            return data
        return {"raw": data}


def connection_status() -> dict[str, Any]:
    if not teams_configured():
        return mcp_status_unconfigured("Teams MCP package not configured")
    try:
        client = TeamsClient()
        auth = client.auth_status()
        authenticated = bool(
            (auth.get("authenticated") if isinstance(auth, dict) else auth)
            or (auth.get("status") if isinstance(auth, dict) else None)
        )
        user = {}
        if authenticated:
            try:
                user = client.get_current_user()
            except Exception:
                user = {}
        display = (
            user.get("displayName")
            or user.get("userPrincipalName")
            or user.get("name")
            if isinstance(user, dict)
            else None
        )
        return {
            "configured": True,
            "ok": authenticated,
            "transport": "mcp",
            "mcp_server": config.setting("MCP_TEAMS_PACKAGE", TEAMS_MCP_PACKAGE)
            or TEAMS_MCP_PACKAGE,
            "authenticated": authenticated,
            "read_only": client.read_only,
            "display_name": display,
            "auth_cmd": "npx @floriscornel/teams-mcp authenticate",
        }
    except Exception as exc:
        return mcp_status_failed(exc)