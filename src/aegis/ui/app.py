import importlib
import sys
from html import escape as html_escape
from pathlib import Path

try:
    import aegis  # noqa: F401
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import aegis.config as _aegis_config

importlib.reload(_aegis_config)
for _mod_name in (
    "aegis.integrations.mcp_runtime",
    "aegis.integrations.github_client",
    "aegis.integrations.github_comments",
    "aegis.integrations.jira_client",
    "aegis.ui.mcp_panel",
):
    if _mod_name in sys.modules:
        importlib.reload(sys.modules[_mod_name])

import streamlit as st

from aegis.agents.registry import AGENT_SPECS
from aegis.core.orchestrator import AegisOrchestrator, AegisReport
from aegis.graph import queries
from aegis.graph.neo4j import CIGClient
from aegis.integrations.github_comments import maybe_post_report, resolve_github_pr_number
from aegis.llm.ollama import OllamaClient
from aegis.ui.mcp_panel import render_mcp_panel

st.set_page_config(page_title="Project AEGIS", layout="wide")

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

      :root {
        --bg: #070b14;
        --panel: rgba(13, 19, 33, 0.72);
        --panel-solid: #0d1321;
        --border: rgba(120, 150, 220, 0.16);
        --border-bright: rgba(120, 190, 255, 0.35);
        --text: #dbe4f5;
        --muted: #7a8ba8;
        --cyan: #22d3ee;
        --violet: #a78bfa;
        --green: #34d399;
        --amber: #fbbf24;
        --rose: #fb7185;
        --grad: linear-gradient(120deg, #22d3ee 0%, #a78bfa 55%, #f472b6 100%);
      }

      .stApp { background: radial-gradient(1200px 700px at 15% -10%, #0d1b3a 0%, transparent 55%),
                          radial-gradient(1000px 600px at 110% 20%, #1a0f33 0%, transparent 50%),
                          var(--bg); color: var(--text); }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stToolbar"] { right: 1rem; }

      html, body, [class*="css"] {
        font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      .mono, code, pre { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace !important; }

      .hero { padding: 6px 0 2px; }
      .hero .title { font-size: 42px; font-weight: 700; letter-spacing: -1px; line-height: 1.05;
                     background: var(--grad); -webkit-background-clip: text; background-clip: text;
                     -webkit-text-fill-color: transparent; }
      .hero .tagline { color: var(--muted); font-size: 15px; margin-top: 6px; }
      .live { display:inline-flex; align-items:center; gap:8px; color: var(--green);
              font-size: 12px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; }
      .live .dot { width:8px; height:8px; border-radius:50%; background: var(--green);
                   box-shadow: 0 0 10px var(--green); animation: pulse 2s infinite; }
      @keyframes pulse { 0%,100% {opacity:1} 50% {opacity:.35} }

      .glass { background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
               padding: 16px 18px; backdrop-filter: blur(14px);
               box-shadow: 0 10px 40px rgba(0,0,0,.35); }
      .glass-glow { border-color: var(--border-bright);
                    box-shadow: 0 0 0 1px rgba(120,190,255,.06), 0 0 34px rgba(34,211,238,.08); }

      .stat { background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
              padding: 14px 18px; backdrop-filter: blur(14px); }
      .stat .label { color: var(--muted); font-size: 11px; letter-spacing: 1.2px;
                     text-transform: uppercase; }
      .stat .value { font-size: 30px; font-weight: 700; margin-top: 4px; }
      .stat .delta { font-size: 12px; color: var(--muted); margin-top: 2px; }
      .stat.accent .value { background: var(--grad); -webkit-background-clip:text;
                            background-clip:text; -webkit-text-fill-color:transparent; }

      .badge { display:inline-block; border-radius:10px; padding:5px 16px; font-weight:700;
               font-size:15px; letter-spacing:1px; color:#06121f; }
      .badge.approve { background: linear-gradient(120deg,#34d399,#22d3ee); }
      .badge.review { background: linear-gradient(120deg,#fbbf24,#fb923c); }
      .badge.reject { background: linear-gradient(120deg,#fb7185,#ef4444); }

      .chip { display:inline-block; background: rgba(44,62,110,.35); color:#c8d6f0;
              border:1px solid rgba(120,150,220,.22); border-radius:999px;
              padding:2px 12px; margin:2px 6px 2px 0; font-size:12.5px; }
      .chip.ok { background: rgba(52,211,153,.14); color:#7ff0c6; border-color: rgba(52,211,153,.35); }
      .chip.warn { background: rgba(251,191,36,.13); color:#ffd98a; border-color: rgba(251,191,36,.35); }
      .chip.bad { background: rgba(251,113,133,.13); color:#ffb3c1; border-color: rgba(251,113,133,.35); }

      .kicker { color: var(--muted); font-size:11px; font-weight:700; letter-spacing:2.5px;
                text-transform: uppercase; margin: 8px 0 2px; }
      .section-title { font-size:20px; font-weight:600; margin: 6px 0 10px; }

      .pr-head { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
      .pr-head .num { font-size:26px; font-weight:800;
                      background: var(--grad); -webkit-background-clip:text; background-clip:text;
                      -webkit-text-fill-color:transparent; }
      .pr-head .title { font-size:17px; font-weight:600; }
      .pr-head .meta { color: var(--muted); font-size:13px; }

      .agent { background: var(--panel); border:1px solid var(--border); border-radius:14px;
               padding: 12px 16px; margin-bottom: 10px; backdrop-filter: blur(10px);
               border-left-width:3px; }
      .agent.ok { border-left-color: var(--green); }
      .agent.warn { border-left-color: var(--amber); }
      .agent.bad { border-left-color: var(--rose); }
      .agent .role { display:flex; align-items:center; gap:8px; font-weight:600; font-size:14px; }
      .agent .role .tick { width:8px; height:8px; border-radius:50%; }
      .agent.ok .tick { background: var(--green); box-shadow:0 0 8px var(--green); }
      .agent.warn .tick { background: var(--amber); box-shadow:0 0 8px var(--amber); }
      .agent.bad .tick { background: var(--rose); box-shadow:0 0 8px var(--rose); }
      .agent .out { color:#b7c4de; font-size:12.5px; margin-top:6px; white-space:pre-wrap;
                    font-family:'JetBrains Mono', monospace; }

      .chain { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }
      .chain .hop { background: rgba(44,62,110,.35); border:1px solid var(--border);
                    border-radius:12px; padding:7px 14px; font-weight:600; font-size:13.5px; }
      .chain .hop.ok { border-color: rgba(52,211,153,.5); color:#7ff0c6; }
      .chain .hop.warn { border-color: rgba(251,191,36,.5); color:#ffd98a; }
      .chain .hop.bad { border-color: rgba(251,113,133,.5); color:#ffb3c1; }
      .chain .hop.dist { font-weight:400; font-size:11px; opacity:.7; }
      .chain .arr { color: var(--muted); font-weight:700; }

      .provenance { border:1px dashed rgba(120,190,255,.28); border-radius:14px;
                    padding: 14px 18px; background: rgba(13,27,58,.25); }
      .provenance .q { color:#8fb7dd; font-size:12px; font-family:'JetBrains Mono',monospace;
                       margin:4px 0; white-space:pre-wrap; }
      .provenance .qline { color: var(--muted); font-size:11.5px; margin-top:6px; }

      .timeline { position:relative; padding-left: 20px; }
      .timeline::before { content:""; position:absolute; left:5px; top:6px; bottom:6px;
                          width:2px; background: linear-gradient(var(--cyan), var(--violet), transparent); }
      .timeline .rel { position:relative; margin-bottom: 12px; }
      .timeline .rel::before { content:""; position:absolute; left:-20px; top:8px; width:12px; height:12px;
                               border-radius:50%; background: var(--violet); box-shadow:0 0 10px var(--violet); }
      .timeline .rel .ver { font-weight:700; font-size:15px; }
      .timeline .rel .sub { color: var(--muted); font-size:12.5px; }

      div[data-testid="stExpander"] { background: var(--panel); border:1px solid var(--border);
                                      border-radius:12px; }
      div[data-testid="stExpander"] summary { font-weight:600; }
      .stTabs [data-baseweb="tab-list"] { gap: 6px; }
      .stTabs [data-baseweb="tab"] { border-radius: 10px 10px 0 0; }
      .stTabs [aria-selected="true"] { background: rgba(34,211,238,.1); }

      [data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:12px;
                                    overflow:hidden; }
      button[kind="primary"] { background: var(--grad); color:#06121f; font-weight:700;
                               border:none; }
      button[kind="primary"]:hover { filter: brightness(1.1); }
      .stProgress > div > div > div { background: var(--grad); }
      hr { border-color: var(--border); }

      .conn-card { background: var(--panel); border:1px solid var(--border); border-radius:18px;
                   padding: 18px 20px 16px; backdrop-filter: blur(14px); margin-bottom: 12px;
                   box-shadow: 0 10px 40px rgba(0,0,0,.35); position:relative; overflow:hidden; }
      .conn-card::before { content:""; position:absolute; inset:0 auto 0 0; width:3px; }
      .conn-card.ok::before { background: var(--green); }
      .conn-card.warn::before { background: var(--amber); }
      .conn-card.bad::before { background: var(--rose); }
      .conn-card.ok { border-color: rgba(52,211,153,.28);
                      box-shadow: 0 0 0 1px rgba(52,211,153,.08), 0 10px 40px rgba(0,0,0,.35); }
      .conn-head { display:flex; align-items:center; gap:12px; margin-bottom: 12px; }
      .conn-glyph { width:42px; height:42px; border-radius:12px; display:flex; align-items:center;
                    justify-content:center; font-weight:800; font-size:13px; letter-spacing:.4px;
                    color:#06121f; flex-shrink:0; }
      .conn-glyph.gh { background: linear-gradient(135deg,#e8eefc,#a78bfa); }
      .conn-glyph.jira { background: linear-gradient(135deg,#22d3ee,#60a5fa); }
      .conn-name { font-weight:700; font-size:16px; }
      .conn-via { color: var(--muted); font-size:12px; margin-top:1px; }
      .conn-pill { margin-left:auto; border-radius:999px; padding:4px 12px; font-size:11px;
                   font-weight:700; letter-spacing:.8px; text-transform:uppercase; }
      .conn-pill.ok { background: rgba(52,211,153,.16); color:#7ff0c6; border:1px solid rgba(52,211,153,.35); }
      .conn-pill.warn { background: rgba(251,191,36,.14); color:#ffd98a; border:1px solid rgba(251,191,36,.35); }
      .conn-pill.bad { background: rgba(251,113,133,.14); color:#ffb3c1; border:1px solid rgba(251,113,133,.35); }
      .conn-headline { font-size:20px; font-weight:700; letter-spacing:-.3px; margin: 2px 0 10px;
                       background: var(--grad); -webkit-background-clip:text; background-clip:text;
                       -webkit-text-fill-color:transparent; }
      .conn-facts { display:grid; grid-template-columns: 1fr 1fr; gap:8px 14px; margin-bottom: 12px; }
      .conn-fact .k { color: var(--muted); font-size:10px; letter-spacing:1.2px; text-transform:uppercase; }
      .conn-fact .v { font-size:13px; margin-top:2px; color:#d5def0; }
      .term { font-family:'JetBrains Mono', monospace; font-size:11.5px; color:#9ec9ea;
              background: rgba(7,14,28,.55); border:1px dashed rgba(120,190,255,.22);
              border-radius:10px; padding:8px 12px; overflow:auto; white-space:nowrap; }
      .conn-err { margin-top:10px; color:#ffb3c1; font-size:12.5px; }

      .stTextInput input, .stSelectbox [data-baseweb="select"] > div {
        background: rgba(7,14,28,.55) !important; border-radius:10px !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="hero"><div class="title">PROJECT AEGIS</div>'
    '<div class="tagline">Connected Intelligence Graph — AI-driven release shield · '
    '<span class="live"><span class="dot"></span>live from Neo4j</span></div></div>',
    unsafe_allow_html=True,
)

VERDICT_COLORS = {"APPROVE": "approve", "REVIEW": "review", "REJECT": "reject"}
SOURCE_LABELS = {
    "direct_file_coverage": "Direct file coverage",
    "affected_service_coverage": "Affected service coverage",
    "regression_history": "Regression history",
}
ROLE_ORDER = [
    ("PR Compliance Reviewer", "PR Reviewer"),
    ("Blast Radius Analyst", "Blast Radius"),
    ("Risk Analyzer", "Risk Analyzer"),
    ("Test Selector", "Test Selector"),
    ("AEGIS Release Orchestrator", "Orchestrator"),
]

GLOSSARY = {
    "Hops": "Distance upstream from the changed services, walked over DEPENDS_ON edges (0 = changed service).",
    "Routes": "API routes exposed by a service that could be affected.",
    "Customer flows": "End-to-end customer journeys that touch at-risk services.",
    "Tests": "Automated tests covering files owned by that service.",
    "Past incidents": "Incidents previously logged against the service.",
    "Merge confidence": "How safe AEGIS thinks a merge is (higher = safer).",
    "Regression probability": "Estimated likelihood the change breaks something.",
    "Alignment": "Whether changed files match the Jira stories they claim to implement.",
    "Story epic": "The business capability a Jira story belongs to (Payments, Commerce, Platform).",
    "RELEASED_IN": "Relationship between a microservice and the release version it shipped in.",
    "DETECTS": "Relationship between a test case and the incident it would have caught.",
}


def chips(items, variant="") -> str:
    parts = [f'<span class="chip {variant}">{html_escape(str(i))}</span>' for i in items]
    return "".join(parts) if parts else '<span style="color:var(--muted)">none</span>'


def status_rows_html(title, rows) -> str:
    """Render a stack-status card. Rows are (label, variant) or (label, value, variant)."""
    parts = []
    for row in rows:
        if len(row) >= 3:
            label, value, variant = row[0], row[1], row[2]
        else:
            label, second = row[0], row[1]
            if second in {"ok", "warn", "bad"}:
                value, variant = second.upper(), second
            else:
                value, variant = second, ""
        if variant in {"ok", "warn", "bad"}:
            chip = (
                f'<span class="chip {variant}" style="margin:0">'
                f"{html_escape(str(value))}</span>"
            )
        else:
            chip = (
                f'<span style="color:var(--muted);font-size:12.5px;text-align:right;'
                f'max-width:62%">{html_escape(str(value))}</span>'
            )
        parts.append(
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'padding:5px 0;border-bottom:1px solid var(--border);font-size:13px;gap:12px">'
            f"<span>{html_escape(str(label))}</span>{chip}</div>"
        )
    return (
        f'<div class="glass glass-glow" style="margin-bottom:12px">'
        f'<div style="font-weight:600;margin-bottom:4px">{html_escape(title)}</div>'
        f"{''.join(parts)}</div>"
    )


def stat_html(label: str, value: str, delta: str = "", accent: bool = False) -> str:
    delta_html = f'<div class="delta">{delta}</div>' if delta else ""
    return (
        f'<div class="stat {"accent" if accent else ""}">'
        f'<div class="label">{label}</div><div class="value">{value}</div>{delta_html}</div>'
    )


def agent_nodes(report: AegisReport) -> list[tuple[str, str, str]]:
    """(role_short, output_text, variant) for the agent output diagram."""
    raw = report.agent_outputs.get("raw", {})
    nodes = []

    alignment = report.agent_outputs.get("alignment") or report.story_alignment.get("alignment", "GAPS")
    text = raw.get("PR Compliance Reviewer") or (
        f"ALIGNMENT={alignment}\n"
        f"Deterministic check of {len(report.story_alignment.get('files', []))} changed file(s) vs story epics."
    )
    nodes.append(("PR Reviewer", text.strip(), "ok" if alignment == "ALIGNED" else "bad"))

    radius = report.blast_radius
    affected = radius.get("affected_services", [])
    text = raw.get("Blast Radius Analyst") or (
        f"AFFECTED={len(affected)}\n" + ", ".join(affected) or "no services mapped"
    )
    nodes.append(("Blast Radius", text.strip(), "warn"))

    text = raw.get("Risk Analyzer") or (
        f"REGRESSION_PROBABILITY={report.regression_probability:.3f}\n"
        f"MERGE_CONFIDENCE={report.merge_confidence:.1f}"
    )
    nodes.append(("Risk Analyzer", text.strip(), "warn"))

    tests = ", ".join(t["id"] for t in report.recommended_tests) or "none"
    text = raw.get("Test Selector") or f"SELECTED {len(report.recommended_tests)}: {tests}"
    nodes.append(("Test Selector", text.strip(), "ok"))

    text = raw.get("AEGIS Release Orchestrator") or f"VERDICT={report.verdict}"
    nodes.append(("Orchestrator", text.strip(), report.verdict.lower()))

    return nodes


def agent_diagram_html(report: AegisReport) -> str:
    blocks = []
    for role, out, variant in agent_nodes(report):
        blocks.append(
            f'<div class="agent {variant}"><div class="role"><span class="tick"></span>{role}</div>'
            f'<div class="out">{out}</div></div>'
        )
    return "".join(blocks)


def blast_chain_html(report: AegisReport) -> str:
    radius = report.blast_radius
    hops = radius.get("upstream_hops", {})
    changed = set(radius.get("changed_services", []))
    ordered = sorted(
        radius.get("affected_services", []),
        key=lambda s: (0 if s in changed else min(hops.get(s, [99])), s),
    )
    parts = []
    for i, svc in enumerate(ordered):
        distance = 0 if svc in changed else min(hops.get(svc, [99]))
        variant = "ok" if svc in changed else ("warn" if distance == 1 else "bad")
        dist_html = "" if svc in changed else f' <span class="dist">+{distance} hop</span>'
        parts.append(f'<span class="hop {variant}">{svc}{dist_html}</span>')
        if i < len(ordered) - 1:
            parts.append('<span class="arr">→</span>')
    return '<div class="chain">' + "".join(parts) + "</div>"


def provenance_html(report: AegisReport) -> str:
    prov = report.provenance
    stats = prov.get("graph_stats", {})
    nodes = stats.get("nodes", {})
    rels = stats.get("relationships", {})
    generated = prov.get("generated_at", "unknown")

    node_summary = " · ".join(
        f"{label} <b>{count}</b>" for label, count in sorted(nodes.items())
    )
    rel_summary = " · ".join(
        f"{rel} <b>{count}</b>" for rel, count in sorted(rels.items())
    )

    q_block = "".join(
        f'<div class="q">→ {q}</div>' for q in prov.get("queries", [])
    )
    empty_q = "<div class='q'>—</div>"

    return (
        f'<div class="provenance">'
        f'<div class="live"><span class="dot"></span>data sourced from the CIG · {generated}</div>'
        f'<div class="qline">Neo4j graph read: {node_summary}</div>'
        f'<div class="qline">Relationships traversed: {rel_summary}</div>'
        f'<div class="qline" style="margin-top:8px">Cypher executed for this analysis:</div>'
        f'{q_block or empty_q}'
        f'</div>'
    )


@st.cache_data(show_spinner=False, ttl=600)
def run_analysis(pr_number: int, use_llm: bool) -> AegisReport:
    return AegisOrchestrator().analyze_pr(pr_number, use_llm=use_llm)


tab_health, tab_analyze = st.tabs(["Infrastructure & CIG", "PR Analysis"])

with tab_health:
    col_stat, col_graph = st.columns([1, 1], gap="large")
    with col_stat:
        st.markdown('<div class="kicker">Stack status</div>', unsafe_allow_html=True)

        neo4j_rows = [('Checking Neo4j...', 'warn')]
        try:
            cig = CIGClient()
            ok = cig.verify_connection()
            if ok:
                stats = queries.graph_stats(cig)
                releases = queries.release_history(cig)
                open_inc = queries.open_incidents(cig)
                neo4j_rows = [
                    ("Neo4j CIG", "ok"),
                    ("Endpoint", "bolt://localhost:7687"),
                    ("Nodes", str(sum(stats.get("nodes", {}).values()))),
                    ("Relationships", str(sum(stats.get("relationships", {}).values()))),
                ]
            else:
                neo4j_rows = [("Neo4j CIG: connection failed", "bad")]
                stats, releases, open_inc = {}, [], []
            cig.close()
        except Exception as exc:
            neo4j_rows = [(f"Neo4j CIG: {exc}", "bad")]
            stats, releases, open_inc = {}, [], []

        ollama_rows = [("Checking Ollama...", "warn")]
        try:
            llm = OllamaClient()
            models = llm.list_models()
            if llm.is_model_available():
                ollama_rows = [
                    ("Ollama", "ok"),
                    ("Models", ", ".join(models)),
                    ("Active model", llm.model),
                ]
            else:
                ollama_rows = [
                    ("Ollama", "ok"),
                    (f"Model '{llm.model}' not pulled yet", "warn"),
                ]
        except Exception as exc:
            ollama_rows = [(f"Ollama: {exc}", "bad")]

        st.markdown(
            status_rows_html("Neo4j — Connected Intelligence Graph", neo4j_rows)
            + status_rows_html("Ollama — Local LLM", ollama_rows),
            unsafe_allow_html=True,
        )

        st.markdown('<div class="kicker">CrewAI agents</div>', unsafe_allow_html=True)
        st.caption("Six AIDLC roles, one local LLM, orchestrated by CrewAI.")
        for spec in AGENT_SPECS:
            with st.expander(f"{spec['role']}  ·  `{spec['name']}`"):
                st.markdown(f"**Goal:** {spec['goal']}")
                st.markdown(f"**Backstory:** {spec['backstory']}")

    with col_graph:
        st.markdown('<div class="kicker">Graph intelligence</div>', unsafe_allow_html=True)
        nodes = stats.get("nodes", {})
        rels = stats.get("relationships", {})
        if nodes:
            c1, c2, c3 = st.columns(3)
            c1.markdown(
                stat_html("Microservices", str(nodes.get("Microservice", 0))), unsafe_allow_html=True)
            c2.markdown(
                stat_html("Code files", str(nodes.get("CodeFile", 0))), unsafe_allow_html=True)
            c3.markdown(
                stat_html("Test cases", str(nodes.get("TestCase", 0))), unsafe_allow_html=True)
            c4, c5, c6 = st.columns(3)
            c4.markdown(
                stat_html("Incidents", str(nodes.get("Incident", 0)),
                          delta=f"{len(open_inc)} open"), unsafe_allow_html=True)
            c5.markdown(
                stat_html("Releases", str(nodes.get("Release", 0))), unsafe_allow_html=True)
            c6.markdown(
                stat_html("PRs analyzed", str(nodes.get("PullRequest", 0))), unsafe_allow_html=True)

            if open_inc:
                st.markdown('<div class="kicker">Open incidents</div>', unsafe_allow_html=True)
                for inc in open_inc:
                    st.markdown(
                        f'<span class="chip bad">{inc["id"]} · S{inc["severity"]} · '
                        f'{inc["service"]} · {inc["root_cause"]}</span>',
                        unsafe_allow_html=True,
                    )

            st.markdown('<div class="kicker">Relationship map</div>', unsafe_allow_html=True)
            st.markdown(
                chips([f"{rel}×{count}" for rel, count in sorted(rels.items())]), unsafe_allow_html=True)

        st.markdown('<div class="kicker">Release timeline</div>', unsafe_allow_html=True)
        if releases:
            st.markdown('<div class="timeline">', unsafe_allow_html=True)
            for rel in reversed(releases):
                st.markdown(
                    f'<div class="rel"><div class="ver">{rel["version"]} '
                    f'<span class="chip ok">live</span></div>'
                    f'<div class="sub">{rel["deployed_at"]} · {rel["notes"]} · '
                    f'{", ".join(rel["services"]) or "—"}</div></div>',
                    unsafe_allow_html=True,
                )
            st.markdown("</div>", unsafe_allow_html=True)

    render_mcp_panel()

with tab_analyze:
    try:
        cig = CIGClient()
        rows = cig.run(
            "MATCH (pr:PullRequest) RETURN pr.number AS number, pr.title AS title "
            "ORDER BY pr.number"
        )
        cig.close()
    except Exception as exc:
        st.error(f"Could not load PRs: {exc}")
        rows = []

    options = {r["number"]: r["title"] for r in rows}
    pr_number = st.selectbox(
        "Pull request",
        list(options.keys()),
        format_func=lambda n: f"#{n} — {options[n]}",
    )

    fast = st.toggle(
        "Fast mode — deterministic analysis (no LLM agents)",
        value=True,
        help="Runs instantly using graph math only. Turn off to invoke the CrewAI "
             "agents over the local LLM (slower, but shows real agent reasoning).",
    )

    if st.button("Run AEGIS analysis", type="primary"):
        with st.spinner(
            "Fast path: computing over the CIG..." if fast
            else "Agents reasoning over the CIG (local LLM)..."
        ):
            try:
                report = run_analysis(pr_number, use_llm=not fast)
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
                report = None

        posted = None
        if report:
            gh_target = resolve_github_pr_number(report.pr_number)
            with st.spinner(f"Posting AEGIS report to GitHub PR #{gh_target}..."):
                posted = maybe_post_report(report)

        if report:
            st.markdown(
                f'<div class="glass pr-head" style="margin-bottom:14px">'
                f'<span class="num">#{report.pr_number}</span>'
                f'<span class="title">{report.pr.get("title", "")}</span>'
                f'<span class="meta">by {report.pr.get("author", "?")} · '
                f'{report.pr.get("base", "main")} → {report.pr.get("head", "")}</span>'
                f'<span class="meta" style="margin-left:auto">mode: '
                f'{"LLM agents" if report.mode == "full" else "deterministic"}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if posted and posted.get("ok"):
                gh_n = posted.get("github_pr_number")
                repo = posted.get("repo") or ""
                mapped = (
                    f" (CIG #{posted.get('pr_number')})"
                    if gh_n and posted.get("pr_number") != gh_n
                    else ""
                )
                link = posted.get("html_url")
                msg = f"Posted analysis to GitHub PR #{gh_n} on `{repo}`{mapped}."
                if link:
                    st.success(msg)
                    st.markdown(f"[Open comment]({link})")
                else:
                    st.success(msg)
            elif posted and posted.get("skipped"):
                st.caption(
                    "GitHub comment skipped — set `GITHUB_TOKEN`, "
                    "`GITHUB_REPO_OWNER`, `GITHUB_REPO_NAME` to auto-post."
                )
            elif posted and not posted.get("ok"):
                st.warning(
                    f"Analysis completed, but GitHub comment failed: {posted.get('error')}"
                )

            stories = report.stories
            if stories:
                story_labels = [
                    f"{s['key']} · {s['title']} ({s['status']})" for s in stories
                ]
                st.markdown(
                    f'<b>Linked stories</b> '
                    f'{chips(story_labels, "ok")}',
                    unsafe_allow_html=True,
                )

            st.markdown('<div class="kicker">Agent outputs</div>', unsafe_allow_html=True)
            st.markdown(agent_diagram_html(report), unsafe_allow_html=True)
            st.markdown(
                '<div style="font-size:11.5px;color:var(--muted)">Synthesis of the five '
                'CrewAI agent outputs (fast mode shows deterministic reasoning).</div>',
                unsafe_allow_html=True,
            )

            st.markdown('<div class="kicker">Decision</div>', unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns([1.1, 1, 1, 1], gap="medium")
            with c1:
                st.markdown(
                    f'<div class="glass" style="text-align:center">'
                    f'<div class="label" style="color:var(--muted);font-size:11px;'
                    f'letter-spacing:1.5px;text-transform:uppercase">Verdict</div>'
                    f'<span class="badge {VERDICT_COLORS.get(report.verdict, "review")}" '
                    f'style="margin-top:8px">{report.verdict}</span></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    stat_html("Merge confidence", f"{report.merge_confidence:.0f}%", accent=True),
                    unsafe_allow_html=True)
            with c3:
                st.markdown(
                    stat_html("Regression probability", f"{report.regression_probability:.0%}", accent=True),
                    unsafe_allow_html=True)
            with c4:
                st.markdown(
                    stat_html("Alignment", report.agent_outputs.get("alignment", "GAPS")),
                    unsafe_allow_html=True)
            st.progress(min(max(report.merge_confidence, 0), 100) / 100)

            st.markdown('<div class="kicker">Requirements alignment</div>', unsafe_allow_html=True)
            alignment = report.story_alignment
            if alignment.get("files"):
                for f in alignment["files"]:
                    variant = "ok" if f["aligned"] else "bad"
                    st.markdown(
                        f'<span class="chip {variant}">{"✓" if f["aligned"] else "✗"} '
                        f'{f["path"]} · {f["reason"]}</span>',
                        unsafe_allow_html=True,
                    )
                if alignment["alignment"] == "GAPS":
                    st.warning(
                        "Misaligned files found: the PR touches code that does not match "
                        "the epic of its linked stories. Human review required."
                    )
            else:
                st.info("No changed files mapped to the graph.")

            st.markdown('<div class="kicker">Blast radius</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="glass"><b>Blast chain (hop distance upstream)</b><br>'
                f'{blast_chain_html(report)}</div>',
                unsafe_allow_html=True,
            )

            radius = report.blast_radius
            features = report.deterministic_features

            rows = []
            for svc in radius.get("affected_services", []):
                detail = radius["services_detail"].get(svc, {})
                hops = max(radius["upstream_hops"].get(svc, [0]))
                rows.append({
                    "Service": svc,
                    "Hops": hops,
                    "Routes": len(detail.get("routes", [])),
                    "Flows": len(detail.get("flows", [])),
                    "Tests": len(detail.get("tests", [])),
                    "Past incidents": len(detail.get("incidents", [])),
                })
            st.dataframe(
                rows,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Hops": st.column_config.NumberColumn("Hops", help=GLOSSARY["Hops"]),
                    "Routes": st.column_config.NumberColumn("Routes", help=GLOSSARY["Routes"]),
                    "Flows": st.column_config.NumberColumn("Flows", help=GLOSSARY["Customer flows"]),
                    "Tests": st.column_config.NumberColumn("Tests", help=GLOSSARY["Tests"]),
                    "Past incidents": st.column_config.NumberColumn("Past incidents", help=GLOSSARY["Past incidents"]),
                },
            )

            st.markdown(
                f'<b>Customer flows at risk</b> '
                f'{chips(features.get("affected_flows", []), "warn")}',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<b>Past incidents in scope</b> '
                f'{chips(features.get("past_incidents", []))}',
                unsafe_allow_html=True,
            )

            st.markdown('<div class="kicker">Test targeting</div>', unsafe_allow_html=True)
            suite = report.suite_stats
            total = suite.get("total_tests", 0)
            reduction = suite.get("reduction_pct", 0)
            c1, c2, c3 = st.columns(3)
            c1.markdown(
                stat_html("Suite size", f"{total} tests"), unsafe_allow_html=True)
            c2.markdown(
                stat_html("Targeted", f"{len(report.recommended_tests)} tests",
                          delta="instead of the full suite"), unsafe_allow_html=True)
            c3.markdown(
                stat_html("Suite cut", f"{reduction:.1f}%", accent=True,
                          delta=f"−{len(report.recommended_tests)} tests not run"),
                unsafe_allow_html=True)

            if report.recommended_tests:
                test_rows = [{
                    "Test": t["id"],
                    "Why": SOURCE_LABELS.get(t.get("source"), t.get("source", "")),
                    "Related incidents": ", ".join(t.get("incidents", [])) or "-",
                } for t in report.recommended_tests]
                st.dataframe(
                    test_rows,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Why": st.column_config.TextColumn("Why", help="Selection rationale, in priority order."),
                    },
                )
            else:
                st.info("No tests in scope.")

            st.markdown('<div class="kicker">Risk signals</div>', unsafe_allow_html=True)
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(
                stat_html("Files changed", str(features.get("num_files", 0))), unsafe_allow_html=True)
            c2.markdown(
                stat_html("Code churn", f'{features.get("churn", 0)} lines'), unsafe_allow_html=True)
            c3.markdown(
                stat_html("File coverage", f'{features.get("file_test_coverage_ratio", 0):.0%}'),
                unsafe_allow_html=True)
            c4.markdown(
                stat_html("Open incidents", str(len(features.get("past_incidents", [])) or 0)),
                unsafe_allow_html=True)

            st.markdown('<div class="kicker">Data provenance</div>', unsafe_allow_html=True)
            st.markdown(provenance_html(report), unsafe_allow_html=True)

            with st.expander("What do these numbers mean?"):
                for term, meaning in GLOSSARY.items():
                    st.markdown(f"**{term}** — {meaning}")

            with st.expander("Raw blast radius JSON"):
                st.json(radius)
            with st.expander("Raw risk features JSON"):
                st.json(features)
            with st.expander("Raw agent output"):
                st.json(report.agent_outputs)
