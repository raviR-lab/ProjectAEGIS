"""MCP stdio client runtime for Project AEGIS.

Live GitHub and Jira access goes *only* through MCP tool servers
(no in-app HTTP REST clients for those systems).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from typing import Any

from aegis import config

log = logging.getLogger(__name__)

GITHUB_MCP_PACKAGE = "@modelcontextprotocol/server-github"
JIRA_MCP_PACKAGE = "@aashari/mcp-server-atlassian-jira"

DEFAULT_TIMEOUT = 45.0


class McpError(RuntimeError):
    def __init__(self, message: str, *, body: str | None = None):
        super().__init__(message)
        self.body = body


def _run_async(coro):
    """Run a coroutine from sync code (Streamlit / CLI)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


def parse_tool_payload(result: Any) -> Any:
    """Normalize MCP CallToolResult content into JSON-ish Python values."""
    if result is None:
        return None
    if getattr(result, "isError", False):
        texts = []
        for block in getattr(result, "content", None) or []:
            texts.append(getattr(block, "text", None) or str(block))
        raise McpError("MCP tool error", body="\n".join(texts)[:2000])

    texts: list[str] = []
    for block in getattr(result, "content", None) or []:
        t = getattr(block, "text", None)
        if t is not None:
            texts.append(t)
    if not texts:
        structured = getattr(result, "structuredContent", None) or getattr(
            result, "structured_content", None
        )
        if structured is not None:
            return structured
        return None

    raw = "\n".join(texts).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        if "```" in raw:
            parts = raw.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                try:
                    return json.loads(part)
                except json.JSONDecodeError:
                    continue
        return raw


async def _call_tool_async(
    *,
    command: str,
    args: list[str],
    env: dict[str, str],
    tool: str,
    arguments: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    binary = command.split()[0] if command else ""
    if not shutil.which(binary) and not shutil.which(command):
        raise McpError(
            f"MCP command not found: {command}. "
            "Install Node.js (for npx) in the AEGIS runtime."
        )

    merged_env = {**os.environ, **{k: str(v) for k, v in env.items() if v is not None}}
    params = StdioServerParameters(command=command, args=args, env=merged_env)

    async def _inner():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool, arguments or {})
                return parse_tool_payload(result)

    try:
        return await asyncio.wait_for(_inner(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        raise McpError(
            f"MCP tool '{tool}' timed out after {timeout:.0f}s"
        ) from exc


def call_mcp_tool(
    *,
    command: str,
    args: list[str],
    env: dict[str, str],
    tool: str,
    arguments: dict[str, Any] | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    return _run_async(
        _call_tool_async(
            command=command,
            args=args,
            env=env,
            tool=tool,
            arguments=arguments,
            timeout=timeout,
        )
    )


def _stdio_launch(command_key: str, package_key: str, args_key: str, default_package: str) -> tuple[str, list[str], str]:
    cmd = config.setting(command_key, "npx") or "npx"
    package = config.setting(package_key, default_package) or default_package
    args_raw = config.setting(args_key)
    args = args_raw.split() if args_raw else ["-y", package]
    return cmd, args, package


def _atlassian_site_name(base_url: str) -> str:
    return (
        (base_url or "")
        .rstrip("/")
        .replace("https://", "")
        .replace("http://", "")
        .replace(".atlassian.net", "")
        .strip("/")
    )


def github_mcp_command() -> tuple[str, list[str], dict[str, str], str]:
    cmd, args, package = _stdio_launch(
        "MCP_GITHUB_COMMAND", "MCP_GITHUB_PACKAGE", "MCP_GITHUB_ARGS", GITHUB_MCP_PACKAGE
    )
    env = {"GITHUB_PERSONAL_ACCESS_TOKEN": config.setting("GITHUB_TOKEN")}
    return cmd, args, env, package


def jira_mcp_command() -> tuple[str, list[str], dict[str, str], str]:
    cmd, args, package = _stdio_launch(
        "MCP_JIRA_COMMAND", "MCP_JIRA_PACKAGE", "MCP_JIRA_ARGS", JIRA_MCP_PACKAGE
    )
    env = {
        "ATLASSIAN_SITE_NAME": _atlassian_site_name(config.setting("JIRA_BASE_URL")),
        "ATLASSIAN_USER_EMAIL": config.setting("JIRA_EMAIL"),
        "ATLASSIAN_API_TOKEN": config.setting("JIRA_API_TOKEN"),
    }
    return cmd, args, env, package


def _mask_secret(value: str) -> str:
    if not value:
        return "not set"
    if len(value) <= 8:
        return f"set ({len(value)} chars)"
    return f"set ({len(value)} chars, {value[:4]}…{value[-4:]})"


def _spawn_details(cmd: str, args: list[str], package: str, token: str, extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "transport": "stdio / MCP",
        "command": cmd,
        "args": " ".join(args),
        "spawn": f"{cmd} {' '.join(args)}".strip(),
        "package": package,
        "token": _mask_secret(token),
        "token_set": bool(token),
        **extra,
    }


def github_mcp_details() -> dict[str, Any]:
    """Current GitHub MCP spawn config for the Infrastructure page (no secrets)."""
    cmd, args, env, package = github_mcp_command()
    owner = config.setting("GITHUB_REPO_OWNER")
    repo = config.setting("GITHUB_REPO_NAME")
    return _spawn_details(
        cmd,
        args,
        package,
        env.get("GITHUB_PERSONAL_ACCESS_TOKEN") or "",
        {
            "kind": "GitHub",
            "env_injected": "GITHUB_PERSONAL_ACCESS_TOKEN ← GITHUB_TOKEN",
            "owner": owner,
            "repo": repo,
            "full_name": "/".join(p for p in (owner, repo) if p),
            "source": config.setting("GITHUB_SOURCE", "auto") or "auto",
            "pr_map": config.setting("GITHUB_PR_MAP"),
        },
    )


def jira_mcp_details() -> dict[str, Any]:
    """Current Jira MCP spawn config for the Infrastructure page (no secrets)."""
    cmd, args, env, package = jira_mcp_command()
    return _spawn_details(
        cmd,
        args,
        package,
        env.get("ATLASSIAN_API_TOKEN") or "",
        {
            "kind": "Jira",
            "env_injected": "ATLASSIAN_SITE_NAME / USER_EMAIL / API_TOKEN",
            "site": env.get("ATLASSIAN_SITE_NAME") or "",
            "email": env.get("ATLASSIAN_USER_EMAIL") or config.setting("JIRA_EMAIL"),
            "base_url": config.setting("JIRA_BASE_URL"),
            "project_key": config.setting("JIRA_PROJECT_KEY", "AEG") or "AEG",
            "project_name": config.setting("JIRA_PROJECT_NAME", "Project AEGIS") or "Project AEGIS",
            "source": config.setting("JIRA_SOURCE", "local") or "local",
        },
    )


def call_github_tool(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    cmd, args, env, _package = github_mcp_command()
    if not env.get("GITHUB_PERSONAL_ACCESS_TOKEN"):
        raise McpError("GITHUB_TOKEN missing for GitHub MCP server")
    return call_mcp_tool(command=cmd, args=args, env=env, tool=tool, arguments=arguments)


def call_jira_tool(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    cmd, args, env, _package = jira_mcp_command()
    if not env.get("ATLASSIAN_API_TOKEN") or not env.get("ATLASSIAN_USER_EMAIL"):
        raise McpError("Jira MCP needs JIRA_EMAIL and JIRA_API_TOKEN in .env")
    if not env.get("ATLASSIAN_SITE_NAME"):
        raise McpError("Jira MCP needs JIRA_BASE_URL (site name) in .env")
    return call_mcp_tool(command=cmd, args=args, env=env, tool=tool, arguments=arguments)


def mcp_status_unconfigured(error: str) -> dict[str, Any]:
    return {"configured": False, "ok": False, "transport": "mcp", "error": error}


def mcp_status_failed(exc: BaseException) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "configured": True,
        "ok": False,
        "transport": "mcp",
        "error": str(exc),
    }
    status = getattr(exc, "status", None)
    body = getattr(exc, "body", None)
    if status is not None:
        payload["status"] = status
    if body is not None:
        payload["body"] = body
    return payload
