"""Infrastructure page: GitHub / Jira MCP connection cards and editors."""

from __future__ import annotations

from html import escape as html_escape

import streamlit as st

from aegis import config
from aegis.integrations.github_client import (
    connection_status as github_connection_status,
    github_configured,
)
from aegis.integrations.jira_client import (
    connection_status as jira_connection_status,
    jira_configured,
)
from aegis.integrations.mcp_runtime import (
    GITHUB_MCP_PACKAGE,
    JIRA_MCP_PACKAGE,
    github_mcp_details,
    jira_mcp_details,
)


def mcp_probe_state(status: dict | None, configured: bool) -> tuple[str, str]:
    if status and status.get("ok"):
        return "ok", "Connected"
    if status and status.get("configured") and not status.get("ok"):
        return "bad", "Failed"
    if configured:
        return "warn", "Ready"
    return "warn", "Not set"


def conn_card_html(
    *,
    kind: str,
    glyph: str,
    glyph_class: str,
    headline: str,
    facts: list[tuple[str, str]],
    spawn: str,
    variant: str,
    pill: str,
    error: str | None = None,
) -> str:
    fact_html = "".join(
        f'<div class="conn-fact"><div class="k">{html_escape(k)}</div>'
        f'<div class="v">{html_escape(v)}</div></div>'
        for k, v in facts
    )
    err = f'<div class="conn-err">{html_escape(error)}</div>' if error else ""
    return (
        f'<div class="conn-card {variant}">'
        f'<div class="conn-head">'
        f'<div class="conn-glyph {glyph_class}">{html_escape(glyph)}</div>'
        f'<div><div class="conn-name">{html_escape(kind)}</div>'
        f'<div class="conn-via">MCP stdio · no in-app REST</div></div>'
        f'<span class="conn-pill {variant}">{html_escape(pill)}</span></div>'
        f'<div class="conn-headline">{html_escape(headline or "Not configured")}</div>'
        f'<div class="conn-facts">{fact_html}</div>'
        f'<div class="term">{html_escape(spawn or "—")}</div>{err}</div>'
    )


def _cfg(key: str, default: str = "") -> str:
    return config.setting(key, default) or default


def _option_index(value: str | None, options: list[str], fallback: int = 0) -> int:
    current = (value or "").lower()
    return options.index(current) if current in options else fallback


def _probe_error(status: dict | None) -> str | None:
    if status and not status.get("ok") and not status.get("skipped"):
        return str(status.get("error") or "Probe failed")[:180]
    return None


def _headline(
    status: dict | None,
    *,
    live: list[str],
    fallback: list[str],
    placeholder: str,
) -> str:
    values = live if status and status.get("ok") else fallback
    for value in values:
        if value:
            return value
    return placeholder


def _save(session_key: str, updates: dict[str, str]) -> None:
    saved = config.apply_updates(updates)
    st.session_state[session_key] = None
    st.success("Saved · " + ", ".join(saved) if saved else "Nothing to save")
    st.rerun()


def _advanced_server_fields(prefix: str, command_key: str, package_key: str, args_key: str, default_pkg: str) -> tuple[str, str, str]:
    st.caption("Advanced MCP server")
    cmd = st.text_input("Command", value=_cfg(command_key, "npx") or "npx", key=f"{prefix}_cmd")
    pkg = st.text_input("Package", value=_cfg(package_key, default_pkg) or default_pkg, key=f"{prefix}_pkg")
    args = st.text_input(
        "Args override",
        value=_cfg(args_key),
        placeholder="-y <package>",
        key=f"{prefix}_args",
    )
    return cmd, pkg, args


def render_mcp_panel() -> None:
    """Full-width GitHub + Jira MCP cards, test actions, and editors."""
    if (config.setting("NEO4J_PASSWORD") or "").strip() in {"", "changeme"}:
        st.warning(
            "Neo4j is using the default password. Set NEO4J_PASSWORD in .env "
            "to a strong value before exposing this app beyond localhost."
        )
    gh_details = github_mcp_details()
    jira_details = jira_mcp_details()
    gh_status = st.session_state.get("github_mcp_status")
    jira_status = st.session_state.get("jira_mcp_status")
    gh_var, gh_pill = mcp_probe_state(gh_status, github_configured())
    jira_var, jira_pill = mcp_probe_state(jira_status, jira_configured())

    st.markdown('<div class="kicker">Integrations · MCP</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title">GitHub &amp; Jira connections</div>'
        '<div style="color:var(--muted);font-size:13.5px;margin:-4px 0 14px">'
        "AEGIS talks to GitHub and Jira only through MCP. Credentials stay in "
        "<code>.env</code> and are injected into the server process — never into REST clients. "
        "Graph analysis still works if a connection is off.</div>",
        unsafe_allow_html=True,
    )

    mcp_l, mcp_r = st.columns(2, gap="large")
    with mcp_l:
        st.markdown(
            conn_card_html(
                kind="GitHub",
                glyph="GH",
                glyph_class="gh",
                headline=_headline(
                    gh_status,
                    live=[(gh_status or {}).get("full_name") or ""],
                    fallback=[gh_details.get("full_name") or ""],
                    placeholder="Connect a GitHub repo",
                ),
                facts=[
                    ("Token", gh_details.get("token") or "not set"),
                    ("Source", gh_details.get("source") or "auto"),
                    ("PR map", gh_details.get("pr_map") or "none"),
                    ("Package", gh_details.get("package") or "—"),
                ],
                spawn=gh_details.get("spawn") or "",
                variant=gh_var,
                pill=gh_pill,
                error=_probe_error(gh_status),
            ),
            unsafe_allow_html=True,
        )
        if st.button(
            "Test GitHub connection",
            disabled=not github_configured(),
            width="stretch",
            help="Spawns the GitHub MCP server with your token and probes the repo.",
        ):
            with st.spinner("Talking to GitHub MCP…"):
                st.session_state.github_mcp_status = github_connection_status()
            st.rerun()
        with st.expander("Edit GitHub connection", expanded=not github_configured()):
            with st.form("github_mcp_config"):
                g1, g2 = st.columns(2)
                with g1:
                    gh_owner = st.text_input("Owner", value=_cfg("GITHUB_REPO_OWNER"))
                with g2:
                    gh_repo = st.text_input("Repository", value=_cfg("GITHUB_REPO_NAME"))
                gh_map = st.text_input(
                    "CIG → GitHub PR map",
                    value=_cfg("GITHUB_PR_MAP"),
                    placeholder="482:1, 500:2",
                )
                gh_opts = ["auto", "mcp", "fixture"]
                gh_source = st.selectbox(
                    "When to use MCP",
                    gh_opts,
                    index=_option_index(_cfg("GITHUB_SOURCE", "auto"), gh_opts),
                )
                gh_token = st.text_input(
                    "Personal access token",
                    type="password",
                    value="",
                    placeholder="••••  leave blank to keep current",
                )
                gh_cmd, gh_pkg, gh_args = _advanced_server_fields(
                    "gh",
                    "MCP_GITHUB_COMMAND",
                    "MCP_GITHUB_PACKAGE",
                    "MCP_GITHUB_ARGS",
                    GITHUB_MCP_PACKAGE,
                )
                if st.form_submit_button("Save GitHub", type="primary"):
                    if gh_token:
                        gh_level, gh_hint = config.github_token_quality(gh_token)
                        if gh_level == "classic":
                            st.warning(
                                "Classic PAT detected — consider a fine-grained token "
                                "scoped to Contents/Metadata/Pull requests/Issues."
                            )
                        elif gh_level == "invalid":
                            st.error("That GitHub token looks invalid. Double-check it.")
                    _save(
                        "github_mcp_status",
                        {
                            "GITHUB_REPO_OWNER": gh_owner,
                            "GITHUB_REPO_NAME": gh_repo,
                            "GITHUB_SOURCE": gh_source,
                            "GITHUB_PR_MAP": gh_map,
                            "MCP_GITHUB_COMMAND": gh_cmd,
                            "MCP_GITHUB_PACKAGE": gh_pkg,
                            "MCP_GITHUB_ARGS": gh_args,
                            "GITHUB_TOKEN": gh_token,
                        },
                    )

    with mcp_r:
        st.markdown(
            conn_card_html(
                kind="Jira",
                glyph="JI",
                glyph_class="jira",
                headline=_headline(
                    jira_status,
                    live=[
                        (jira_status or {}).get("project_name") or "",
                        (jira_status or {}).get("site") or "",
                    ],
                    fallback=[
                        jira_details.get("base_url") or "",
                        jira_details.get("site") or "",
                    ],
                    placeholder="Connect a Jira site",
                ),
                facts=[
                    ("Token", jira_details.get("token") or "not set"),
                    ("Source", jira_details.get("source") or "local"),
                    ("Project", jira_details.get("project_key") or "—"),
                    ("Email", jira_details.get("email") or "not set"),
                ],
                spawn=jira_details.get("spawn") or "",
                variant=jira_var,
                pill=jira_pill,
                error=_probe_error(jira_status),
            ),
            unsafe_allow_html=True,
        )
        if st.button(
            "Test Jira connection",
            disabled=not jira_configured(),
            width="stretch",
            help="Spawns the Jira MCP server and checks the site + project.",
        ):
            with st.spinner("Talking to Jira MCP…"):
                st.session_state.jira_mcp_status = jira_connection_status()
            st.rerun()
        jira_opts = ["mcp", "cloud", "local"]
        with st.expander("Edit Jira connection", expanded=not jira_configured()):
            with st.form("jira_mcp_config"):
                jira_url = st.text_input(
                    "Site URL",
                    value=_cfg("JIRA_BASE_URL"),
                    placeholder="https://your-site.atlassian.net",
                )
                j1, j2 = st.columns(2)
                with j1:
                    jira_email = st.text_input("Email", value=_cfg("JIRA_EMAIL"))
                with j2:
                    jira_key = st.text_input("Project key", value=_cfg("JIRA_PROJECT_KEY", "AEG") or "AEG")
                jira_name = st.text_input(
                    "Project name",
                    value=_cfg("JIRA_PROJECT_NAME", "Project AEGIS") or "Project AEGIS",
                )
                jira_source = st.selectbox(
                    "When to use MCP",
                    jira_opts,
                    index=_option_index(_cfg("JIRA_SOURCE", "local"), jira_opts, fallback=2),
                )
                jira_token = st.text_input(
                    "API token",
                    type="password",
                    value="",
                    placeholder="••••  leave blank to keep current",
                )
                jira_cmd, jira_pkg, jira_args = _advanced_server_fields(
                    "jira",
                    "MCP_JIRA_COMMAND",
                    "MCP_JIRA_PACKAGE",
                    "MCP_JIRA_ARGS",
                    JIRA_MCP_PACKAGE,
                )
                if st.form_submit_button("Save Jira", type="primary"):
                    if jira_token:
                        jira_level, _jhint = config.jira_token_quality(jira_token)
                        if jira_level == "invalid":
                            st.error("That Jira API token looks invalid. Double-check it.")
                    _save(
                        "jira_mcp_status",
                        {
                            "JIRA_BASE_URL": jira_url,
                            "JIRA_EMAIL": jira_email,
                            "JIRA_PROJECT_KEY": jira_key,
                            "JIRA_PROJECT_NAME": jira_name,
                            "JIRA_SOURCE": jira_source,
                            "MCP_JIRA_COMMAND": jira_cmd,
                            "MCP_JIRA_PACKAGE": jira_pkg,
                            "MCP_JIRA_ARGS": jira_args,
                            "JIRA_API_TOKEN": jira_token,
                        },
                    )
