"""Jira Cloud integration via MCP only (no in-app REST).

Uses `@aashari/mcp-server-atlassian-jira` tools:
jira_get / jira_post / jira_put / jira_patch / jira_delete.

Infrastructure page only needs connection_status(); request() is kept
so later story sync can reuse this client without changing analysis.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from aegis import config
from aegis.integrations.mcp_runtime import McpError, call_jira_tool


class JiraError(RuntimeError):
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


def jira_configured() -> bool:
    return bool(_cfg("JIRA_BASE_URL") and _cfg("JIRA_EMAIL") and _cfg("JIRA_API_TOKEN"))


def project_key() -> str:
    return (_cfg("JIRA_PROJECT_KEY", "AEG") or "AEG").upper()


def _require_settings() -> tuple[str, str, str]:
    base = _cfg("JIRA_BASE_URL").rstrip("/")
    email = _cfg("JIRA_EMAIL")
    token = _cfg("JIRA_API_TOKEN")
    missing = [
        name
        for name, val in (
            ("JIRA_BASE_URL", base),
            ("JIRA_EMAIL", email),
            ("JIRA_API_TOKEN", token),
        )
        if not val
    ]
    if missing:
        raise JiraError(
            "Missing Jira credentials in .env: " + ", ".join(missing)
            + ". Credentials are injected only into the Jira MCP server."
        )
    if "atlassian.net" not in base and not base.startswith("http"):
        base = f"https://{base}"
    return base, email, token


def _query_params(query: dict | None) -> dict[str, str] | None:
    if not query:
        return None
    out: dict[str, str] = {}
    for k, v in query.items():
        if v is None:
            continue
        if isinstance(v, (list, tuple)):
            out[str(k)] = ",".join(str(x) for x in v)
        else:
            out[str(k)] = str(v)
    return out or None


@dataclass
class JiraClient:
    """MCP-backed Jira client."""

    base_url: str
    email: str
    api_token: str
    timeout: float = 30.0

    @classmethod
    def from_config(cls) -> "JiraClient":
        base, email, token = _require_settings()
        return cls(base_url=base, email=email, api_token=token)

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | list | None = None,
        query: dict | None = None,
    ) -> Any:
        method_u = method.upper()
        tool = {
            "GET": "jira_get",
            "POST": "jira_post",
            "PUT": "jira_put",
            "PATCH": "jira_patch",
            "DELETE": "jira_delete",
        }.get(method_u)
        if not tool:
            raise JiraError(f"Unsupported method for Jira MCP: {method}")

        if not path.startswith("/"):
            path = "/" + path

        args: dict[str, Any] = {
            "path": path,
            "outputFormat": "json",
        }
        qp = _query_params(query)
        if qp:
            args["queryParams"] = qp
        if body is not None and method_u in {"POST", "PUT", "PATCH"}:
            args["body"] = body

        try:
            data = call_jira_tool(tool, args)
        except McpError as exc:
            msg = str(exc)
            body_txt = exc.body or ""
            status = None
            if "404" in body_txt or "Not Found" in body_txt:
                status = 404
            elif "401" in body_txt or "Unauthorized" in body_txt:
                status = 401
            elif "403" in body_txt or "Forbidden" in body_txt:
                status = 403
            raise JiraError(
                f"Jira MCP {method_u} {path} failed: {msg}",
                status=status,
                body=body_txt,
            ) from exc

        if isinstance(data, str):
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return data

    def myself(self) -> dict:
        return self.request("GET", "/rest/api/3/myself")

    def get_project(self, key: str) -> dict | None:
        try:
            return self.request("GET", f"/rest/api/3/project/{quote(key)}")
        except JiraError as exc:
            if exc.status == 404:
                return None
            raise


def connection_status() -> dict[str, Any]:
    if not jira_configured():
        return {
            "configured": False,
            "ok": False,
            "transport": "mcp",
            "error": "Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env",
        }
    try:
        client = JiraClient.from_config()
        me = client.myself()
        proj = client.get_project(project_key())
        return {
            "configured": True,
            "ok": True,
            "transport": "mcp",
            "mcp_server": _cfg("MCP_JIRA_PACKAGE", "@aashari/mcp-server-atlassian-jira")
            or "@aashari/mcp-server-atlassian-jira",
            "display_name": me.get("displayName"),
            "email": me.get("emailAddress") or _cfg("JIRA_EMAIL"),
            "account_id": me.get("accountId"),
            "site": _cfg("JIRA_BASE_URL"),
            "project_key": project_key(),
            "project_exists": proj is not None,
            "project_name": (proj or {}).get("name"),
        }
    except JiraError as exc:
        return {
            "configured": True,
            "ok": False,
            "transport": "mcp",
            "error": str(exc),
            "body": exc.body,
            "status": exc.status,
        }
    except Exception as exc:
        return {
            "configured": True,
            "ok": False,
            "transport": "mcp",
            "error": str(exc),
        }
