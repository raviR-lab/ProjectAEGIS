import importlib
import itertools
import math
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
    "aegis.ui.mcp_panel",
    "aegis.ui.bot_preview",
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
from aegis.ui.bot_preview import bot_dock_script
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

      .stApp { background:
                 linear-gradient(rgba(120,180,255,.045) 1px, transparent 1px),
                 linear-gradient(90deg, rgba(120,180,255,.045) 1px, transparent 1px),
                 radial-gradient(1200px 700px at 15% -10%, #0d1b3a 0%, transparent 55%),
                 radial-gradient(1000px 600px at 110% 20%, #1a0f33 0%, transparent 50%),
                 var(--bg);
               background-size: 100% 46px, 46px 100%, auto, auto, auto;
               color: var(--text);
               animation: gridDrift 32s linear infinite; }
      @keyframes gridDrift {
        from { background-position: 0 0, 0 0, 0 0, 0 0, 0 0; }
        to   { background-position: 0 460px, 460px 0, 0 0, 0 0, 0 0; }
      }
      [data-testid="stHeader"] { background: transparent; }
      [data-testid="stToolbar"] { right: 1rem; }

      html, body, [class*="css"] {
        font-family: 'Space Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      }
      .mono, code, pre { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace !important; }

      .hero { padding: 6px 0 2px; }
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
               box-shadow: 0 10px 40px rgba(0,0,0,.35); }
      .glass-glow { border-color: var(--border-bright);
                    box-shadow: 0 0 0 1px rgba(120,190,255,.06), 0 0 34px rgba(34,211,238,.08); }

      .stat { background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
              padding: 14px 18px; backdrop-filter: blur(14px); position: relative;
              overflow: hidden; transition: transform .25s ease, border-color .25s ease;
              animation: riseIn .6s cubic-bezier(.2,.8,.2,1) both; }
      .stat:hover { transform: translateY(-3px); border-color: var(--border-bright); }
      .stat::after { content:""; position:absolute; left:0; right:0; bottom:0; height:2px;
                     background: var(--grad); transform-origin: left;
                     animation: wipeIn 1.1s cubic-bezier(.2,.8,.2,1) both .15s; }
      @keyframes riseIn { from { opacity:0; transform: translateY(12px); } }
      @keyframes wipeIn { from { transform: scaleX(0); } }
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

      /* ---------- futuristic telemetry deck ---------- */
      .panel { position:relative; border:1px solid var(--border); border-radius:18px;
               padding:16px 18px 14px; margin-bottom:14px; overflow:hidden;
               background: linear-gradient(160deg, rgba(19,28,50,.92), rgba(9,14,26,.78));
               box-shadow: 0 14px 44px rgba(0,0,0,.45);
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
      .panel-head { display:flex; align-items:baseline; gap:10px; margin-bottom:14px; }
      .panel-title { font-size:14px; font-weight:600; letter-spacing:.2px; }
      .panel-sub { color:var(--muted); font-size:11.5px; }
      .panel-tag { margin-left:auto; font-size:10px; font-weight:700; letter-spacing:1.4px;
                   text-transform:uppercase; color:#8fb7dd; border:1px solid var(--border);
                   border-radius:999px; padding:3px 10px; }

      .gauge-wrap { display:flex; justify-content:center; }
      .gauge { width:100%; max-width:250px; overflow:visible; }
      .gauge .gnum { font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:46px;
                     fill:#eef4ff; }
      .gauge .gsuf { font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:17px;
                     fill:#7a8ba8; }
      .gauge .gcap { font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:10.5px;
                     fill:#7a8ba8; letter-spacing:2.2px; }
      @keyframes gaugeFill { from { stroke-dashoffset: var(--dash-len); }
                             to   { stroke-dashoffset: var(--dash-off); } }
      .gauge .val { animation: gaugeFill 1.35s cubic-bezier(.2,.8,.2,1) both,
                               ringBreathe 3.4s ease-in-out 1.35s infinite; }
      @keyframes ringBreathe { 0%,100% { opacity:1; } 50% { opacity:.74; } }
      /* breathing halo behind the readout */
      .gauge .ghalo { transform-box: fill-box; transform-origin: center;
                      animation: haloPulse 3.6s ease-in-out infinite; }
      @keyframes haloPulse { 0%,100% { opacity:.15; transform: scale(1); }
                             50%     { opacity:.05; transform: scale(1.1); } }
      /* marker riding the tip of the value arc */
      .gauge .gtip { transform-box: fill-box; transform-origin: center;
                     animation: tipPulse 1.9s ease-in-out .9s infinite; }
      .gauge .gtip-halo { transform-box: fill-box; transform-origin: center;
                          animation: tipRing 1.9s ease-out .9s infinite; }
      @keyframes tipPulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.28); } }
      @keyframes tipRing { 0% { opacity:.55; transform: scale(.7); }
                           100% { opacity:0; transform: scale(2.5); } }
      .gauge-foot { text-align:center; color:var(--muted); font-size:12px; margin-top:2px; }

      .cb { display:flex; align-items:flex-end; gap:10px; }
      .cb-item { flex:1; min-width:0; text-align:center; }
      .cb-val { font-size:13px; font-weight:700; color:#dce6fa; margin-bottom:5px; }
      .cb-track { position:relative; height:104px; border-radius:9px;
                  background: rgba(120,150,220,.08); overflow:hidden; }
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

      .mt { margin-bottom:11px; }
      .mt:last-child { margin-bottom:0; }
      .mt-top { display:flex; justify-content:space-between; align-items:baseline;
                font-size:12.5px; margin-bottom:5px; color:#c8d6f0; gap:10px; }
      .mt-top b { color:#eef4ff; font-family:'JetBrains Mono',monospace; font-size:12px; }
      .mt-track { height:8px; border-radius:999px; background: rgba(120,150,220,.1); overflow:hidden; }
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
      .spark .sdot { stroke:#0b1120; stroke-width:2; transform-box: fill-box;
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
      .ticker { position:relative; overflow:hidden; margin:12px 0 6px; padding:9px 0;
                border:1px solid var(--border); border-radius:12px;
                background: rgba(9,14,26,.6);
                mask-image: linear-gradient(90deg, transparent, #000 7%, #000 93%, transparent);
                -webkit-mask-image: linear-gradient(90deg, transparent, #000 7%, #000 93%, transparent); }
      .ticker-track { display:inline-flex; white-space:nowrap; will-change:transform;
                      animation: tickerRoll 42s linear infinite; }
      .ticker:hover .ticker-track { animation-play-state: paused; }
      @keyframes tickerRoll { from { transform: translateX(0); } to { transform: translateX(-50%); } }
      .tk { display:inline-flex; align-items:center; gap:8px; padding:0 22px;
            font-size:12.5px; color:#c8d6f0; }
      .tk b { font-family:'JetBrains Mono',monospace; font-size:12px; color:#eef4ff; }
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

      /* the dock's loader iframe should occupy no space in the page flow */
      .st-key-botdock_mount { height:0 !important; min-height:0 !important;
                              margin:0 !important; padding:0 !important;
                              overflow:hidden !important; gap:0 !important; }
      .st-key-botdock_mount iframe { height:0 !important; min-height:0 !important;
                                     border:0 !important; display:block; }

      /* docked PR-bot mockup: bottom-right, collapsible, drag-resizable */
      .botdock { position:fixed; right:22px; bottom:22px; z-index:100000;
                 width:380px; height:520px; display:flex; flex-direction:column;
                 font-family:'Space Grotesk', system-ui, sans-serif; color:var(--text);
                 background: rgba(10,15,27,.93); border:1px solid var(--border-bright);
                 border-radius:18px; overflow:hidden; backdrop-filter: blur(18px);
                 box-shadow: 0 26px 70px rgba(0,0,0,.62), 0 0 34px rgba(34,211,238,.07);
                 animation: dockIn .55s cubic-bezier(.2,.8,.2,1) both; }
      @keyframes dockIn { from { opacity:0; transform: translateY(18px) scale(.97); } }
      .botdock.resizing { animation:none; }

      .bd-grip { position:absolute; top:0; left:0; width:20px; height:20px; z-index:4;
                 cursor: nwse-resize; touch-action:none; }
      .bd-grip::before { content:""; position:absolute; top:7px; left:7px; width:7px; height:7px;
                         border-top:2px solid rgba(120,190,255,.5);
                         border-left:2px solid rgba(120,190,255,.5); border-radius:3px 0 0 0; }
      .bd-grip:hover::before { border-color: var(--cyan); }

      .bd-head { flex:0 0 auto; display:flex; align-items:center; gap:11px;
                 padding:12px 14px 12px 22px; cursor:pointer; user-select:none;
                 border-bottom:1px solid var(--border); background: rgba(9,14,26,.6); }
      .bd-who { min-width:0; }
      .bd-caret { flex:0 0 auto; color:var(--muted); font-size:12px;
                  transition: transform .25s ease; }
      .bot-ava { width:31px; height:31px; border-radius:10px; flex:0 0 auto;
                 display:flex; align-items:center; justify-content:center;
                 background: var(--grad); color:#06121f; font-weight:800; font-size:11.5px;
                 letter-spacing:.5px; box-shadow: 0 0 18px rgba(34,211,238,.28); }
      .bot-id { font-weight:600; font-size:14px; }
      .bot-sub { color:var(--muted); font-size:11px; white-space:nowrap;
                 overflow:hidden; text-overflow:ellipsis; }
      .bot-flag { margin-left:auto; flex:0 0 auto; color:#ffd98a; font-size:9.5px;
                  letter-spacing:1.6px; text-transform:uppercase;
                  border:1px solid rgba(251,191,36,.35);
                  background: rgba(251,191,36,.1); border-radius:999px; padding:3px 10px; }

      .bd-thread { flex:1 1 auto; min-height:0; overflow-y:auto; padding:16px 16px 10px;
                   display:flex; flex-direction:column; gap:11px;
                   background:
                     radial-gradient(520px 260px at 92% 0%, rgba(167,139,250,.07), transparent 62%); }
      .bd-thread::-webkit-scrollbar { width:8px; }
      .bd-thread::-webkit-scrollbar-track { background: transparent; }
      .bd-thread::-webkit-scrollbar-thumb { background: rgba(120,150,220,.26); border-radius:8px; }

      .turn { display:flex; animation: riseIn .55s cubic-bezier(.2,.8,.2,1) both; }
      .turn.me { justify-content:flex-end; }
      .bubble { max-width:90%; padding:10px 14px; border-radius:16px; font-size:13px;
                line-height:1.55; border:1px solid var(--border);
                background: rgba(20,28,48,.72); color:var(--text); }
      .turn.me .bubble { max-width:82%; border-color: rgba(120,190,255,.3); color:#eef4ff;
                         background: linear-gradient(120deg, rgba(34,211,238,.16), rgba(167,139,250,.16)); }
      .bubble p { margin:0 0 6px; }
      .bubble p:last-child { margin-bottom:0; }
      .bubble .b-title { font-weight:600; font-size:12px; color:#eef4ff;
                         letter-spacing:.3px; margin-bottom:5px; }
      .bubble ul { margin:2px 0 6px; padding-left:17px; }
      .bubble li { margin:1px 0; }
      .bubble code { font-family:'JetBrains Mono',monospace; font-size:11px;
                     background: rgba(120,150,220,.14); border-radius:5px; padding:1px 5px; }
      .bot-chips { margin-top:6px; }
      .bubble.typing { display:flex; gap:5px; padding:13px 15px; }
      .bubble.typing i { width:6px; height:6px; border-radius:50%; background:var(--cyan);
                         animation: typeDot 1.3s ease-in-out infinite; }
      .bubble.typing i:nth-child(2) { animation-delay:.18s; }
      .bubble.typing i:nth-child(3) { animation-delay:.36s; }
      @keyframes typeDot { 0%,100% { opacity:.25; transform: translateY(0); }
                           45% { opacity:1; transform: translateY(-3px); } }

      .bd-composer { flex:0 0 auto; display:flex; align-items:center; gap:9px; padding:11px 13px;
                     border-top:1px solid var(--border); background: rgba(9,14,26,.6); }
      .bd-input { flex:1; min-width:0; font-family:inherit; font-size:12.5px;
                  color:var(--text); padding:9px 13px; border:1px solid var(--border);
                  border-radius:12px; background: rgba(7,11,20,.65); outline:none;
                  transition: border-color .2s ease, box-shadow .2s ease; }
      .bd-input::placeholder { color:var(--muted); }
      .bd-input:focus { border-color: var(--border-bright);
                        box-shadow: 0 0 0 3px rgba(34,211,238,.1); }
      .bd-send { flex:0 0 auto; font-family:inherit; font-size:12px; font-weight:700;
                 color:#06121f; background: var(--grad); border:0; border-radius:12px;
                 padding:10px 16px; cursor:pointer;
                 transition: opacity .2s ease, transform .15s ease; }
      .bd-send:hover:not(:disabled) { transform: translateY(-1px); }
      .bd-send:disabled { cursor:default; opacity:.4; transform:none; }

      .botdock.collapsed { width:auto !important; height:auto !important; border-radius:999px; }
      .botdock.collapsed .bd-head { border-bottom:none; padding:9px 15px; }
      .botdock.collapsed .bd-grip, .botdock.collapsed .bd-thread,
      .botdock.collapsed .bd-composer, .botdock.collapsed .bot-sub,
      .botdock.collapsed .bot-flag { display:none; }
      .botdock.collapsed .bd-caret { transform: rotate(180deg); }

      @media (max-width: 680px) {
        .botdock { left:12px; right:12px; bottom:12px; width:auto !important; }
        .botdock.collapsed { left:auto !important; }
      }

      @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { animation: none !important; transition: none !important; }
      }

      .verdict-panel { text-align:center; display:flex; flex-direction:column;
                       align-items:center; justify-content:center; gap:10px; min-height:268px; }
      .verdict-panel .badge { font-size:22px; padding:10px 30px; border-radius:14px; }
      .verdict-panel .vlabel { color:var(--muted); font-size:10.5px; letter-spacing:2.2px;
                               text-transform:uppercase; }
      .verdict-panel .vsub { color:#c8d6f0; font-size:13px; }

      .conn-card { background: var(--panel); border:1px solid var(--border); border-radius:18px;
                   padding: 18px 20px 16px; backdrop-filter: blur(14px); margin-bottom: 12px;
                   box-shadow: 0 10px 40px rgba(0,0,0,.35); position:relative; overflow:hidden;
                   min-height: 205px; display:flex; flex-direction:column; }
      .conn-card::before { content:""; position:absolute; inset:0 auto 0 0; width:3px; }
      .conn-card.ok::before { background: var(--green); }
      .conn-card.warn::before { background: var(--amber); }
      .conn-card.bad::before { background: var(--rose); }
      .conn-card.ok { border-color: rgba(52,211,153,.28);
                      box-shadow: 0 0 0 1px rgba(52,211,153,.08), 0 10px 40px rgba(0,0,0,.35); }
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


RAMPS = {
    "info": ("#22d3ee", "#a78bfa"),
    "ok": ("#34d399", "#22d3ee"),
    "warn": ("#fbbf24", "#fb923c"),
    "bad": ("#fb7185", "#ef4444"),
    "violet": ("#a78bfa", "#f472b6"),
}
GAUGE_START = 135.0
GAUGE_SWEEP = 270.0
GAUGE_RADIUS = 72.0
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


def gauge_html(
    percent: float,
    caption: str,
    *,
    display: str | None = None,
    suffix: str = "%",
    variant: str | None = None,
    foot: str = "",
) -> str:
    """Radial arc gauge: animated value ring, tick bezel and centred readout."""
    pct = max(0.0, min(float(percent) / 100.0, 1.0))
    start, stop = RAMPS.get(variant or score_variant(pct * 100), RAMPS["info"])
    uid = f"gg{next(_uid_counter)}"
    track = _arc_path(100, 100, GAUGE_RADIUS, GAUGE_START, GAUGE_START + GAUGE_SWEEP)
    length = 2 * math.pi * GAUGE_RADIUS * (GAUGE_SWEEP / 360.0)
    offset = length * (1.0 - pct)

    ticks = []
    for i in range(28):
        frac = i / 27.0
        degrees = GAUGE_START + GAUGE_SWEEP * frac
        x1, y1 = _polar(100, 100, GAUGE_RADIUS + 12, degrees)
        x2, y2 = _polar(100, 100, GAUGE_RADIUS + 17, degrees)
        lit = frac <= pct
        color = stop if lit else "rgba(120,150,220,.22)"
        ticks.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="{color}" stroke-width="2" stroke-linecap="round" '
            f'opacity="{"0.85" if lit else "1"}"/>'
        )

    readout = display if display is not None else f"{float(percent):.0f}"
    tip_x, tip_y = _polar(100, 100, GAUGE_RADIUS, GAUGE_START + GAUGE_SWEEP * pct)
    return (
        '<div class="gauge-wrap"><svg class="gauge" viewBox="0 0 200 176" '
        'xmlns="http://www.w3.org/2000/svg">'
        f'<defs><linearGradient id="{uid}" x1="0" y1="1" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{start}"/><stop offset="1" stop-color="{stop}"/>'
        f'</linearGradient>'
        f'<radialGradient id="{uid}h">'
        f'<stop offset="0" stop-color="{stop}" stop-opacity=".55"/>'
        f'<stop offset="1" stop-color="{stop}" stop-opacity="0"/>'
        f'</radialGradient>'
        f'<filter id="{uid}b" x="-30%" y="-30%" width="160%" height="160%">'
        f'<feGaussianBlur stdDeviation="5" result="blur"/>'
        f'<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter></defs>'
        f'<circle class="ghalo" cx="100" cy="100" r="58" fill="url(#{uid}h)"/>'
        f"{''.join(ticks)}"
        f'<path d="{track}" fill="none" stroke="rgba(120,150,220,.13)" '
        f'stroke-width="13" stroke-linecap="round"/>'
        f'<path class="val" d="{track}" fill="none" stroke="url(#{uid})" stroke-width="13" '
        f'stroke-linecap="round" filter="url(#{uid}b)" '
        f'stroke-dasharray="{length:.2f}" stroke-dashoffset="{offset:.2f}" '
        f'style="--dash-len:{length:.2f};--dash-off:{offset:.2f}"/>'
        f'<circle class="gtip-halo" cx="{tip_x:.2f}" cy="{tip_y:.2f}" r="7" fill="{stop}"/>'
        f'<circle class="gtip" cx="{tip_x:.2f}" cy="{tip_y:.2f}" r="4" fill="#eef4ff"/>'
        f'<text class="gnum" x="100" y="99" text-anchor="middle">{html_escape(readout)}'
        f'<tspan class="gsuf" dx="2">{html_escape(suffix)}</tspan></text>'
        f'<text class="gcap" x="100" y="124" text-anchor="middle">'
        f'{html_escape(caption.upper())}</text>'
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
        f"{body}</div>"
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
        if llm.is_model_available():
            return [
                ("Ollama", "ok"),
                ("Models", ", ".join(models)),
                ("Active model", llm.model),
            ], True
        return [
            ("Ollama", "ok"),
            (f"Model '{llm.model}' not pulled yet", "warn"),
        ], False
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
    """Pull-request picker for the analysis tab."""
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


tab_health, tab_analyze = st.tabs(["Infrastructure & CIG", "PR Analysis"])

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
    deck_l, deck_r = st.columns([1, 1.5], gap="large")
    with deck_l:
        st.markdown(
            panel_html(
                "Platform readiness",
                gauge_html(
                    readiness,
                    "Readiness score",
                    variant=score_variant(readiness),
                    foot=readiness_note,
                ),
                sub="graph · model · incidents",
                tag="live",
                tall=True,
            ),
            unsafe_allow_html=True,
        )
    with deck_r:
        composition = [
            (NODE_LABELS.get(label, label), count)
            for label, count in sorted(nodes.items(), key=lambda kv: -kv[1])
        ][:7]
        st.markdown(
            panel_html(
                "Graph composition",
                bars_html(composition, variant="info"),
                sub=f"{sum(nodes.values())} nodes across {len(nodes)} labels",
                tag="neo4j",
                tall=True,
            ),
            unsafe_allow_html=True,
        )

    if nodes:
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.markdown(
            stat_html("Microservices", str(nodes.get("Microservice", 0))), unsafe_allow_html=True)
        k2.markdown(
            stat_html("Code files", str(nodes.get("CodeFile", 0))), unsafe_allow_html=True)
        k3.markdown(
            stat_html("Test cases", str(nodes.get("TestCase", 0))), unsafe_allow_html=True)
        k4.markdown(
            stat_html("Incidents", str(nodes.get("Incident", 0)),
                      delta=f"{len(open_inc)} open"), unsafe_allow_html=True)
        k5.markdown(
            stat_html("Releases", str(nodes.get("Release", 0))), unsafe_allow_html=True)
        k6.markdown(
            stat_html("PRs analyzed", str(nodes.get("PullRequest", 0))), unsafe_allow_html=True)

    chart_l, chart_r = st.columns([1, 1], gap="large")
    with chart_l:
        top_rels = sorted(rels.items(), key=lambda kv: -kv[1])[:6]
        st.markdown(
            panel_html(
                "Relationship density",
                meters_html([(rel, count) for rel, count in top_rels], variant="violet"),
                sub=f"{sum(rels.values())} edges traversable",
                tag="edges",
            ),
            unsafe_allow_html=True,
        )
    with chart_r:
        cadence = [len(rel.get("services") or []) for rel in releases]
        latest = releases[-1]["version"] if releases else "—"
        st.markdown(
            panel_html(
                "Release cadence",
                sparkline_html(cadence, variant="ok"),
                sub=f"services per release · latest {latest}",
                tag="timeline",
            ),
            unsafe_allow_html=True,
        )

    col_stat, col_graph = st.columns([1, 1], gap="large")
    with col_stat:
        st.markdown('<div class="kicker">Stack status</div>', unsafe_allow_html=True)
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
        if open_inc:
            st.markdown('<div class="kicker">Open incidents</div>', unsafe_allow_html=True)
            for inc in open_inc:
                st.markdown(
                    f'<span class="chip bad">{inc["id"]} · S{inc["severity"]} · '
                    f'{inc["service"]} · {inc["root_cause"]}</span>',
                    unsafe_allow_html=True,
                )

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

options = load_pr_options()

with tab_analyze:
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
            confidence = min(max(report.merge_confidence, 0.0), 100.0)
            regression = min(max(report.regression_probability * 100.0, 0.0), 100.0)
            alignment_label = report.agent_outputs.get("alignment", "GAPS")
            d1, d2, d3 = st.columns([1, 1, 1], gap="large")
            with d1:
                st.markdown(
                    f'<div class="panel verdict-panel">'
                    f'<div class="vlabel">Verdict</div>'
                    f'<span class="badge {VERDICT_COLORS.get(report.verdict, "review")}">'
                    f'{html_escape(report.verdict)}</span>'
                    f'<div class="vsub">Requirement alignment · '
                    f'<b>{html_escape(str(alignment_label))}</b></div>'
                    f'<div class="vsub" style="color:var(--muted)">'
                    f'{"LLM agents" if report.mode == "full" else "deterministic"} mode</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with d2:
                st.markdown(
                    panel_html(
                        "Merge confidence",
                        gauge_html(
                            confidence,
                            "Confidence",
                            variant=score_variant(confidence),
                            foot="Higher is safer to merge",
                        ),
                        tag="score",
                        tall=True,
                    ),
                    unsafe_allow_html=True,
                )
            with d3:
                st.markdown(
                    panel_html(
                        "Regression risk",
                        gauge_html(
                            regression,
                            "Risk score",
                            variant=score_variant(regression, invert=True),
                            foot="Likelihood this change breaks something",
                        ),
                        tag="risk",
                        tall=True,
                    ),
                    unsafe_allow_html=True,
                )

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

            if rows:
                br_l, br_r = st.columns([1, 1], gap="large")
                with br_l:
                    st.markdown(
                        panel_html(
                            "Test coverage by service",
                            meters_html(
                                [(r["Service"], r["Tests"]) for r in rows], variant="ok",
                                unit=" tests",
                            ),
                            sub="automated tests guarding each affected service",
                            tag="coverage",
                        ),
                        unsafe_allow_html=True,
                    )
                with br_r:
                    st.markdown(
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
            tt_l, tt_r = st.columns([1, 1.5], gap="large")
            with tt_l:
                st.markdown(
                    panel_html(
                        "Suite reduction",
                        gauge_html(
                            min(max(float(reduction), 0.0), 100.0),
                            "Suite cut",
                            variant="ok",
                            foot=f"{targeted} of {total} tests selected",
                        ),
                        tag="targeting",
                        tall=True,
                    ),
                    unsafe_allow_html=True,
                )
            with tt_r:
                st.markdown(
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
                    unsafe_allow_html=True,
                )
            c1, c2, c3 = st.columns(3)
            c1.markdown(
                stat_html("Suite size", f"{total} tests"), unsafe_allow_html=True)
            c2.markdown(
                stat_html("Targeted", f"{targeted} tests",
                          delta="instead of the full suite"), unsafe_allow_html=True)
            c3.markdown(
                stat_html("Suite cut", f"{reduction:.1f}%", accent=True,
                          delta=f"−{max(total - targeted, 0)} tests not run"),
                unsafe_allow_html=True)

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

# The dock is mounted on the page body so it survives tab switches and reruns.
# Its loader iframe carries no visible content; CSS collapses the space it takes.
with st.container(key="botdock_mount"):
    st.iframe(bot_dock_script(), height=1)
