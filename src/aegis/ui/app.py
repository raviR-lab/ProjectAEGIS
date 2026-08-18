import importlib
import itertools
import math
import re
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
    "aegis.integrations.jenkins_client",
    "aegis.integrations.teams_client",
    "aegis.graph.ingest",
    "aegis.graph.sync",
    "aegis.graph.recommend",
    "aegis.graph.queries",
    "aegis.core.orchestrator",
    "aegis.ui.mcp_panel",
):
    if _mod_name in sys.modules:
        importlib.reload(sys.modules[_mod_name])

import streamlit as st

from aegis.agents.registry import AGENT_SPECS
from aegis.core.orchestrator import (
    AegisOrchestrator,
    AegisReport,
    BLAST_EXTRA_SERVICE,
    BLAST_FLOW_RISK,
    BLAST_INCIDENT_RISK,
    CONFIDENCE_MAX,
    GAP_RISK,
    LLM_RISK_WEIGHT,
    RISK_CHURN_CAP,
    SCORE_MAX,
    SECURITY_FAIL_RISK,
    SECURITY_REVIEW_RISK,
    TEST_NONE_RISK,
    TEST_UNCOVERED_RISK,
)
from aegis.graph import queries
from aegis.graph.neo4j import CIGClient
from aegis.integrations.github_comments import maybe_post_report, resolve_github_pr_number
from aegis.llm.ollama import OllamaClient
from aegis.ui.mcp_panel import render_mcp_panel


st.set_page_config(page_title="Project AEGIS", layout="wide")

st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;600&display=swap');

      /* light-dark() follows Streamlit's color-scheme on .stApp — no JS, instant toggle. */
      :root {
        --cyan: #22d3ee;
        --violet: #a78bfa;
        --green: #34d399;
        --amber: #fbbf24;
        --rose: #fb7185;
        --grad: linear-gradient(120deg, #22d3ee 0%, #a78bfa 55%, #f472b6 100%);
        --bg: light-dark(#f4f7fc, #070b14);
        --panel: light-dark(rgba(255, 255, 255, 0.92), rgba(13, 19, 33, 0.72));
        --panel-solid: light-dark(#ffffff, #0d1321);
        --border: light-dark(rgba(15, 23, 42, 0.12), rgba(120, 150, 220, 0.16));
        --border-bright: light-dark(rgba(14, 165, 233, 0.35), rgba(120, 190, 255, 0.35));
        --text: light-dark(#0f172a, #dbe4f5);
        --muted: light-dark(#64748b, #7a8ba8);
        --text-soft: light-dark(#334155, #c8d6f0);
        --text-strong: light-dark(#0f172a, #eef4ff);
        --text-code: light-dark(#475569, #b7c4de);
        --accent-tag: light-dark(#0369a1, #8fb7dd);
        --term-fg: light-dark(#0e7490, #9ec9ea);
        --term-bg: light-dark(rgba(255, 255, 255, 0.92), rgba(7, 14, 28, 0.55));
        --input-bg: light-dark(rgba(255, 255, 255, 0.96), rgba(7, 14, 28, 0.55));
        --btn-secondary-bg: light-dark(rgba(255, 255, 255, 0.96), rgba(13, 19, 33, 0.88));
        --grid-line: light-dark(rgba(14, 116, 144, 0.08), rgba(120, 180, 255, 0.045));
        --grid-glow-a: light-dark(#dbeafe, #0d1b3a);
        --grid-glow-b: light-dark(#ede9fe, #1a0f33);
        --shadow: light-dark(rgba(15, 23, 42, 0.08), rgba(0, 0, 0, 0.35));
        --shadow-deep: light-dark(rgba(15, 23, 42, 0.12), rgba(0, 0, 0, 0.45));
        --ticker-bg: light-dark(rgba(255, 255, 255, 0.78), rgba(9, 14, 26, 0.6));
        --provenance-bg: light-dark(rgba(224, 242, 254, 0.55), rgba(13, 27, 58, 0.25));
        --chip-bg: light-dark(rgba(226, 232, 240, 0.9), rgba(44, 62, 110, 0.35));
        --chip-fg: light-dark(#334155, #c8d6f0);
        --chip-border: light-dark(rgba(148, 163, 184, 0.4), rgba(120, 150, 220, 0.22));
        --hop-bg: light-dark(rgba(226, 232, 240, 0.9), rgba(44, 62, 110, 0.35));
        --cb-val: light-dark(#1e293b, #dce6fa);
        --cb-track: light-dark(rgba(148, 163, 184, 0.18), rgba(120, 150, 220, 0.08));
        --mt-track: light-dark(rgba(148, 163, 184, 0.18), rgba(120, 150, 220, 0.1));
        --spark-dot-stroke: light-dark(#ffffff, #0b1120);
        --tab-active-bg: light-dark(rgba(14, 165, 233, 0.12), rgba(34, 211, 238, 0.1));
        --ok-fg: light-dark(#047857, #7ff0c6);
        --warn-fg: light-dark(#b45309, #ffd98a);
        --bad-fg: light-dark(#be123c, #ffb3c1);
        --conn-fact-v: light-dark(#334155, #d5def0);
        --glass-glow-border: light-dark(rgba(14, 165, 233, 0.22), rgba(120, 190, 255, 0.35));
        --gauge-track: light-dark(rgba(148, 163, 184, 0.22), rgba(120, 150, 220, 0.13));
      }

      .stApp {
        background:
          linear-gradient(var(--grid-line) 1px, transparent 1px),
          linear-gradient(90deg, var(--grid-line) 1px, transparent 1px),
          radial-gradient(1200px 700px at 15% -10%, var(--grid-glow-a) 0%, transparent 55%),
          radial-gradient(1000px 600px at 110% 20%, var(--grid-glow-b) 0%, transparent 50%),
          var(--bg);
        background-size: 100% 46px, 46px 100%, auto, auto, auto;
        color: var(--text);
        animation: gridDrift 32s linear infinite;
      }
      @keyframes gridDrift {
        from { background-position: 0 0, 0 0, 0 0, 0 0, 0 0; }
        to   { background-position: 0 460px, 460px 0, 0 0, 0 0, 0 0; }
      }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stToolbar"] { right: 1rem; }

      /* ---------- page rhythm (Streamlit stacks blocks tightly by default) ---------- */
      section.main > div.block-container {
        padding-top: 1.75rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 1180px;
      }
      [data-testid="stVerticalBlock"] { gap: 1.15rem; }
      [data-testid="stHorizontalBlock"] {
        align-items: stretch;
        gap: 1.35rem !important;
      }
      [data-testid="stTabs"] [data-testid="stVerticalBlock"] {
        gap: 1.25rem;
        padding-top: 0.85rem;
      }
      [data-testid="stMarkdownContainer"] p { margin-bottom: 0.65rem; }
      [data-testid="stCaptionContainer"] {
        margin-top: -0.15rem;
        margin-bottom: 0.65rem;
      }
      [data-testid="stSelectbox"],
      [data-testid="stToggle"],
      [data-testid="stButton"] { margin-bottom: 0.35rem; }
      [data-testid="stDataFrame"] { margin: 0.65rem 0 1.1rem; }
      div[data-testid="stExpander"] { margin: 0.5rem 0 0.85rem; }
      hr { margin: 1.75rem 0 !important; border-color: var(--border); }

      html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      .mono, code, pre { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace !important; }

      .hero { padding: 6px 0 2px; margin-bottom: 18px; }
      .hero .title { font-size: 42px; font-weight: 700; letter-spacing: -1px; line-height: 1.05;
                     background: var(--grad); -webkit-background-clip: text; background-clip: text;
                     -webkit-text-fill-color: transparent;
                     background-size: 240% 100%; animation: titleShift 11s ease-in-out infinite; }
      @keyframes titleShift { 0%,100% { background-position: 0% 50%; }
                              50%     { background-position: 100% 50%; } }
      .hero .tagline { color: var(--muted); font-size: 15px; margin-top: 6px; }
      .live { display:inline-flex; align-items:center; gap:8px; color: var(--green);
              font-size: 12px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; }
      .live .dot { width:8px; height:8px; border-radius:50%; background: var(--green);
                   box-shadow: 0 0 10px var(--green); animation: pulse 2s infinite; }
      @keyframes pulse { 0%,100% {opacity:1} 50% {opacity:.35} }

      .glass { background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
               padding: 16px 18px; backdrop-filter: blur(14px);
               box-shadow: 0 10px 40px var(--shadow); }
      .glass-glow { border-color: var(--glass-glow-border);
                    box-shadow: 0 0 0 1px var(--glass-glow-border), 0 0 34px var(--tab-active-bg); }
      .stack-pair { display:grid; grid-template-columns:1fr 1fr; gap:24px; align-items:stretch;
                    margin: 0 0 22px; }
      .stack-pair > .stack-card { height:100%; margin-bottom:0; padding: 20px 22px;
                                  display:flex; flex-direction:column; box-sizing:border-box; }
      .crew-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px 16px; margin: 4px 0 18px; }
      .crew-grid .crew-agent { margin-bottom:0; min-width:0; }
      .crew-grid .crew-agent summary { min-width:0; overflow:hidden; }

      /* Equal-height cards that wrap instead of squeezing on narrow screens. */
      .sgrid { display:grid; gap:16px; align-items:stretch; margin: 10px 0 22px;
               grid-template-columns: repeat(auto-fit, minmax(158px, 1fr)); }

      .stat { background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
              padding: 16px 20px; backdrop-filter: blur(14px); position: relative;
              overflow: hidden; transition: transform .25s ease, border-color .25s ease;
              animation: riseIn .6s cubic-bezier(.2,.8,.2,1) both;
              height:100%; display:flex; flex-direction:column; }
      .stat:hover { transform: translateY(-3px); border-color: var(--border-bright); }
      .stat::after { content:""; position:absolute; left:0; right:0; bottom:0; height:2px;
                     background: var(--grad); transform-origin: left;
                     animation: wipeIn 1.1s cubic-bezier(.2,.8,.2,1) both .15s; }
      @keyframes riseIn { from { opacity:0; transform: translateY(12px); } }
      @keyframes wipeIn { from { transform: scaleX(0); } }
      /* Two lines are reserved for every label so values share one baseline. */
      .stat .label { color: var(--muted); font-size: 11px; letter-spacing: 1.2px;
                     line-height: 1.25; min-height: 2.5em; text-transform: uppercase; }
      .stat .value { font-size: clamp(23px, 2.1vw, 30px); font-weight: 700;
                     line-height: 1.15; margin-top: 2px;
                     overflow-wrap: anywhere; }
      /* Pushed to the floor of the card so deltas line up across a row. */
      .stat .delta { font-size: 12px; color: var(--muted); margin-top: auto; padding-top: 4px; }
      .stat.accent .value { background: var(--grad); -webkit-background-clip:text;
                            background-clip:text; -webkit-text-fill-color:transparent; }

      .badge { display:inline-flex; align-items:center; justify-content:center;
               border-radius:10px; padding:8px 18px; font-weight:700;
               font-size:15px; letter-spacing:1px; line-height:1.1; color:#06121f; }
      .badge.approve { background: linear-gradient(120deg,#34d399,#22d3ee); }
      .badge.review { background: linear-gradient(120deg,#fbbf24,#fb923c); }
      .badge.reject { background: linear-gradient(120deg,#fb7185,#ef4444); }

      .chip { display:inline-flex; align-items:center; background: var(--chip-bg);
              color: var(--chip-fg); border:1px solid var(--chip-border); border-radius:999px;
              padding:4px 12px; margin:3px 8px 3px 0; font-size:12.5px; line-height:1.25; }
      .chip.ok { background: rgba(52,211,153,.14); color: var(--ok-fg); border-color: rgba(52,211,153,.35); }
      .chip.warn { background: rgba(251,191,36,.13); color: var(--warn-fg); border-color: rgba(251,191,36,.35); }
      .chip.bad { background: rgba(251,113,133,.13); color: var(--bad-fg); border-color: rgba(251,113,133,.35); }

      .gap-hint { background: rgba(251,191,36,.10); border:1px solid rgba(251,191,36,.38);
                  border-radius:16px; padding:14px 16px 14px 18px; margin: 8px 0 4px;
                  box-shadow: 0 0 0 1px rgba(251,191,36,.06); }
      .gap-hint .gap-kicker { color: var(--warn-fg); font-size:10.5px; font-weight:700;
                              letter-spacing:1.6px; text-transform:uppercase; margin-bottom:6px; }
      .gap-hint .gap-title { font-size:15px; font-weight:700; line-height:1.35; margin-bottom:6px; }
      .gap-hint .gap-body { color: var(--text-soft); font-size:13.5px; line-height:1.5; }
      .gap-hint .gap-fix { margin-top:10px; font-size:13.5px; line-height:1.5; color: var(--text-strong); }
      .gap-hint .gap-fix b { color: var(--warn-fg); }
      .gap-suggest { margin-top:12px; padding-top:12px; border-top:1px dashed rgba(251,191,36,.35); }
      .gap-suggest .gs-kicker { color: var(--ok-fg); font-size:10.5px; font-weight:700;
                                letter-spacing:1.4px; text-transform:uppercase; margin-bottom:6px; }
      .gap-suggest .gs-key { font-family:'JetBrains Mono',monospace; font-size:14px; font-weight:700;
                             color: var(--text-strong); }
      .gap-suggest .gs-title { font-size:14px; margin-top:3px; color: var(--text-strong); }
      .gap-suggest .gs-why { margin-top:6px; font-size:13px; line-height:1.5; color: var(--text-soft); }
      .gap-suggest .gs-alts { margin-top:8px; font-size:12.5px; color: var(--muted); }
      .gap-howto h3 { font-size:16px; margin: 4px 0 8px; }
      .gap-howto p, .gap-howto li { font-size:14px; line-height:1.55; color: var(--text-soft); }
      .gap-howto ol { padding-left: 1.2rem; }
      .gap-howto code { font-family:'JetBrains Mono',monospace; font-size:12px; }
      div[data-testid="stPopover"] button[kind="secondary"] {
        width: 42px; height: 42px; min-height: 42px !important; border-radius: 999px !important;
        font-weight: 800; font-size: 18px; font-style: italic; letter-spacing: 0;
        border: 1px solid rgba(251,191,36,.45) !important;
        background: rgba(251,191,36,.16) !important; color: var(--warn-fg) !important;
      }

      .kicker { color: var(--muted); font-size:11px; font-weight:700; letter-spacing:2.5px;
                text-transform: uppercase; margin: 30px 0 12px; }
      .kicker:first-of-type { margin-top: 10px; }
      .section-title { font-size:20px; font-weight:600; margin: 6px 0 14px; }
      .section-note { color:var(--muted); font-size:12.5px; margin: -6px 0 16px; line-height:1.5; }

      .pr-head { display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; }
      .pr-head .num { font-size:26px; font-weight:800;
                      background: var(--grad); -webkit-background-clip:text; background-clip:text;
                      -webkit-text-fill-color:transparent; }
      .pr-head .title { font-size:17px; font-weight:600; }
      .pr-head .meta { color: var(--muted); font-size:13px; }

      .agent { background: var(--panel); border:1px solid var(--border); border-radius:12px;
               padding: 0; margin-bottom: 8px; backdrop-filter: blur(10px);
               border-left-width:3px; }
      .agent.ok { border-left-color: var(--green); }
      .agent.warn { border-left-color: var(--amber); }
      .agent.bad { border-left-color: var(--rose); }
      .agent summary { display:flex; align-items:center; gap:8px; cursor:pointer;
                       list-style:none; padding: 9px 14px; min-height: 38px;
                       white-space:nowrap; overflow:hidden; }
      .agent summary::-webkit-details-marker { display:none; }
      .agent summary::before,
      .crew-agent summary::before {
        content:"";
        width:12px; height:12px; flex-shrink:0;
        background-color: currentColor;
        -webkit-mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M9 5.5v13l9.5-6.5z'/%3E%3C/svg%3E") center / 11px 11px no-repeat;
        mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='black' d='M9 5.5v13l9.5-6.5z'/%3E%3C/svg%3E") center / 11px 11px no-repeat;
      }
      .agent[open] summary::before,
      .crew-agent[open] summary::before { transform: rotate(90deg); }
      .crew-agent { background: var(--panel); border:1px solid var(--border); border-radius:12px;
                    padding: 0; margin-bottom: 8px; backdrop-filter: blur(10px); }
      .crew-agent summary { display:flex; align-items:center; gap:8px; cursor:pointer;
                            list-style:none; padding: 10px 14px; min-height: 40px;
                            line-height:1.2; color: var(--text); }
      .crew-agent summary::-webkit-details-marker { display:none; }
      .crew-agent .crew-title { font-weight:600; font-size:13.5px; line-height:1.2; }
      .crew-agent .crew-dot { color: var(--muted); line-height:1; }
      .crew-agent .crew-id { background: rgba(255,255,255,.06); border-radius:6px;
                             padding: 2px 7px; font-size:12.5px; line-height:1;
                             display:inline-flex; align-items:center;
                             color: var(--text-code); font-family:'JetBrains Mono', monospace; }
      .crew-agent .crew-body { padding: 2px 14px 12px 36px; color: var(--muted);
                               font-size:13px; line-height:1.45; }
      .agent .role { display:flex; align-items:center; gap:8px; font-weight:600; font-size:13px;
                     flex-shrink:0; min-width: 118px; }
      .agent .role .tick { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
      .agent.ok .tick { background: var(--green); box-shadow:0 0 8px var(--green); }
      .agent.warn .tick { background: var(--amber); box-shadow:0 0 8px var(--amber); }
      .agent.bad .tick { background: var(--rose); box-shadow:0 0 8px var(--rose); }
      .agent .one { flex:1; min-width:0; overflow:hidden; text-overflow:ellipsis;
                    white-space:nowrap; color: var(--text-code); font-size:12.5px;
                    font-family:'JetBrains Mono', monospace; }
      .agent .out { color: var(--text-code); font-size:12.5px; margin: 0 14px 10px;
                    padding-top: 2px; border-top:1px solid var(--border);
                    white-space:pre-wrap; font-family:'JetBrains Mono', monospace;
                    line-height:1.45; max-height: 220px; overflow:auto; }

      .chain { display:flex; align-items:center; flex-wrap:wrap; gap:10px;
                margin: 6px 0 18px; }
      .chain .hop { background: var(--hop-bg); border:1px solid var(--border);
                    border-radius:12px; padding:7px 14px; font-weight:600; font-size:13.5px; }
      .chain .hop.ok { border-color: rgba(52,211,153,.5); color: var(--ok-fg); }
      .chain .hop.warn { border-color: rgba(251,191,36,.5); color: var(--warn-fg); }
      .chain .hop.bad { border-color: rgba(251,113,133,.5); color: var(--bad-fg); }
      .chain .hop.dist { font-weight:400; font-size:11px; opacity:.7; }
      .chain .arr { color: var(--muted); font-weight:700; }

      .provenance { border:1px dashed var(--border-bright); border-radius:14px;
                    padding: 16px 20px; background: var(--provenance-bg); margin-bottom: 8px; }
      .provenance .q { color: var(--accent-tag); font-size:12px; font-family:'JetBrains Mono',monospace;
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
      div[data-testid="stExpander"] details > summary {
        font-weight:600;
        display:flex !important;
        align-items:center !important;
      }
      div[data-testid="stExpander"] summary > span {
        display:flex !important;
        align-items:center !important;
      }
      div[data-testid="stExpander"] summary > span > *:first-child {
        display:inline-flex !important;
        align-items:center !important;
        justify-content:center !important;
        line-height:1 !important;
        margin:0 !important;
        transform: translateY(1px);
      }
      div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
      div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p,
      div[data-testid="stExpander"] summary p {
        margin:0 !important;
        line-height:1.3 !important;
      }
      div[data-testid="stExpander"] summary code {
        line-height:1.3 !important;
        vertical-align:middle;
      }
      .stTabs [data-baseweb="tab-list"] { gap: 6px; }
      .stTabs [data-baseweb="tab"] { border-radius: 10px 10px 0 0; }
      .stTabs [aria-selected="true"] { background: var(--tab-active-bg); }

      [data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:12px;
                                    overflow:hidden; }

      /* Streamlit buttons — label text often sits in nested <p> tags and misaligns */
      [data-testid="stButton"] button,
      [data-testid="stFormSubmitButton"] button,
      [data-testid="stDownloadButton"] button {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        font-weight: 600 !important;
        font-size: 0.92rem !important;
        line-height: 1.2 !important;
        letter-spacing: 0.01em;
        border-radius: 10px !important;
        padding: 0.58rem 1.15rem !important;
        min-height: 2.55rem;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        white-space: nowrap;
      }
      [data-testid="stButton"] button p,
      [data-testid="stFormSubmitButton"] button p,
      [data-testid="stDownloadButton"] button p,
      [data-testid="stButton"] button div[data-testid="stMarkdownContainer"],
      [data-testid="stFormSubmitButton"] button div[data-testid="stMarkdownContainer"] {
        margin: 0 !important;
        padding: 0 !important;
        line-height: 1.2 !important;
        font-size: inherit !important;
        font-weight: inherit !important;
        color: inherit !important;
      }
      [data-testid="stButton"] button[kind="primary"],
      [data-testid="stFormSubmitButton"] button[kind="primary"],
      button[kind="primary"] {
        background: var(--grad) !important;
        color: #06121f !important;
        border: none !important;
        box-shadow: 0 0 0 1px rgba(34,211,238,.12);
      }
      [data-testid="stButton"] button[kind="primary"]:hover,
      [data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
      button[kind="primary"]:hover { filter: brightness(1.08); }
      [data-testid="stButton"] button:not([kind="primary"]),
      [data-testid="stFormSubmitButton"] button:not([kind="primary"]) {
        background: var(--btn-secondary-bg) !important;
        color: var(--text) !important;
        border: 1px solid var(--border-bright) !important;
      }
      [data-testid="stButton"] button:disabled,
      [data-testid="stFormSubmitButton"] button:disabled {
        opacity: 0.45;
      }

      .stProgress > div > div > div { background: var(--grad); }
      hr { border-color: var(--border); }

      /* ---------- futuristic telemetry deck ---------- */
      .panel { position:relative; border:1px solid var(--border); border-radius:18px;
               padding:18px 20px 16px; margin-bottom:20px; overflow:hidden;
               background: linear-gradient(160deg, var(--panel), var(--panel-solid));
               box-shadow: 0 14px 44px var(--shadow-deep);
               animation: riseIn .65s cubic-bezier(.2,.8,.2,1) both; }
      /* travelling scanline along the top edge */
      .panel::after { content:""; position:absolute; top:0; left:0; width:45%; height:1px;
                      background: linear-gradient(90deg, transparent, rgba(120,200,255,.75), transparent);
                      animation: scanX 4.2s ease-in-out infinite; }
      @keyframes scanX { 0% { transform: translateX(-110%); }
                         55%,100% { transform: translateX(240%); } }
      /* slow diagonal sheen sweeping the glass */
      .panel::before { content:""; position:absolute; top:0; bottom:0; left:-55%; width:42%;
                       pointer-events:none; transform: skewX(-14deg);
                       background: linear-gradient(100deg, transparent,
                                   rgba(150,205,255,.075), transparent);
                       animation: sheen 8s ease-in-out infinite; }
      @keyframes sheen { 0%,58% { left:-55%; } 100% { left:135%; } }
      .panel.tall { min-height: 268px; }
      .panel-head { display:flex; align-items:center; gap:12px; margin-bottom:16px;
                    flex-wrap:wrap; }
      .panel-title { font-size:14px; font-weight:600; letter-spacing:.2px; line-height:1.3; }
      .panel-sub { color:var(--muted); font-size:11.5px; min-width:0; line-height:1.35; }
      .panel-tag { margin-left:auto; flex:0 0 auto; font-size:10px; font-weight:700;
                   letter-spacing:1.4px; line-height:1.2;
                   text-transform:uppercase; color: var(--accent-tag); border:1px solid var(--border);
                   border-radius:999px; padding:5px 10px; display:inline-flex; align-items:center; }
      /* Body fills the leftover height so charts centre and panel floors line up. */
      .panel-body { flex:1 1 auto; min-width:0; display:flex; flex-direction:column;
                    justify-content:center; }

      /* Panels in a row: equal height, and they wrap rather than shrink to nothing. */
      .pgrid { display:grid; gap:22px; align-items:stretch; margin: 8px 0 24px;
               grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); }
      .pgrid > .panel { height:100%; margin-bottom:0; display:flex; flex-direction:column; }
      .pgrid.r-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .pgrid.r-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .pgrid.r-narrow-wide { grid-template-columns: minmax(0, 1fr) minmax(0, 1.5fr); }

      .gauge-wrap { display:flex; justify-content:center; }
      .gauge { width:100%; max-width:280px; overflow:visible; }
      .gauge .gnum { font-family:'Plus Jakarta Sans',sans-serif; font-weight:700; font-size:32px;
                     fill: var(--text-strong); }
      .gauge .gsuf { font-family:'Plus Jakarta Sans',sans-serif; font-weight:600; font-size:15px;
                     fill: var(--muted); baseline-shift: super; }
      .gauge .gcap { font-family:'Plus Jakarta Sans',sans-serif; font-weight:600; font-size:10px;
                     fill: var(--muted); letter-spacing:1.6px; }
      .gauge .glabel { font-family:'Plus Jakarta Sans',sans-serif; font-weight:600; font-size:8.5px;
                       fill: var(--muted); }
      .gauge .gneedle { fill: #d4d4d8; filter: drop-shadow(0 1px 2px rgba(0,0,0,.35)); }
      .gauge .ghub { fill: #f4f4f5; stroke-width: 2; }
      @keyframes gaugeFill { from { stroke-dashoffset: var(--dash-len); }
                             to   { stroke-dashoffset: var(--dash-off); } }
      .gauge .val { animation: gaugeFill 1.35s cubic-bezier(.2,.8,.2,1) both,
                               ringBreathe 3.4s ease-in-out 1.35s infinite; }
      @keyframes ringBreathe { 0%,100% { opacity:1; } 50% { opacity:.74; } }
      .gauge .ghalo { transform-box: fill-box; transform-origin: center;
                      animation: haloPulse 3.6s ease-in-out infinite; }
      @keyframes haloPulse { 0%,100% { opacity:.18; transform: scale(1); }
                             50%     { opacity:.06; transform: scale(1.1); } }
      .gauge .gtip { transform-box: fill-box; transform-origin: center;
                     fill: #fecaca;
                     animation: tipPulse 1.9s ease-in-out .9s infinite; }
      .gauge .gtip-halo { transform-box: fill-box; transform-origin: center;
                          animation: tipRing 1.9s ease-out .9s infinite; }
      @keyframes tipPulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.28); } }
      @keyframes tipRing { 0% { opacity:.55; transform: scale(.7); }
                           100% { opacity:0; transform: scale(2.5); } }
      .gauge-foot { text-align:center; color:var(--muted); font-size:12px;
                    margin-top:8px; line-height:1.45; padding: 0 6px; }

      .cb { display:flex; align-items:flex-end; gap:10px; }
      .cb-item { flex:1; min-width:0; text-align:center; }
      .cb-val { font-size:13px; font-weight:700; color: var(--cb-val); margin-bottom:5px; }
      .cb-track { position:relative; height:104px; border-radius:9px;
                  background: var(--cb-track); overflow:hidden; }
      .panel.tall .cb-track { height:150px; }
      .cb-fill { position:absolute; left:0; right:0; bottom:0; border-radius:9px; overflow:hidden;
                 animation: barGrow 1.05s cubic-bezier(.2,.8,.2,1) both; }
      @keyframes barGrow { from { height:0; } }
      /* light pulse riding the top cap of each bar */
      .cb-fill::after { content:""; position:absolute; left:0; right:0; top:0; height:38%;
                        background: linear-gradient(180deg, rgba(255,255,255,.42), transparent);
                        animation: capGlow 2.8s ease-in-out infinite; }
      @keyframes capGlow { 0%,100% { opacity:.35; } 50% { opacity:.9; } }
      .cb-lab { color:var(--muted); font-size:10.5px; margin-top:7px; white-space:nowrap;
                overflow:hidden; text-overflow:ellipsis; }

      .mt { margin-bottom:14px; }
      .mt:last-child { margin-bottom:0; }
      .mt-top { display:flex; justify-content:space-between; align-items:baseline;
                font-size:12.5px; margin-bottom:5px; color: var(--text-soft); gap:10px; }
      .mt-top b { color: var(--text-strong); font-family:'JetBrains Mono',monospace; font-size:12px; }
      .mt-track { height:8px; border-radius:999px; background: var(--mt-track); overflow:hidden; }
      .mt-fill { position:relative; height:100%; border-radius:999px; overflow:hidden;
                 animation: mtGrow 1.15s cubic-bezier(.2,.8,.2,1) both; }
      @keyframes mtGrow { from { width:0; } }
      /* shine travelling down each meter */
      .mt-fill::after { content:""; position:absolute; top:0; bottom:0; width:36%; left:-36%;
                        background: linear-gradient(90deg, transparent,
                                    rgba(255,255,255,.5), transparent);
                        animation: mtShine 2.9s linear infinite; }
      @keyframes mtShine { to { left:120%; } }

      .spark { width:100%; display:block; overflow:visible; }
      .spark .sline { fill:none; stroke-width:2.2; stroke-linecap:round; stroke-linejoin:round;
                      animation: drawLine 1.7s cubic-bezier(.3,.7,.2,1) both; }
      @keyframes drawLine { from { stroke-dashoffset: var(--len); } to { stroke-dashoffset: 0; } }
      .spark .sarea { animation: fadeIn .9s ease-out 1.1s both; }
      @keyframes fadeIn { from { opacity:0; } }
      .spark .sdot { stroke: var(--spark-dot-stroke); stroke-width:2; transform-box: fill-box;
                     transform-origin: center;
                     animation: fadeIn .4s 1.5s both, tipPulse 2s ease-in-out 1.6s infinite; }
      .spark .sdot-halo { transform-box: fill-box; transform-origin: center;
                          animation: tipRing 2s ease-out 1.6s infinite; }
      /* vertical scan bar sweeping the plot */
      .spark .sscan { animation: scanSweep 5.5s ease-in-out 1.6s infinite; }
      @keyframes scanSweep { 0% { opacity:0; transform: translateX(0); }
                             12%,78% { opacity:1; }
                             100% { opacity:0; transform: translateX(284px); } }

      /* continuously scrolling telemetry strip */
      .ticker { position:relative; overflow:hidden; margin:16px 0 22px; padding:11px 0;
                border:1px solid var(--border); border-radius:12px;
                background: var(--ticker-bg);
                mask-image: linear-gradient(90deg, transparent, #000 7%, #000 93%, transparent);
                -webkit-mask-image: linear-gradient(90deg, transparent, #000 7%, #000 93%, transparent); }
      .ticker-track { display:inline-flex; white-space:nowrap; will-change:transform;
                      animation: tickerRoll 42s linear infinite; }
      .ticker:hover .ticker-track { animation-play-state: paused; }
      @keyframes tickerRoll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
      .tk { display:inline-flex; align-items:center; gap:8px; padding:0 22px;
            font-size:12.5px; color: var(--text-soft); }
      .tk b { font-family:'JetBrains Mono',monospace; font-size:12px; color: var(--text-strong); }
      .tk i { width:7px; height:7px; border-radius:50%; background:var(--cyan);
              box-shadow:0 0 9px var(--cyan); animation: pulse 2.2s infinite; }
      .tk.ok i { background:var(--green); box-shadow:0 0 9px var(--green); }
      .tk.warn i { background:var(--amber); box-shadow:0 0 9px var(--amber); }
      .tk.bad i { background:var(--rose); box-shadow:0 0 9px var(--rose); }
      .tk s { color:var(--muted); text-decoration:none; letter-spacing:1.4px;
              text-transform:uppercase; font-size:10px; }

      .agent .tick { animation: pulse 2.4s infinite; }
      .chip.bad { animation: alertPulse 2.6s ease-in-out infinite; }
      @keyframes alertPulse { 0%,100% { box-shadow: 0 0 0 0 rgba(251,113,133,0); }
                              50% { box-shadow: 0 0 0 4px rgba(251,113,133,.12); } }

      /* ---------- responsive layout ---------- */

      @media (max-width: 1180px) {
        .pgrid.r-3 { grid-template-columns: repeat(auto-fit, minmax(258px, 1fr)); }
        /* Wider minimum so a six-card row breaks 3+3 rather than 5+1. */
        .sgrid { grid-template-columns: repeat(auto-fit, minmax(196px, 1fr)); }
      }
      @media (max-width: 900px) {
        .pgrid, .pgrid.r-2, .pgrid.r-3, .pgrid.r-narrow-wide {
          grid-template-columns: minmax(0, 1fr); }
        /* Columns that hold real widgets can't become grids, so stack them here. */
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        [data-testid="stColumn"] { flex: 1 1 100% !important; min-width: 100% !important; }
      }
      @media (max-width: 640px) {
        .block-container { padding-left: 1rem !important; padding-right: 1rem !important; }
        .sgrid { grid-template-columns: repeat(auto-fit, minmax(132px, 1fr)); gap: 11px; }
        .stat { padding: 12px 14px; }
        .panel { padding: 14px 14px 12px; }
        .gauge { max-width: 208px; }
        .cb-lab { font-size: 9.5px; }
      }

      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { animation: none !important; transition: none !important; }
      }

      .verdict-panel { text-align:center; display:flex; flex-direction:column;
                       align-items:center; justify-content:center; gap:12px;
                       min-height:268px; padding: 8px 12px; }
      .verdict-panel .badge { font-size:22px; padding:10px 30px; border-radius:14px; }
      .verdict-panel .vlabel { color:var(--muted); font-size:10.5px; letter-spacing:2.2px;
                               text-transform:uppercase; line-height:1.2; margin-bottom:4px; }
      .verdict-panel .vsub { color: var(--text-soft); font-size:13px; }

      .conn-card { background: var(--panel); border:1px solid var(--border); border-radius:18px;
                   padding: 18px 20px 16px; backdrop-filter: blur(14px); margin-bottom: 12px;
                   box-shadow: 0 10px 40px var(--shadow); position:relative; overflow:hidden;
                   min-height: 205px; display:flex; flex-direction:column; }
      .conn-card::before { content:""; position:absolute; inset:0 auto 0 0; width:3px; }
      .conn-card.ok::before { background: var(--green); }
      .conn-card.warn::before { background: var(--amber); }
      .conn-card.bad::before { background: var(--rose); }
      .conn-card.ok { border-color: rgba(52,211,153,.28);
                      box-shadow: 0 0 0 1px rgba(52,211,153,.08), 0 10px 40px var(--shadow); }
      .conn-head { display:flex; align-items:center; gap:12px; margin-bottom: 12px; }
      .conn-glyph { width:42px; height:42px; border-radius:12px; display:flex; align-items:center;
                    justify-content:center; flex-shrink:0; }
      .conn-glyph .conn-icon { width:22px; height:22px; display:block; }
      .conn-glyph.gh { background:#24292f; }
      .conn-glyph.jira { background:#0052CC; }
      .conn-glyph.jenkins { background:#D24939; }
      .conn-glyph.teams { background:#6264A7; }
      .conn-name { font-weight:700; font-size:16px; }
      .conn-via { color: var(--muted); font-size:12px; margin-top:1px; }
      .conn-pill { margin-left:auto; border-radius:999px; padding:5px 12px; font-size:11px;
                   font-weight:700; letter-spacing:.8px; line-height:1.1;
                   text-transform:uppercase; display:inline-flex; align-items:center; white-space:nowrap; }
      .conn-pill.ok { background: rgba(52,211,153,.16); color: var(--ok-fg); border:1px solid rgba(52,211,153,.35); }
      .conn-pill.warn { background: rgba(251,191,36,.14); color: var(--warn-fg); border:1px solid rgba(251,191,36,.35); }
      .conn-pill.bad { background: rgba(251,113,133,.14); color: var(--bad-fg); border:1px solid rgba(251,113,133,.35); }
      .conn-headline { font-size:20px; font-weight:700; letter-spacing:-.3px; margin: 2px 0 10px;
                       background: var(--grad); -webkit-background-clip:text; background-clip:text;
                       -webkit-text-fill-color:transparent; }
      .conn-facts { display:grid; grid-template-columns: 1fr 1fr; gap:8px 14px; margin-bottom: 12px; }
      .conn-fact .k { color: var(--muted); font-size:10px; letter-spacing:1.2px; text-transform:uppercase; }
      .conn-fact .v { font-size:13px; margin-top:2px; color: var(--conn-fact-v); }
      .term { font-family:'JetBrains Mono', monospace; font-size:11.5px; color: var(--term-fg);
              background: var(--term-bg); border:1px dashed var(--border-bright);
              border-radius:10px; padding:8px 12px; overflow:auto; white-space:nowrap; }
      .conn-err { margin-top:10px; color: var(--bad-fg); font-size:12.5px; }

      .stTextInput input, .stSelectbox [data-baseweb="select"] > div {
        background: var(--input-bg) !important; border-radius:10px !important;
      }
      [data-testid="stToggle"] label,
      [data-testid="stSelectbox"] label,
      [data-testid="stTextInput"] label {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        font-size: 0.92rem !important;
        line-height: 1.35 !important;
      }
      [data-testid="stToggle"] label p,
      [data-testid="stSelectbox"] label p,
      [data-testid="stTextInput"] label p {
        margin: 0 !important;
        line-height: 1.35 !important;
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
    ("Security Analyst", "Security"),
    ("Blast Radius Analyst", "Blast Radius"),
    ("Risk Analyzer", "Risk Analyzer"),
    ("Test Selector", "Test Selector"),
    ("Deployment Advisor", "Deployment"),
    ("AEGIS Release Orchestrator", "Orchestrator"),
]

GLOSSARY = {
    "Hops": "Distance upstream from the changed services, walked over DEPENDS_ON edges (0 = changed service).",
    "Routes": "API routes exposed by a service that could be affected.",
    "Customer flows": "End-to-end customer journeys that touch at-risk services.",
    "Tests": "Automated tests covering files owned by that service.",
    "Past incidents": "Incidents previously logged against the service.",
    "Safe-to-merge score": "min(98%, 100% − Risk Score). Higher means safer to ship.",
    "Risk Score": "Sum of PR Reviewer + Security + Blast Radius + Risk Analyzer + Test Selector, capped at 98%.",
    "Alignment": "Whether changed files match the Jira stories they claim to implement.",
    "Story epic": "The business capability a Jira story belongs to (Payments, Commerce, Platform).",
    "RELEASED_IN": "Relationship between a microservice and the release version it shipped in.",
    "DETECTS": "Relationship between a test case and the incident it would have caught.",
    "Security": "Security Analyst signal: PASS (clear), REVIEW (human security look needed), FAIL (block).",
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
        f'<div class="glass glass-glow stack-card">'
        f'<div style="font-weight:600;margin-bottom:8px">{html_escape(title)}</div>'
        f"{''.join(parts)}</div>"
    )


def stat_html(label: str, value: str, delta: str = "", accent: bool = False) -> str:
    delta_html = f'<div class="delta">{delta}</div>' if delta else ""
    return (
        f'<div class="stat {"accent" if accent else ""}">'
        f'<div class="label">{label}</div><div class="value">{value}</div>{delta_html}</div>'
    )


RAMPS = {
    "info": ("#22d3ee", "#a78bfa"),
    "ok": ("#059669", "#34d399"),
    "warn": ("#fbbf24", "#fb923c"),
    "bad": ("#9f1239", "#ef4444"),
    "violet": ("#a78bfa", "#f472b6"),
    "red": ("#9f1239", "#ef4444"),
}
GAUGE_THEME = {
    "ok": ("rgba(6,78,59,.45)", "rgba(16,185,129,.32)", "#047857"),
    "red": ("rgba(127,29,29,.45)", "rgba(180,60,70,.28)", "#9f1239"),
    "bad": ("rgba(127,29,29,.45)", "rgba(180,60,70,.28)", "#9f1239"),
    "warn": ("rgba(120,53,15,.45)", "rgba(251,191,36,.30)", "#b45309"),
}
GAUGE_START = 150.0
GAUGE_SWEEP = 240.0
GAUGE_RADIUS = 70.0
GAUGE_CX, GAUGE_CY = 110.0, 118.0
# Equal visual spacing (speed-test style): low values stretched, high values compressed.
GAUGE_TICKS = (0, 5, 10, 20, 35, 50, 70, 85, 100)
_uid_counter = itertools.count()


def score_variant(percent: float, *, invert: bool = False) -> str:
    """Traffic-light variant for a 0-100 score (invert for 'lower is better')."""
    value = 100.0 - percent if invert else percent
    if value >= 75:
        return "ok"
    if value >= 45:
        return "warn"
    return "bad"


def _polar(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    rad = math.radians(degrees)
    return cx + radius * math.cos(rad), cy + radius * math.sin(rad)


def _arc_path(cx: float, cy: float, radius: float, start: float, end: float) -> str:
    x1, y1 = _polar(cx, cy, radius, start)
    x2, y2 = _polar(cx, cy, radius, end)
    large = 1 if abs(end - start) > 180 else 0
    return f"M {x1:.2f} {y1:.2f} A {radius:.2f} {radius:.2f} 0 {large} 1 {x2:.2f} {y2:.2f}"


def _gauge_frac(value: float) -> float:
    """Map 0–100 onto the dial with non-linear (speed-test) spacing."""
    v = max(0.0, min(100.0, float(value)))
    ticks = GAUGE_TICKS
    span = float(len(ticks) - 1)
    for i in range(1, len(ticks)):
        lo, hi = float(ticks[i - 1]), float(ticks[i])
        if v <= hi:
            t = 0.0 if hi == lo else (v - lo) / (hi - lo)
            return (i - 1 + t) / span
    return 1.0


def gauge_html(
    percent: float,
    caption: str,
    *,
    display: str | None = None,
    suffix: str = "%",
    variant: str | None = None,
    foot: str = "",
) -> str:
    """Non-linear 0–100 radial gauge (speed-test layout, needle)."""
    key = variant if variant in RAMPS else "red"
    frac = _gauge_frac(percent)
    start, stop = RAMPS[key]
    track_stroke, tick_off, hub = GAUGE_THEME.get(key, GAUGE_THEME["red"])
    uid = f"gg{next(_uid_counter)}"
    cx, cy, radius = GAUGE_CX, GAUGE_CY, GAUGE_RADIUS
    track = _arc_path(cx, cy, radius, GAUGE_START, GAUGE_START + GAUGE_SWEEP)
    length = 2 * math.pi * radius * (GAUGE_SWEEP / 360.0)
    offset = length * (1.0 - frac)
    angle = GAUGE_START + GAUGE_SWEEP * frac

    ticks = []
    n_major = len(GAUGE_TICKS)
    for i, label in enumerate(GAUGE_TICKS):
        degrees = GAUGE_START + GAUGE_SWEEP * (i / (n_major - 1))
        x1, y1 = _polar(cx, cy, radius + 8, degrees)
        x2, y2 = _polar(cx, cy, radius + 16, degrees)
        lx, ly = _polar(cx, cy, radius + 26, degrees)
        lit = i / (n_major - 1) <= frac + 1e-9
        color = stop if lit else tick_off
        ticks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="2.4" stroke-linecap="round"/>'
        )
        ticks.append(
            f'<text class="glabel" x="{lx:.1f}" y="{ly:.1f}" text-anchor="middle" '
            f'dominant-baseline="middle">{label}</text>'
        )
        if i < n_major - 1:
            for k in (1, 2):
                minor = GAUGE_START + GAUGE_SWEEP * ((i + k / 3) / (n_major - 1))
                mx1, my1 = _polar(cx, cy, radius + 8, minor)
                mx2, my2 = _polar(cx, cy, radius + 12, minor)
                ticks.append(
                    f'<line x1="{mx1:.1f}" y1="{my1:.1f}" x2="{mx2:.1f}" y2="{my2:.1f}" '
                    f'stroke="{tick_off}" stroke-width="1.4" '
                    f'stroke-linecap="round"/>'
                )

    tip_x, tip_y = _polar(cx, cy, radius, angle)
    nx, ny = _polar(cx, cy, radius - 6, angle)
    tail_x, tail_y = _polar(cx, cy, 10, angle + 180)
    b1x, b1y = _polar(cx, cy, 3.2, angle + 90)
    b2x, b2y = _polar(cx, cy, 3.2, angle - 90)
    readout = display if display is not None else f"{float(percent):.0f}"
    return (
        '<div class="gauge-wrap"><svg class="gauge" viewBox="0 0 220 210" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="{uid}" x1="0" y1="1" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{stop}"/>'
        f'</linearGradient>'
        f'<radialGradient id="{uid}h">'
        f'<stop offset="0" stop-color="{stop}" stop-opacity=".5"/>'
        f'<stop offset="1" stop-color="{stop}" stop-opacity="0"/>'
        f'</radialGradient>'
        f'<filter id="{uid}b" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur stdDeviation="4.5" result="blur"/>'
        f'<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter></defs>'
        f'<circle class="ghalo" cx="{cx:.0f}" cy="{cy:.0f}" r="52" fill="url(#{uid}h)"/>'
        f"{''.join(ticks)}"
        f'<path class="gauge-track" d="{track}" fill="none" '
        f'stroke="{track_stroke}" stroke-width="14" stroke-linecap="round"/>'
        f'<path class="val" d="{track}" fill="none" stroke="url(#{uid})" stroke-width="14" '
        f'stroke-linecap="round" filter="url(#{uid}b)" '
        f'stroke-dasharray="{length:.2f}" stroke-dashoffset="{offset:.2f}" '
        f'style="--dash-len:{length:.2f};--dash-off:{offset:.2f}"/>'
        f'<circle class="gtip-halo" cx="{tip_x:.2f}" cy="{tip_y:.2f}" r="7" fill="{stop}"/>'
        f'<polygon class="gneedle" points="'
        f'{nx:.1f},{ny:.1f} {b1x:.1f},{b1y:.1f} {tail_x:.1f},{tail_y:.1f} {b2x:.1f},{b2y:.1f}"/>'
        f'<circle class="ghub" cx="{cx:.0f}" cy="{cy:.0f}" r="6.5" '
        f'style="stroke:{hub}"/>'
        f'<text class="gnum" x="{cx:.0f}" y="{cy + 48:.0f}" text-anchor="middle">'
        f'{html_escape(readout)}'
        f'<tspan class="gsuf" dx="3" dy="-0.15em">{html_escape(suffix)}</tspan></text>'
        f'<text class="gcap" x="{cx:.0f}" y="{cy + 66:.0f}" text-anchor="middle">'
        f'{html_escape(caption)}</text>'
        '</svg></div>'
        + (f'<div class="gauge-foot">{html_escape(foot)}</div>' if foot else "")
    )


def bars_html(items: list[tuple[str, float]], *, variant: str = "info") -> str:
    """Vertical bar chart driven by CSS heights (no plotting dependency)."""
    if not items:
        return '<div style="color:var(--muted);font-size:12.5px">No data in the graph yet.</div>'
    start, stop = RAMPS.get(variant, RAMPS["info"])
    peak = max((float(v) for _, v in items), default=0.0) or 1.0
    cells = []
    for index, (label, value) in enumerate(items):
        height = max(3.0, float(value) / peak * 100.0)
        delay = index * 0.09
        cells.append(
            '<div class="cb-item">'
            f'<div class="cb-val">{value:g}</div>'
            f'<div class="cb-track"><div class="cb-fill" style="height:{height:.1f}%;'
            f'animation-delay:{delay:.2f}s;'
            f'background:linear-gradient(180deg,{stop},{start})"></div></div>'
            f'<div class="cb-lab" title="{html_escape(str(label))}">'
            f'{html_escape(str(label))}</div></div>'
        )
    return f'<div class="cb">{"".join(cells)}</div>'


def meters_html(items: list[tuple[str, float]], *, variant: str = "violet", unit: str = "") -> str:
    """Horizontal ranked meters, largest value normalised to full width."""
    if not items:
        return '<div style="color:var(--muted);font-size:12.5px">Nothing to show.</div>'
    start, stop = RAMPS.get(variant, RAMPS["violet"])
    peak = max((float(v) for _, v in items), default=0.0) or 1.0
    rows = []
    for index, (label, value) in enumerate(items):
        width = max(2.0, float(value) / peak * 100.0)
        delay = index * 0.1
        rows.append(
            '<div class="mt"><div class="mt-top">'
            f'<span>{html_escape(str(label))}</span><b>{value:g}{html_escape(unit)}</b></div>'
            f'<div class="mt-track"><div class="mt-fill" style="width:{width:.1f}%;'
            f'animation-delay:{delay:.2f}s;'
            f'background:linear-gradient(90deg,{start},{stop})"></div></div></div>'
        )
    return "".join(rows)


def sparkline_html(values: list[float], *, variant: str = "info", height: int = 92) -> str:
    """Area sparkline with end-point marker."""
    points = [float(v) for v in values]
    if len(points) < 2:
        return '<div style="color:var(--muted);font-size:12.5px">Not enough history yet.</div>'
    start, stop = RAMPS.get(variant, RAMPS["info"])
    uid = f"sp{next(_uid_counter)}"
    width, pad = 300.0, 8.0
    low, high = min(points), max(points)
    span = (high - low) or 1.0
    step = (width - pad * 2) / (len(points) - 1)
    coords = [
        (pad + i * step, height - pad - (v - low) / span * (height - pad * 2))
        for i, v in enumerate(points)
    ]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = (
        f"M {coords[0][0]:.1f} {height - pad:.1f} L "
        + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords)
        + f" L {coords[-1][0]:.1f} {height - pad:.1f} Z"
    )
    tip_x, tip_y = coords[-1]
    # Polyline length drives the stroke draw-on animation.
    stroke_len = sum(
        math.dist(coords[i], coords[i + 1]) for i in range(len(coords) - 1)
    )
    return (
        f'<svg class="spark" viewBox="0 0 {width:.0f} {height}" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="{uid}" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{stop}"/>'
        f'</linearGradient>'
        f'<linearGradient id="{uid}a" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{stop}" stop-opacity=".38"/>'
        f'<stop offset="1" stop-color="{stop}" stop-opacity="0"/>'
        f'</linearGradient>'
        f'<linearGradient id="{uid}s" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{stop}" stop-opacity="0"/>'
        f'<stop offset="1" stop-color="{stop}" stop-opacity=".55"/>'
        f'</linearGradient></defs>'
        f'<path class="sarea" d="{area}" fill="url(#{uid}a)"/>'
        f'<rect class="sscan" x="{pad:.0f}" y="0" width="10" height="{height}" '
        f'fill="url(#{uid}s)"/>'
        f'<polyline class="sline" points="{line}" stroke="url(#{uid})" '
        f'stroke-dasharray="{stroke_len:.2f}" style="--len:{stroke_len:.2f}"/>'
        f'<circle class="sdot-halo" cx="{tip_x:.1f}" cy="{tip_y:.1f}" r="7" fill="{stop}"/>'
        f'<circle class="sdot" cx="{tip_x:.1f}" cy="{tip_y:.1f}" r="4" fill="{stop}"/>'
        "</svg>"
    )


def ticker_html(items: list[tuple[str, str, str]]) -> str:
    """Seamless scrolling telemetry strip. Items are (label, value, variant)."""
    if not items:
        return ""
    cells = "".join(
        f'<span class="tk {html_escape(variant)}"><i></i><s>{html_escape(label)}</s>'
        f"<b>{html_escape(value)}</b></span>"
        for label, value, variant in items
    )
    # The track is duplicated so translateX(-50%) loops without a visible seam.
    return f'<div class="ticker"><div class="ticker-track">{cells}{cells}</div></div>'


def panel_html(title: str, body: str, *, sub: str = "", tag: str = "", tall: bool = False) -> str:
    sub_html = f'<span class="panel-sub">{html_escape(sub)}</span>' if sub else ""
    tag_html = f'<span class="panel-tag">{html_escape(tag)}</span>' if tag else ""
    return (
        f'<div class="panel{" tall" if tall else ""}"><div class="panel-head">'
        f'<span class="panel-title">{html_escape(title)}</span>{sub_html}{tag_html}</div>'
        f'<div class="panel-body">{body}</div></div>'
    )


def panel_grid_html(panels: list[str], *, ratio: str = "") -> str:
    """Lay panels out as one equal-height row that wraps on smaller screens.

    A CSS grid is used instead of st.columns so every panel in the row shares a
    height and the row reflows to a single column on phones. ``ratio`` picks a
    column template: "r-2", "r-3" or "r-narrow-wide".
    """
    cells = [p for p in panels if p]
    if not cells:
        return ""
    css = f"pgrid {ratio}".strip()
    return f'<div class="{css}">{"".join(cells)}</div>'


def stats_grid_html(items: list[tuple]) -> str:
    """Row of stat cards as one wrapping grid, so every card is the same height.

    Items are ``(label, value)``, optionally with ``delta`` and ``accent``.
    """
    cells = []
    for item in items:
        label, value = item[0], item[1]
        delta = item[2] if len(item) > 2 else ""
        accent = bool(item[3]) if len(item) > 3 else False
        cells.append(stat_html(label, value, delta, accent))
    return f'<div class="sgrid">{"".join(cells)}</div>' if cells else ""


def _one_line(text: str, limit: int = 110) -> str:
    """First non-empty line, collapsed whitespace, truncated for the closed row."""
    line = ""
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            break
    if len(line) > limit:
        return line[: limit - 1] + "…"
    return line or "—"


def _compact_body(text: str, *, limit: int = 800) -> str:
    """Keep expanded agent text short: drop blank runs, cap length."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
    kept = [line for line in lines if line]
    body = "\n".join(kept)
    if len(body) > limit:
        return body[: limit - 1] + "…"
    return body


def agent_nodes(report: AegisReport) -> list[tuple[str, str, str, str]]:
    """(role_short, one_line, detail, variant) for the collapsible agent list."""
    raw = report.agent_outputs.get("raw", {}) or {}
    nodes = []

    alignment = report.agent_outputs.get("alignment") or report.story_alignment.get("alignment", "GAPS")
    review_line = f"ALIGNMENT={alignment}"
    review_body = _compact_body(raw.get("PR Compliance Reviewer") or "")
    nodes.append(("PR Reviewer", review_line, review_body, "ok" if alignment == "ALIGNED" else "bad"))

    security = report.agent_outputs.get("security") or "PASS"
    security_variant = {"PASS": "ok", "REVIEW": "warn", "FAIL": "bad"}.get(security, "warn")
    sec_body = _compact_body(raw.get("Security Analyst") or "")
    nodes.append(("Security", f"SECURITY={security}", sec_body, security_variant))

    radius = report.blast_radius or {}
    affected = radius.get("affected_services", []) or []
    blast_line = f"{len(affected)} service(s)" + (f" · {', '.join(affected[:4])}" if affected else "")
    blast_body = _compact_body(raw.get("Blast Radius Analyst") or "")
    nodes.append(("Blast Radius", blast_line, blast_body, "warn"))

    risk_line = (
        f"risk score {report.regression_probability:.0%} · "
        f"confidence {report.merge_confidence:.0f}"
    )
    risk_body = _compact_body(raw.get("Risk Analyzer") or "")
    nodes.append(("Risk Analyzer", risk_line, risk_body, "warn"))

    tests = [t.get("id") for t in report.recommended_tests if t.get("id")]
    test_line = f"{len(tests)} test(s) selected"
    test_body = _compact_body(
        raw.get("Test Selector") or (", ".join(tests) if tests else "")
    )
    nodes.append(("Test Selector", test_line, test_body, "ok"))

    verdict_variant = {"APPROVE": "ok", "REVIEW": "warn", "REJECT": "bad"}.get(report.verdict, "warn")
    orch_body = _compact_body(raw.get("AEGIS Release Orchestrator") or "")
    nodes.append(("Orchestrator", f"VERDICT={report.verdict}", orch_body, verdict_variant))

    return nodes


def agent_diagram_html(report: AegisReport) -> str:
    blocks = []
    for role, line, detail, variant in agent_nodes(report):
        extra = ""
        if detail and _one_line(detail) != line:
            extra = f'<div class="out">{html_escape(detail)}</div>'
        blocks.append(
            f'<details class="agent {variant}">'
            f'<summary>'
            f'<span class="role"><span class="tick"></span>{html_escape(role)}</span>'
            f'<span class="one">{html_escape(line)}</span>'
            f'</summary>{extra}</details>'
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


def risk_score_formula_markdown() -> str:
    """Published Risk Score formula for the numbers glossary."""
    gap = f"{GAP_RISK:.0%}"
    review = f"{SECURITY_REVIEW_RISK:.0%}"
    fail = f"{SECURITY_FAIL_RISK:.0%}"
    extra = f"{BLAST_EXTRA_SERVICE:.0%}"
    flow = f"{BLAST_FLOW_RISK:.0%}"
    incident = f"{BLAST_INCIDENT_RISK:.0%}"
    churn = f"{RISK_CHURN_CAP:.0%}"
    llm = f"{LLM_RISK_WEIGHT:.0%}"
    uncovered = f"{TEST_UNCOVERED_RISK:.0%}"
    none = f"{TEST_NONE_RISK:.0%}"
    cap = f"{SCORE_MAX:.0%}"
    conf_cap = f"{CONFIDENCE_MAX:.0f}%"
    return (
        "**Risk Score** is a formula, not a free-form model guess.\n\n"
        f"`Risk Score = min({cap}, PR Reviewer + Security + Blast Radius + "
        "Risk Analyzer + Test Selector)`\n\n"
        f"- **PR Reviewer:** {gap} × share of changed files that do not match the Jira story\n"
        f"- **Security:** {review} if REVIEW, {fail} if FAIL\n"
        f"- **Blast Radius:** {extra} per extra service, {flow} if a customer flow is hit, "
        f"{incident} per past incident\n"
        f"- **Risk Analyzer:** up to {churn} from code churn; plus {llm} × the model's "
        "regression number when agents are on\n"
        f"- **Test Selector:** {uncovered} × uncovered files; {none} more if no tests were selected\n\n"
        f"**Safe-to-merge score** = `min({conf_cap}, 100% − Risk Score)`\n\n"
        "A Risk Score **above 1%** cannot be APPROVE. "
        "The Orchestrator turns this into APPROVE / REVIEW / REJECT. "
        "Deployment Advisor is release-only and is not in this formula."
    )


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


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def friendly_file_reason(file_row: dict, stories: list[dict]) -> str:
    domain = (file_row.get("domain") or "unknown").strip()
    if file_row.get("aligned"):
        return f"matches the Jira epic ({domain})"
    if not stories:
        return "this PR has no Jira ticket linked"
    epics = _unique([str(s.get("epic") or "unspecified") for s in stories])
    keys = _unique([str(s.get("key") or "") for s in stories])
    ticket = ", ".join(keys) if keys else "the linked ticket"
    epic = ", ".join(epics)
    return f"this is {domain} code, but {ticket} is about {epic}"


def alignment_gap_guidance(alignment: dict, pr: dict, suggestions: list[dict] | None = None) -> dict | None:
    """Plain-language GAP hint plus a longer how-to for the info popover."""
    if alignment.get("alignment") != "GAPS":
        return None
    stories = [s for s in (alignment.get("linked_stories") or []) if s.get("key")]
    files = [f for f in (alignment.get("files") or []) if not f.get("aligned")]
    if not files:
        files = list(alignment.get("files") or [])
    paths = _unique([str(f.get("path") or "") for f in files])
    domains = _unique([str(f.get("domain") or "unknown") for f in files])
    services = _unique([str(f.get("microservice") or "") for f in files])
    pr_n = pr.get("number") or alignment.get("pr_number") or "?"
    title = pr.get("title") or "this pull request"
    service_label = ", ".join(f"`{s}`" for s in services) or "the changed service"
    domain_label = ", ".join(domains) or "this area"
    file_list = ", ".join(f"`{p}`" for p in paths) or "the changed files"
    suggestions = list(suggestions or [])
    best = suggestions[0] if suggestions else None
    best_key = html_escape(str(best.get("key"))) if best else None
    best_title = html_escape(str(best.get("title") or "")) if best else ""
    best_why = html_escape("; ".join(best.get("reasons") or [])) if best else ""

    suggest_html = ""
    suggest_fix = ""
    if best:
        alts = suggestions[1:]
        alt_html = ""
        if alts:
            bits = ", ".join(
                f"{html_escape(str(a.get('key')))} ({html_escape(str(a.get('title') or ''))})"
                for a in alts
            )
            alt_html = f'<div class="gs-alts">Also considered: {bits}</div>'
        suggest_html = (
            '<div class="gap-suggest">'
            '<div class="gs-kicker">Best matching Jira ticket</div>'
            f'<div class="gs-key">{best_key}</div>'
            f'<div class="gs-title">{best_title}</div>'
            f'<div class="gs-why">{best_why}</div>'
            f"{alt_html}"
            "</div>"
        )
        suggest_fix = (
            f"Put {best.get('key')} in the GitHub PR title, then re-run analysis. "
            "AEGIS will sync GitHub into Neo4j and link that ticket."
        )

    details_suggest = ""
    if best:
        details_suggest = (
            f"\n\n### Best matching Jira ticket\n\n"
            f"**{best.get('key')}** — {html_escape(str(best.get('title')))}\n\n"
            f"- Epic: `{html_escape(str(best.get('epic') or '—'))}`\n"
            f"- Status: `{html_escape(str(best.get('status') or '—'))}`\n"
            f"- Why it fits: {html_escape('; '.join(best.get('reasons') or []))}\n\n"
            "AEGIS scored live Jira issues against this PR's GitHub title and files "
            "(product area + shared words). Put that key in the GitHub title and re-run."
        )

    if not stories:
        return {
            "title": "This pull request has no Jira ticket",
            "body": (
                f"PR #{html_escape(str(pr_n))} changes <b>{html_escape(domain_label)}</b> code, "
                "but AEGIS cannot see a Jira story for that work. Without a ticket, it cannot "
                "tell whether the change is in scope — so it flags a gap and will not approve."
            ),
            "fix": suggest_fix or (
                "To resolve: put the matching Jira key in the GitHub PR title, "
                "then re-run analysis. AEGIS will update Neo4j from GitHub."
            ),
            "suggest_html": suggest_html,
            "details": (
                f"### What went wrong\n\n"
                f"**PR #{pr_n}** — {html_escape(str(title))}\n\n"
                f"- Changed files: {file_list}\n"
                f"- Service: {service_label} ({domain_label})\n"
                f"- Linked Jira story: none\n\n"
                "AEGIS compares each changed file's service area with the epic of the "
                "Jira story on the PR. No story means every file looks unaccounted for.\n\n"
                "### How to fix it\n\n"
                "1. Use the suggested Jira ticket below (or pick another in the same product area).\n"
                f"2. Put that key in the GitHub PR title.\n"
                "3. Re-run analysis — AEGIS syncs the GitHub title into Neo4j and links the ticket.\n\n"
                "You do not need to change the code — only attach the right ticket."
                f"{details_suggest}"
            ),
        }

    story_bits = ", ".join(
        f"{s.get('key')} ({s.get('epic') or 'no epic'})" for s in stories
    )
    return {
        "title": "The linked Jira ticket does not match this code",
        "body": (
            f"The files in PR #{html_escape(str(pr_n))} belong to "
            f"<b>{html_escape(domain_label)}</b>, but the linked ticket is "
            f"<b>{html_escape(story_bits)}</b>. AEGIS treats that as the wrong work item."
        ),
        "fix": suggest_fix or (
            f"To resolve: link this PR to a Jira story whose epic is "
            f"{html_escape(domain_label)} (same product area as the files). "
            "Leave the code as-is, then re-run analysis."
        ),
        "suggest_html": suggest_html,
        "details": (
            f"### What went wrong\n\n"
            f"**PR #{pr_n}** — {html_escape(str(title))}\n\n"
            f"- Changed files: {file_list}\n"
            f"- Those files live in {service_label} (**{domain_label}**)\n"
            f"- Linked Jira: {html_escape(story_bits)}\n\n"
            "A file is aligned only when its service area matches the epic of a "
            "linked Jira story.\n\n"
            "### How to fix it\n\n"
            "1. Switch the PR to the suggested Jira ticket (or another whose epic "
            f"is **{html_escape(domain_label)}**).\n"
            "2. Put that key in the GitHub PR title, then re-run analysis.\n"
            "3. Alignment should switch from GAPS to ALIGNED if the epic matches "
            "— the code itself does not need to change.\n\n"
            "If the files really are out of scope for the ticket, split them into "
            "a separate PR instead of forcing the link."
            f"{details_suggest}"
        ),
    }


def run_analysis(pr_number: int, use_llm: bool) -> AegisReport:
    return AegisOrchestrator().analyze_pr(pr_number, use_llm=use_llm)


@st.cache_data(show_spinner=False, ttl=600)
def run_analysis_cached(pr_number: int, use_llm: bool) -> AegisReport:
    """Cached LLM path only. Fast mode stays live so graph edits show immediately."""
    return run_analysis(pr_number, use_llm)


NODE_LABELS = {
    "Microservice": "Services",
    "CodeFile": "Files",
    "TestCase": "Tests",
    "Incident": "Incidents",
    "Release": "Releases",
    "PullRequest": "PRs",
    "Story": "Stories",
    "CustomerFlow": "Flows",
    "ApiRoute": "Routes",
    "Epic": "Epics",
}


def load_graph_health() -> tuple[list[tuple], dict, list[dict], list[dict], bool]:
    """(status_rows, graph_stats, releases, open_incidents, reachable)."""
    try:
        cig = CIGClient()
        try:
            if not cig.verify_connection():
                return [("Neo4j CIG: connection failed", "bad")], {}, [], [], False
            stats = queries.graph_stats(cig)
            releases = queries.release_history(cig)
            open_inc = queries.open_incidents(cig)
        finally:
            cig.close()
    except Exception as exc:
        return [(f"Neo4j CIG: {exc}", "bad")], {}, [], [], False

    rows = [
        ("Neo4j CIG", "ok"),
        ("Endpoint", "bolt://localhost:7687"),
        ("Nodes", str(sum(stats.get("nodes", {}).values()))),
        ("Relationships", str(sum(stats.get("relationships", {}).values()))),
    ]
    return rows, stats, releases, open_inc, True


def load_llm_health() -> tuple[list[tuple], bool]:
    """(status_rows, model_ready)."""
    try:
        llm = OllamaClient()
        models = llm.list_models()
        rows = [
            ("Ollama", "ok"),
            ("Endpoint", llm.base_url),
            ("Models", ", ".join(models) or "—"),
            ("Active model", llm.model),
        ]
        if llm.is_model_available():
            return rows, True
        rows.append((f"Model '{llm.model}' not pulled yet", "warn"))
        return rows, False
    except Exception as exc:
        return [(f"Ollama: {exc}", "bad")], False


def platform_readiness(
    *, graph_ok: bool, llm_ok: bool, open_incidents: list[dict]
) -> tuple[float, str]:
    """Composite 0-100 readiness score plus the reasons it is not 100."""
    score = 100.0
    notes: list[str] = []
    if not graph_ok:
        score -= 55.0
        notes.append("CIG unreachable")
    if not llm_ok:
        score -= 20.0
        notes.append("local model not ready")
    if open_incidents:
        score -= min(len(open_incidents) * 9.0, 27.0)
        notes.append(f"{len(open_incidents)} open incident(s)")
    score = max(0.0, min(score, 100.0))
    return score, " · ".join(notes) if notes else "All systems nominal"


def load_pr_options() -> dict[int, str]:
    """Pull-request picker. Titles are refreshed from GitHub during analysis."""
    try:
        cig = CIGClient()
        try:
            rows = cig.run(
                "MATCH (pr:PullRequest) RETURN pr.number AS number, pr.title AS title "
                "ORDER BY pr.number"
            )
        finally:
            cig.close()
    except Exception as exc:
        st.error(f"Could not load PRs: {exc}")
        return {}
    return {r["number"]: r["title"] for r in rows}


tab_health, tab_analyze, tab_mcps = st.tabs(
    ["Infrastructure & CIG", "PR Analysis", "MCP Integrations"]
)

with tab_health:
    neo4j_rows, stats, releases, open_inc, graph_ok = load_graph_health()
    ollama_rows, llm_ok = load_llm_health()
    nodes = stats.get("nodes", {})
    rels = stats.get("relationships", {})
    readiness, readiness_note = platform_readiness(
        graph_ok=graph_ok, llm_ok=llm_ok, open_incidents=open_inc
    )

    st.markdown(
        ticker_html([
            ("readiness", f"{readiness:.0f}%", score_variant(readiness)),
            ("neo4j", "online" if graph_ok else "offline", "ok" if graph_ok else "bad"),
            ("nodes", f"{sum(nodes.values())}", "info"),
            ("edges", f"{sum(rels.values())}", "info"),
            ("services", f"{nodes.get('Microservice', 0)}", "info"),
            ("code files", f"{nodes.get('CodeFile', 0)}", "info"),
            ("tests", f"{nodes.get('TestCase', 0)}", "ok"),
            (
                "open incidents",
                f"{len(open_inc)}",
                "bad" if open_inc else "ok",
            ),
            ("releases", f"{nodes.get('Release', 0)}", "info"),
            (
                "latest release",
                releases[-1]["version"] if releases else "—",
                "ok" if releases else "warn",
            ),
            ("local llm", "ready" if llm_ok else "model pending", "ok" if llm_ok else "warn"),
            ("prs in graph", f"{nodes.get('PullRequest', 0)}", "info"),
        ]),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="kicker">Mission control</div>', unsafe_allow_html=True)
    composition = [
        (NODE_LABELS.get(label, label), count)
        for label, count in sorted(nodes.items(), key=lambda kv: -kv[1])
    ][:7]
    st.markdown(
        panel_grid_html(
            [
                panel_html(
                    "Platform readiness",
                    gauge_html(
                        readiness,
                        "Platform readiness",
                        variant="ok",
                        foot=readiness_note,
                    ),
                    sub="graph · model · incidents",
                    tag="live",
                    tall=True,
                ),
                panel_html(
                    "Graph composition",
                    bars_html(composition, variant="info"),
                    sub=f"{sum(nodes.values())} nodes across {len(nodes)} labels",
                    tag="neo4j",
                    tall=True,
                ),
            ],
            ratio="r-narrow-wide",
        ),
        unsafe_allow_html=True,
    )

    if nodes:
        st.markdown(
            stats_grid_html([
                ("Microservices", str(nodes.get("Microservice", 0))),
                ("Code files", str(nodes.get("CodeFile", 0))),
                ("Test cases", str(nodes.get("TestCase", 0))),
                ("Incidents", str(nodes.get("Incident", 0)), f"{len(open_inc)} open"),
                ("Releases", str(nodes.get("Release", 0))),
                ("PRs analyzed", str(nodes.get("PullRequest", 0))),
            ]),
            unsafe_allow_html=True,
        )

    st.markdown('<div class="kicker">Stack status</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="stack-pair">'
        + status_rows_html("Neo4j — Connected Intelligence Graph", neo4j_rows)
        + status_rows_html("Ollama — Local LLM", ollama_rows)
        + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown('<div class="kicker">CrewAI agents</div>', unsafe_allow_html=True)
    st.caption("Seven AIDLC roles, one local LLM, orchestrated by CrewAI.")
    crew_blocks = []
    for spec in AGENT_SPECS:
        crew_blocks.append(
            f'<details class="crew-agent">'
            f'<summary>'
            f'<span class="crew-title">{html_escape(spec["role"])}</span>'
            f'<span class="crew-dot">·</span>'
            f'<code class="crew-id">{html_escape(spec["name"])}</code>'
            f'</summary>'
            f'<div class="crew-body">'
            f'<div><b>Goal:</b> {html_escape(spec["goal"])}</div>'
            f'<div style="margin-top:6px"><b>Backstory:</b> {html_escape(spec["backstory"])}</div>'
            f'</div></details>'
        )
    st.markdown(
        f'<div class="crew-grid">{"".join(crew_blocks)}</div>',
        unsafe_allow_html=True,
    )

    if open_inc:
        st.markdown('<div class="kicker">Open incidents</div>', unsafe_allow_html=True)
        for inc in open_inc:
            st.markdown(
                f'<span class="chip bad">{inc["id"]} · S{inc["severity"]} · '
                f'{inc["service"]} · {inc["root_cause"]}</span>',
                unsafe_allow_html=True,
            )

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

options = load_pr_options()

with tab_analyze:
    pr_number = st.selectbox(
        "Pull request",
        list(options.keys()),
        format_func=lambda n: f"#{n} — {options[n]}",
        key="pr_select",
    )

    fast = st.toggle(
        "Fast mode — deterministic analysis (no LLM agents)",
        value=True,
        help="Runs instantly using graph math only. Turn off to invoke the CrewAI "
             "agents over the local LLM (slower, but shows real agent reasoning).",
    )

    if st.button("Run AEGIS analysis", type="primary"):
        if not pr_number:
            st.warning("No pull request in the graph. Run `python scripts/seed_graph.py` first.")
        else:
            with st.spinner(
                "Syncing this PR from GitHub into Neo4j, then analyzing..."
                if fast
                else "Syncing GitHub into Neo4j, then agents reasoning over the CIG..."
            ):
                try:
                    run_analysis_cached.clear()
                    report = run_analysis(pr_number, use_llm=not fast)
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")
                    report = None
            posted = None
            if report:
                gh_target = resolve_github_pr_number(report.pr_number)
                with st.spinner(f"Posting AEGIS report to GitHub PR #{gh_target}..."):
                    posted = maybe_post_report(report)
            st.session_state["aegis_report"] = report
            st.session_state["aegis_posted"] = posted
            st.session_state["aegis_report_pr"] = pr_number

    report = st.session_state.get("aegis_report")
    posted = st.session_state.get("aegis_posted")
    if report is None or st.session_state.get("aegis_report_pr") != pr_number:
        report = None
        posted = None

    if not report:
        st.caption("Pick a pull request and click **Run AEGIS analysis** to see the verdict.")
    else:
            st.markdown(
                f'<div class="glass pr-head" style="margin-bottom:22px">'
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
                '<div class="section-note">One line per agent. Expand a row for the full note.</div>',
                unsafe_allow_html=True,
            )

            st.markdown('<div class="kicker">Decision</div>', unsafe_allow_html=True)
            confidence = min(max(report.merge_confidence, 0.0), 100.0)
            regression = min(max(report.regression_probability * 100.0, 0.0), 100.0)
            alignment_label = report.agent_outputs.get("alignment", "GAPS")
            breakdown = (report.deterministic_features or {}).get("breakage_breakdown") or {}
            agent_labels = {
                "pr_reviewer": "PR Reviewer",
                "security": "Security",
                "blast_radius": "Blast Radius",
                "risk_analyzer": "Risk Analyzer",
                "test_selector": "Test Selector",
            }
            risk_bits = [
                f"{label} {100 * float(breakdown[key]):.0f}%"
                for key, label in agent_labels.items()
                if float(breakdown.get(key) or 0) > 0.004
            ]
            risk_foot = "Formula from all PR analysts, not a single model guess"
            if risk_bits:
                risk_foot += " · " + " + ".join(risk_bits)
            risk_foot += f" · safe-to-merge score {confidence:.0f}%"
            st.markdown(
                panel_grid_html(
                    [
                        f'<div class="panel verdict-panel">'
                        f'<div class="vlabel">Verdict</div>'
                        f'<span class="badge {VERDICT_COLORS.get(report.verdict, "review")}">'
                        f'{html_escape(report.verdict)}</span>'
                        f'<div class="vsub">Requirement alignment · '
                        f'<b>{html_escape(str(alignment_label))}</b></div>'
                        f'<div class="vsub" style="color:var(--muted)">'
                        f'{"LLM agents" if report.mode == "full" else "deterministic"} mode</div>'
                        f"</div>",
                        panel_html(
                            "Risk Score",
                            gauge_html(
                                regression,
                                "Risk Score",
                                variant="red",
                                foot=risk_foot,
                            ),
                            tag="risk",
                            tall=True,
                        ),
                    ],
                    ratio="r-2",
                ),
                unsafe_allow_html=True,
            )

            st.markdown('<div class="kicker">Requirements alignment</div>', unsafe_allow_html=True)
            alignment = report.story_alignment
            stories = alignment.get("linked_stories") or []
            if alignment.get("files"):
                for f in alignment["files"]:
                    variant = "ok" if f["aligned"] else "bad"
                    reason = friendly_file_reason(f, stories)
                    st.markdown(
                        f'<span class="chip {variant}">{"✓" if f["aligned"] else "✗"} '
                        f'{html_escape(str(f["path"]))} · {html_escape(reason)}</span>',
                        unsafe_allow_html=True,
                    )
                guidance = alignment_gap_guidance(
                    alignment, report.pr or {}, getattr(report, "story_suggestions", None) or [],
                )
                if guidance:
                    hint_col, info_col = st.columns([0.9, 0.1], vertical_alignment="center")
                    with hint_col:
                        st.markdown(
                            '<div class="gap-hint">'
                            '<div class="gap-kicker">How to resolve this gap</div>'
                            f'<div class="gap-title">{html_escape(guidance["title"])}</div>'
                            f'<div class="gap-body">{guidance["body"]}</div>'
                            f'{guidance.get("suggest_html") or ""}'
                            f'<div class="gap-fix"><b>Fix:</b> {guidance["fix"]}</div>'
                            "</div>",
                            unsafe_allow_html=True,
                        )
                    with info_col:
                        with st.popover(
                            "i",
                            help="More detail on why this is a gap and how to fix it",
                            use_container_width=True,
                        ):
                            st.markdown(
                                f'<div class="gap-howto">{guidance["details"]}</div>',
                                unsafe_allow_html=True,
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

            if rows:
                st.markdown(
                    panel_grid_html(
                        [
                            panel_html(
                                "Test coverage by service",
                                meters_html(
                                    [(r["Service"], r["Tests"]) for r in rows], variant="ok",
                                    unit=" tests",
                                ),
                                sub="automated tests guarding each affected service",
                                tag="coverage",
                            ),
                            panel_html(
                                "Exposure surface",
                                bars_html(
                                    [
                                        ("Services", len(rows)),
                                        ("Routes", sum(r["Routes"] for r in rows)),
                                        ("Flows", sum(r["Flows"] for r in rows)),
                                        ("Tests", sum(r["Tests"] for r in rows)),
                                        ("Incidents", sum(r["Past incidents"] for r in rows)),
                                    ],
                                    variant="warn",
                                ),
                                sub="everything reachable from the changed files",
                                tag="graph walk",
                            ),
                        ],
                        ratio="r-2",
                    ),
                    unsafe_allow_html=True,
                )

            st.dataframe(
                rows,
                width="stretch",
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
            targeted = len(report.recommended_tests)
            st.markdown(
                panel_grid_html(
                    [
                        panel_html(
                            "Suite reduction",
                            gauge_html(
                                min(max(float(reduction), 0.0), 100.0),
                                "Suite reduction",
                                variant="ok",
                                foot=f"{targeted} of {total} tests selected",
                            ),
                            tag="targeting",
                            tall=True,
                        ),
                        panel_html(
                            "Full suite vs targeted run",
                            bars_html(
                                [("Full suite", total), ("Targeted", targeted),
                                 ("Skipped", max(total - targeted, 0))],
                                variant="violet",
                            ),
                            sub="graph-selected tests replace the whole suite",
                            tag="tests",
                            tall=True,
                        ),
                    ],
                    ratio="r-narrow-wide",
                ),
                unsafe_allow_html=True,
            )
            st.markdown(
                stats_grid_html([
                    ("Suite size", f"{total} tests"),
                    ("Targeted", f"{targeted} tests", "instead of the full suite"),
                    ("Suite reduction", f"{reduction:.1f}%",
                     f"−{max(total - targeted, 0)} tests not run", True),
                ]),
                unsafe_allow_html=True,
            )

            if report.recommended_tests:
                test_rows = [{
                    "Test": t["id"],
                    "Why": SOURCE_LABELS.get(t.get("source"), t.get("source", "")),
                    "Related incidents": ", ".join(t.get("incidents", [])) or "-",
                } for t in report.recommended_tests]
                st.dataframe(
                    test_rows,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Why": st.column_config.TextColumn("Why", help="Selection rationale, in priority order."),
                    },
                )
            else:
                st.info("No tests in scope.")

            st.markdown('<div class="kicker">Risk signals</div>', unsafe_allow_html=True)
            st.markdown(
                stats_grid_html([
                    ("Files changed", str(features.get("num_files", 0))),
                    ("Code churn", f'{features.get("churn", 0)} lines'),
                    ("File coverage", f'{features.get("file_test_coverage_ratio", 0):.0%}'),
                    ("Open incidents", str(len(features.get("past_incidents", [])) or 0)),
                ]),
                unsafe_allow_html=True,
            )

            query_count = len((report.provenance or {}).get("queries") or [])
            with st.expander(f"Data provenance · {query_count} Cypher queries", expanded=False):
                st.markdown(provenance_html(report), unsafe_allow_html=True)

            with st.expander("What do these numbers mean?", expanded=False):
                st.markdown(risk_score_formula_markdown())
                st.markdown("---")
                for term, meaning in GLOSSARY.items():
                    st.markdown(f"**{term}** — {meaning}")

            with st.expander("Raw blast radius JSON"):
                st.json(radius)
            with st.expander("Raw risk features JSON"):
                st.json(features)
            with st.expander("Raw agent output"):
                st.json(report.agent_outputs)

with tab_mcps:
    render_mcp_panel()
