"""Infrastructure page: GitHub / Jira MCP connection cards and editors."""

from __future__ import annotations

from html import escape as html_escape
from urllib.parse import quote

import streamlit as st

from aegis import config
from aegis.integrations.github_client import (
    connection_status as github_connection_status,
    github_configured,
)
from aegis.integrations.jenkins_client import (
    connection_status as jenkins_connection_status,
    jenkins_configured,
)
from aegis.integrations.jira_client import (
    connection_status as jira_connection_status,
    jira_configured,
)
from aegis.integrations.mcp_runtime import (
    GITHUB_MCP_PACKAGE,
    JENKINS_MCP_PACKAGE,
    JIRA_MCP_PACKAGE,
    TEAMS_MCP_PACKAGE,
    github_mcp_details,
    jenkins_mcp_details,
    jira_mcp_details,
    teams_mcp_details,
)
from aegis.integrations.teams_client import (
    connection_status as teams_connection_status,
    teams_configured,
)

# Official brand marks (Simple Icons) as data-URI <img> so Streamlit keeps them.
def _brand_icon(path_d: str, *, fill: str = "#ffffff") -> str:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
        f'<path fill="{fill}" d="{path_d}"/></svg>'
    )
    return (
        f'<img class="conn-icon" alt="" width="22" height="22" '
        f'src="data:image/svg+xml,{quote(svg)}"/>'
    )


ICON_GITHUB = _brand_icon(
    "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577"
    " 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7"
    " 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07"
    " 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332"
    "-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005"
    "-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552"
    " 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0"
    " 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015"
    " 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"
)
ICON_JIRA = _brand_icon(
    "M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0"
    " 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215"
    " 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001"
    " 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A"
    "5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0Z"
)
ICON_JENKINS = _brand_icon(
    "M2.872 24h-.975a3.866 3.866 0 01-.07-.197c-.215-.666-.594-1.49-.692-2.154-.146"
    "-.984.78-1.039 1.374-1.465.915-.66 1.635-1.025 2.627-1.62.295-.179 1.182-.624"
    " 1.281-.829.201-.408-.345-.982-.49-1.3-.225-.507-.345-.937-.376-1.435-.824-.13"
    "-1.455-.627-1.844-1.185-.63-.925-1.066-2.635-.525-3.936.045-.103.254-.305.285"
    "-.463.06-.308-.105-.72-.12-1.048-.06-1.692.284-3.15 1.425-3.66.463-1.84 2.113"
    "-2.453 3.673-3.367.58-.342 1.224-.562 1.89-.807 2.372-.877 6.027-.712 7.994.783"
    ".836.633 2.176 1.97 2.656 2.939 1.262 2.555 1.17 6.825.287 9.934-.12.421-.29"
    " 1.032-.533 1.533-.168.35-.689 1.05-.625 1.36.064.314 1.19 1.17 1.432 1.395.434"
    ".422 1.26.975 1.324 1.5.07.557-.248 1.336-.41 1.875-.217.721-.436 1.441-.654"
    " 2.131H2.87zm11.104-3.54c-.545-.3-1.361-.622-2.065-.757-.87-.164-.78 1.188-.75"
    " 1.994.03.643.36 1.316.51 1.744.076.197.09.41.256.449.3.068 1.29-.326 1.575"
    "-.479.6-.328 1.064-.844 1.574-1.189.016-.17.016-.34.03-.508a2.648 2.648 0"
    " 00-1.095-.277c.314-.15.75-.15 1.035-.332l.016-.193c-.496-.03-.69-.254-1.021"
    "-.436zm7.454 2.935a17.78 17.78 0 00.465-1.752c.06-.287.215-.918.178-1.176-.059"
    "-.459-.684-.799-1.004-1.086-.584-.525-.95-.975-1.56-1.469-.249.375-.78.615-.983"
    ".914 1.447-.689 1.71 2.625 1.141 3.69.09.329.391.45.514.735l-.086.166h1.29c.013"
    " 0 .03 0 .044.014zm-6.634-.012c-.05-.074-.1-.135-.15-.209l-.301.195h.45zm2.77"
    " 0c.008-.209.018-.404.03-.598-.53.029-.825-.48-1.196-.527-.324-.045-.6.361-1.02"
    ".195-.095.105-.183.227-.284.316.154.18.295.375.424.584h.815c.014-.164.135-.285"
    ".3-.285.165 0 .284.121.284.27h.66zm2.116 0c-.314-.479-.947-.898-1.68-.555l-.03"
    ".541h1.71zm-8.51 0l-.104-.344c-.225-.72-.36-1.26-.405-1.68-.914-.436-1.875-.87"
    "-2.654-1.426-.15-.105-1.109-1.35-1.23-1.305-1.739.676-3.359 1.86-4.814 2.984"
    ".256.557.48 1.141.69 1.74h8.505zm8.265-2.113c-.029-.512-.164-1.56-.48-1.74-.66"
    "-.39-1.846.78-2.34.943.045.15.135.271.15.48.285-.074.645-.029.898.092-.299.03"
    "-.629.03-.824.164-.074.195.016.48-.029.764.69.197 1.5.303 2.385.332.164-.227"
    ".225-.645.211-1.082zm-4.08-.36c-.044.375.046.51.12.943 1.26.391 1.034-1.74"
    "-.135-.959zM8.76 19.5c-.45.457 1.27 1.082 1.814 1.115 0-.29.165-.564.135-.77"
    "-.65-.118-1.502-.042-1.945-.347zm5.565.215c0 .043-.061.03-.068.064.58.451"
    " 1.014.545 1.802.51.354-.262.67-.563 1.043-.807-.855.074-1.931.607-2.774.23zm"
    "3.42-17.726c-1.606-.906-4.35-1.591-6.076-.731-1.38.692-3.27 1.84-3.899 3.292"
    ".6 1.402-.166 2.686-.226 4.109-.018.757.36 1.42.391 2.242-.2.338-.825.38-1.26"
    ".356-.146-.729-.4-1.549-1.155-1.63-1.064-.116-1.845.764-1.89 1.683-.06 1.08"
    ".833 2.864 2.085 2.745.488-.046.608-.54 1.139-.54.285.57-.445.75-.523 1.154"
    "-.016.105.06.511.104.705.233.944.744 2.16 1.245 2.88.635.9 1.884 1.051 3.229"
    " 1.141.24-.525 1.125-.48 1.706-.346-.691-.27-1.336-.945-1.875-1.529-.615-.676"
    "-1.23-1.41-1.261-2.28 1.155 1.604 2.1 3 4.2 3.704 1.59.525 3.45-.254 4.664"
    "-1.109.51-.359.811-.93 1.17-1.439 1.35-1.936 1.98-4.71 1.846-7.394-.06-1.111"
    "-.06-2.221-.436-2.955-.389-.781-1.695-1.471-2.475-.781-.15-.764.63-1.23 1.545"
    "-.96-.66-.854-1.336-1.858-2.266-2.384zM13.58 14.896c.615 1.544 2.724 1.363"
    " 4.505 1.323-.084.194-.256.435-.465.515-.57.232-2.145.408-2.937-.012-.506-.27"
    "-.824-.873-1.102-1.227-.137-.172-.795-.608-.012-.609zm.164-.87c.893.464 2.52"
    ".517 3.731.48.066.267.066.593.068.913-1.55.08-3.386-.304-3.794-1.395h-.005zm"
    "6.675-.586c-.473.9-1.145 1.897-2.539 1.928-.023-.284-.045-.735 0-.904 1.064"
    "-.103 1.727-.646 2.543-1.017zm-.649-.667c-1.02.66-2.154 1.375-3.824 1.21-.351"
    "-.31-.485-1-.14-1.458.181.313.06.885.57.97.944.165 2.038-.579 2.73-.84.42"
    "-.713-.046-.976-.42-1.433-.782-.93-1.83-2.1-1.802-3.51.314-.224.346.346.391"
    ".45.404.96 1.424 2.175 2.174 3 .18.21.48.39.51.524.092.39-.254.854-.209"
    " 1.11zm-13.439-.675c-.314-.184-.393-.99-.768-1.01-.535-.03-.438 1.05-.436"
    " 1.68-.37-.33-.435-1.365-.164-1.89-.308-.15-.445.164-.618.284.22-1.59 2.34"
    "-.734 1.99.96zM4.713 5.995c-.685.756-.54 2.174-.459 3.188 1.244-.785 2.898.06"
    " 2.883 1.394.595-.016.223-.744.115-1.215-.353-1.528.592-3.187.041-4.59-1.064"
    ".084-1.939.52-2.578 1.215zm9.12 1.113c.307.562.404 1.148.84 1.57.195.19.574"
    ".424.387.95-.045.121-.365.391-.551.45-.674.195-2.254.03-1.721-.81.563.015"
    " 1.314.36 1.732-.045-.314-.524-.885-1.53-.674-2.13zm6.198-.013h.068c.33.668.6"
    " 1.375 1.004 1.965-.27.628-2.053 1.19-2.023.057.39-.17 1.05-.035 1.395-.25"
    "-.193-.556-.48-1.006-.434-1.771zm-6.927-1.617c-1.422-.33-2.131.592-2.56"
    " 1.553-.384-.094-.231-.615-.135-.883.255-.701 1.28-1.633 2.119-1.506.359.057"
    ".848.386.576.834zM9.642 1.593c-1.56.44-3.56 1.574-4.2 2.974.495-.07.84-.321"
    " 1.33-.351.186-.016.428.074.641.015.424-.104.78-1.065 1.102-1.41.31-.345.685"
    "-.496.94-.81.167-.09.409-.074.42-.33-.073-.075-.15-.135-.232-.105v.017z"
)
ICON_TEAMS = _brand_icon(
    "M20.625 8.127q-.55 0-1.025-.205-.475-.205-.832-.563-.358-.357-.563-.832Q18"
    " 6.053 18 5.502q0-.54.205-1.02t.563-.837q.357-.358.832-.563.474-.205 1.025"
    "-.205.54 0 1.02.205t.837.563q.358.357.563.837.205.48.205 1.02 0 .55-.205"
    " 1.025-.205.475-.563.832-.357.358-.837.563-.48.205-1.02.205zm0-3.75q-.469"
    " 0-.797.328-.328.328-.328.797 0 .469.328.797.328.328.797.328.469 0 .797"
    "-.328.328-.328.328-.797 0-.469-.328-.797-.328-.328-.797-.328zM24 10.002v"
    "5.578q0 .774-.293 1.46-.293.685-.803 1.194-.51.51-1.195.803-.686.293-1.459"
    ".293-.445 0-.908-.105-.463-.106-.85-.329-.293.95-.855 1.729-.563.78-1.319"
    " 1.336-.756.557-1.67.861-.914.305-1.898.305-1.148 0-2.162-.398-1.014-.399"
    "-1.805-1.102-.79-.703-1.312-1.664t-.674-2.086h-5.8q-.411 0-.704-.293T0"
    " 16.881V6.873q0-.41.293-.703t.703-.293h8.59q-.34-.715-.34-1.5 0-.727.275"
    "-1.365.276-.639.75-1.114.475-.474 1.114-.75.638-.275 1.365-.275t1.365.275q"
    ".639.276 1.114.75.474.475.75 1.114.275.638.275 1.365t-.275 1.365q-.276.639"
    "-.75 1.113-.475.475-1.114.75-.638.276-1.365.276-.188 0-.375-.024-.188-.023"
    "-.375-.058v1.078h10.875q.469 0 .797.328.328.328.328.797zM12.75 2.373q-.41"
    " 0-.78.158-.368.158-.638.434-.27.275-.428.639-.158.363-.158.773 0 .41.158"
    ".78.159.368.428.638.27.27.639.428.369.158.779.158.41 0 .773-.158.364-.159"
    ".64-.428.274-.27.433-.639.158-.369.158-.779 0-.41-.158-.773-.159-.364-.434"
    "-.64-.275-.275-.639-.433-.363-.158-.773-.158zM6.937 9.814h2.25V7.94H2.814v"
    "1.875h2.25v6h1.875zm10.313 7.313v-6.75H12v6.504q0 .41-.293.703t-.703.293H"
    "8.309q.152.809.556 1.5.405.691.985 1.19.58.497 1.318.779.738.281 1.582.281"
    ".926 0 1.746-.352.82-.351 1.436-.966.615-.616.966-1.43.352-.815.352-1.752"
    "zm5.25-1.547v-5.203h-3.75v6.855q.305.305.691.452.387.146.809.146.469 0"
    " .879-.176.41-.175.715-.48.304-.305.48-.715t.176-.879Z"
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
    glyph_html: str,
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
        f'<div class="conn-glyph {glyph_class}">{glyph_html}</div>'
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


def _render_github_block(gh_details: dict, gh_status: dict | None, gh_var: str, gh_pill: str) -> None:
    st.markdown(
        conn_card_html(
            kind="GitHub",
            glyph_html=ICON_GITHUB,
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


def _render_jira_block(jira_details: dict, jira_status: dict | None, jira_var: str, jira_pill: str) -> None:
    st.markdown(
        conn_card_html(
            kind="Jira",
            glyph_html=ICON_JIRA,
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


def _render_jenkins_block(
    jenkins_details: dict, jenkins_status: dict | None, jenkins_var: str, jenkins_pill: str
) -> None:
    st.markdown(
        conn_card_html(
            kind="Jenkins",
            glyph_html=ICON_JENKINS,
            glyph_class="jenkins",
            headline=_headline(
                jenkins_status,
                live=[(jenkins_status or {}).get("base_url") or ""],
                fallback=[jenkins_details.get("base_url") or ""],
                placeholder="Connect a Jenkins server",
            ),
            facts=[
                ("Token", jenkins_details.get("token") or "not set"),
                ("Source", jenkins_details.get("source") or "auto"),
                ("User", jenkins_details.get("user") or "not set"),
                ("Package", jenkins_details.get("package") or "—"),
            ],
            spawn=jenkins_details.get("spawn") or "",
            variant=jenkins_var,
            pill=jenkins_pill,
            error=_probe_error(jenkins_status),
        ),
        unsafe_allow_html=True,
    )
    if st.button(
        "Test Jenkins connection",
        disabled=not jenkins_configured(),
        width="stretch",
        help="Spawns the Jenkins MCP server and lists jobs.",
    ):
        with st.spinner("Talking to Jenkins MCP…"):
            st.session_state.jenkins_mcp_status = jenkins_connection_status()
        st.rerun()
    jenkins_opts = ["auto", "mcp", "off"]
    with st.expander("Edit Jenkins connection", expanded=not jenkins_configured()):
        with st.form("jenkins_mcp_config"):
            jenkins_url = st.text_input(
                "Jenkins URL",
                value=_cfg("JENKINS_URL"),
                placeholder="https://jenkins.example.com",
            )
            jk1, jk2 = st.columns(2)
            with jk1:
                jenkins_user = st.text_input("Username", value=_cfg("JENKINS_USER"))
            with jk2:
                jenkins_source = st.selectbox(
                    "When to use MCP",
                    jenkins_opts,
                    index=_option_index(_cfg("JENKINS_SOURCE", "auto"), jenkins_opts),
                )
            jenkins_token = st.text_input(
                "API token",
                type="password",
                value="",
                placeholder="••••  leave blank to keep current",
            )
            jk_cmd, jk_pkg, jk_args = _advanced_server_fields(
                "jenkins",
                "MCP_JENKINS_COMMAND",
                "MCP_JENKINS_PACKAGE",
                "MCP_JENKINS_ARGS",
                JENKINS_MCP_PACKAGE,
            )
            if st.form_submit_button("Save Jenkins", type="primary"):
                if jenkins_token:
                    jk_level, _jk_hint = config.jenkins_token_quality(jenkins_token)
                    if jk_level == "invalid":
                        st.error("That Jenkins API token looks invalid. Double-check it.")
                _save(
                    "jenkins_mcp_status",
                    {
                        "JENKINS_URL": jenkins_url,
                        "JENKINS_USER": jenkins_user,
                        "JENKINS_SOURCE": jenkins_source,
                        "MCP_JENKINS_COMMAND": jk_cmd,
                        "MCP_JENKINS_PACKAGE": jk_pkg,
                        "MCP_JENKINS_ARGS": jk_args,
                        "JENKINS_API_TOKEN": jenkins_token,
                    },
                )


def _render_teams_block(
    teams_details: dict, teams_status: dict | None, teams_var: str, teams_pill: str
) -> None:
    st.markdown(
        conn_card_html(
            kind="Microsoft Teams",
            glyph_html=ICON_TEAMS,
            glyph_class="teams",
            headline=_headline(
                teams_status,
                live=[(teams_status or {}).get("display_name") or ""],
                fallback=[],
                placeholder="Authenticate Microsoft Teams",
            ),
            facts=[
                ("Read-only", teams_details.get("read_only") or "true"),
                ("Source", teams_details.get("source") or "auto"),
                ("Auth", teams_details.get("auth") or "—"),
                ("Package", teams_details.get("package") or "—"),
            ],
            spawn=teams_details.get("spawn") or "",
            variant=teams_var,
            pill=teams_pill,
            error=_probe_error(teams_status),
        ),
        unsafe_allow_html=True,
    )
    if st.button(
        "Test Teams connection",
        disabled=not teams_configured(),
        width="stretch",
        help="Checks the Teams MCP auth status.",
    ):
        with st.spinner("Talking to Teams MCP…"):
            st.session_state.teams_mcp_status = teams_connection_status()
        st.rerun()
    teams_opts = ["read-only", "read-write"]
    with st.expander("Edit Teams connection", expanded=True):
        with st.form("teams_mcp_config"):
            teams_mode = st.selectbox(
                "Access mode",
                teams_opts,
                index=0 if _cfg("TEAMS_MCP_READ_ONLY", "true") == "true" else 1,
            )
            st.caption(
                "Teams uses interactive OAuth. Run once from the server: "
                "`npx @floriscornel/teams-mcp authenticate`"
            )
            tm_cmd, tm_pkg, tm_args = _advanced_server_fields(
                "teams",
                "MCP_TEAMS_COMMAND",
                "MCP_TEAMS_PACKAGE",
                "MCP_TEAMS_ARGS",
                TEAMS_MCP_PACKAGE,
            )
            if st.form_submit_button("Save Teams", type="primary"):
                _save(
                    "teams_mcp_status",
                    {
                        "TEAMS_SOURCE": "auto",
                        "TEAMS_MCP_READ_ONLY": "true" if teams_mode == "read-only" else "false",
                        "MCP_TEAMS_COMMAND": tm_cmd,
                        "MCP_TEAMS_PACKAGE": tm_pkg,
                        "MCP_TEAMS_ARGS": tm_args,
                    },
                )


def render_mcp_panel() -> None:
    """2×2 grid of MCP connection cards with test actions and editors."""
    if (config.setting("NEO4J_PASSWORD") or "").strip() in {"", "changeme"}:
        st.warning(
            "Neo4j is using the default password. Set NEO4J_PASSWORD in .env "
            "to a strong value before exposing this app beyond localhost."
        )
    gh_details = github_mcp_details()
    jira_details = jira_mcp_details()
    jenkins_details = jenkins_mcp_details()
    teams_details = teams_mcp_details()
    gh_status = st.session_state.get("github_mcp_status")
    jira_status = st.session_state.get("jira_mcp_status")
    jenkins_status = st.session_state.get("jenkins_mcp_status")
    teams_status = st.session_state.get("teams_mcp_status")
    gh_var, gh_pill = mcp_probe_state(gh_status, github_configured())
    jira_var, jira_pill = mcp_probe_state(jira_status, jira_configured())
    jenkins_var, jenkins_pill = mcp_probe_state(jenkins_status, jenkins_configured())
    teams_var, teams_pill = mcp_probe_state(teams_status, teams_configured())

    st.markdown('<div class="kicker">Integrations · MCP</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="section-title">GitHub · Jira · Jenkins · Teams connections</div>'
        '<div class="section-note">'
        "AEGIS talks to external systems only through MCP. Credentials stay in "
        "<code>.env</code> and are injected into the server process — never into REST clients. "
        "Graph analysis still works if a connection is off.</div>",
        unsafe_allow_html=True,
    )

    top_l, top_r = st.columns(2, gap="large")
    with top_l:
        _render_github_block(gh_details, gh_status, gh_var, gh_pill)
    with top_r:
        _render_jira_block(jira_details, jira_status, jira_var, jira_pill)

    bottom_l, bottom_r = st.columns(2, gap="large")
    with bottom_l:
        _render_jenkins_block(jenkins_details, jenkins_status, jenkins_var, jenkins_pill)
    with bottom_r:
        _render_teams_block(teams_details, teams_status, teams_var, teams_pill)
