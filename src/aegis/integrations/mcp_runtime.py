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


def _cfg(name: str, default: str | None = None) -> str:
    getter = getattr(config, "get", None)
    if callable(getter):
        val = getter(name, default)
    else:
        val = getattr(config, name, None) or os.getenv(name, default)
    return (val or "").strip()

log = logging.getLogger(__name__)

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


def github_mcp_command() -> tuple[str, list[str], dict[str, str]]:
    cmd = _cfg("MCP_GITHUB_COMMAND", "npx") or "npx"
    package = _cfg("MCP_GITHUB_PACKAGE", "@modelcontextprotocol/server-github") or (
        "@modelcontextprotocol/server-github"
    )
    args_raw = _cfg("MCP_GITHUB_ARGS")
    if args_raw:
        args = args_raw.split()
    else:
        args = ["-y", package]
    token = _cfg("GITHUB_TOKEN")
    env = {"GITHUB_PERSONAL_ACCESS_TOKEN": token}
    return cmd, args, env


def jira_mcp_command() -> tuple[str, list[str], dict[str, str]]:
    cmd = _cfg("MCP_JIRA_COMMAND", "npx") or "npx"
    package = _cfg("MCP_JIRA_PACKAGE", "@aashari/mcp-server-atlassian-jira") or (
        "@aashari/mcp-server-atlassian-jira"
    )
    args_raw = _cfg("MCP_JIRA_ARGS")
    if args_raw:
        args = args_raw.split()
    else:
        args = ["-y", package]

    base = _cfg("JIRA_BASE_URL").rstrip("/")
    site = (
        base.replace("https://", "")
        .replace("http://", "")
        .replace(".atlassian.net", "")
        .strip("/")
    )
    env = {
        "ATLASSIAN_SITE_NAME": site,
        "ATLASSIAN_USER_EMAIL": _cfg("JIRA_EMAIL"),
        "ATLASSIAN_API_TOKEN": _cfg("JIRA_API_TOKEN"),
    }
    return cmd, args, env


def _mask_secret(value: str) -> str:
    if not value:
        return "not set"
    if len(value) <= 8:
        return f"set ({len(value)} chars)"
    return f"set ({len(value)} chars, {value[:4]}…{value[-4:]})"


def github_mcp_details() -> dict[str, Any]:
    """Current GitHub MCP spawn config for the Infrastructure page (no secrets)."""
    cmd, args, env = github_mcp_command()
    token = env.get("GITHUB_PERSONAL_ACCESS_TOKEN") or ""
    return {
        "kind": "GitHub",
        "transport": "stdio / MCP",
        "command": cmd,
        "args": " ".join(args),
        "spawn": f"{cmd} {' '.join(args)}".strip(),
        "package": _cfg("MCP_GITHUB_PACKAGE", "@modelcontextprotocol/server-github")
        or "@modelcontextprotocol/server-github",
        "env_injected": "GITHUB_PERSONAL_ACCESS_TOKEN ← GITHUB_TOKEN",
        "token": _mask_secret(token),
        "token_set": bool(token),
        "owner": _cfg("GITHUB_REPO_OWNER"),
        "repo": _cfg("GITHUB_REPO_NAME"),
        "full_name": "/".join(
            p for p in (_cfg("GITHUB_REPO_OWNER"), _cfg("GITHUB_REPO_NAME")) if p
        ),
        "source": _cfg("GITHUB_SOURCE", "auto") or "auto",
        "pr_map": _cfg("GITHUB_PR_MAP"),
    }


def jira_mcp_details() -> dict[str, Any]:
    """Current Jira MCP spawn config for the Infrastructure page (no secrets)."""
    cmd, args, env = jira_mcp_command()
    token = env.get("ATLASSIAN_API_TOKEN") or ""
    return {
        "kind": "Jira",
        "transport": "stdio / MCP",
        "command": cmd,
        "args": " ".join(args),
        "spawn": f"{cmd} {' '.join(args)}".strip(),
        "package": _cfg("MCP_JIRA_PACKAGE", "@aashari/mcp-server-atlassian-jira")
        or "@aashari/mcp-server-atlassian-jira",
        "env_injected": "ATLASSIAN_SITE_NAME / USER_EMAIL / API_TOKEN",
        "token": _mask_secret(token),
        "token_set": bool(token),
        "site": env.get("ATLASSIAN_SITE_NAME") or "",
        "email": env.get("ATLASSIAN_USER_EMAIL") or _cfg("JIRA_EMAIL"),
        "base_url": _cfg("JIRA_BASE_URL"),
        "project_key": _cfg("JIRA_PROJECT_KEY", "AEG") or "AEG",
        "project_name": _cfg("JIRA_PROJECT_NAME", "Project AEGIS") or "Project AEGIS",
        "source": _cfg("JIRA_SOURCE", "local") or "local",
    }


def call_github_tool(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    cmd, args, env = github_mcp_command()
    if not env.get("GITHUB_PERSONAL_ACCESS_TOKEN"):
        raise McpError("GITHUB_TOKEN missing for GitHub MCP server")
    return call_mcp_tool(
        command=cmd, args=args, env=env, tool=tool, arguments=arguments
    )


def call_jira_tool(tool: str, arguments: dict[str, Any] | None = None) -> Any:
    cmd, args, env = jira_mcp_command()
    if not env.get("ATLASSIAN_API_TOKEN") or not env.get("ATLASSIAN_USER_EMAIL"):
        raise McpError("Jira MCP needs JIRA_EMAIL and JIRA_API_TOKEN in .env")
    if not env.get("ATLASSIAN_SITE_NAME"):
        raise McpError("Jira MCP needs JIRA_BASE_URL (site name) in .env")
    return call_mcp_tool(
        command=cmd, args=args, env=env, tool=tool, arguments=arguments
    )
