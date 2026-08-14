"""Preview of the planned AEGIS PR bot, docked in the bottom-right corner.

The window is collapsible by clicking its header and resizable by dragging the
grip in its top-left corner. It opens on a scripted transcript that shows the
shape of the answers the bot will give, and anything typed into it gets a canned
"still being built" reply. Nothing here queries the graph, calls an LLM, or
writes to GitHub: the reply is hard-coded and never leaves the browser.

Streamlit hides the contents of inactive tabs, so a fixed-position panel placed
inside a tab would vanish on tab switch. Instead the panel is mounted onto the
page body by a hidden loader iframe, which keeps it visible app-wide.
"""

from __future__ import annotations

import json
from html import escape as html_escape

DOCK_ID = "aegis-bot-dock"

# The single answer the bot gives to anything typed at it, until it is real.
REPLY = (
    "Hey! I'm warming up in the garage — something sharp is on the workbench. "
    "Hang tight; the real PR Copilot is almost ready to roll. ✨"
)

# Scripted opening transcript. Bot bodies are authored here (never user input),
# so the small amount of inline markup is trusted.
TRANSCRIPT: tuple[tuple[str, str], ...] = (
    ("me", "What's the risk on PR #482?"),
    (
        "bot",
        '<div class="b-title">Refund flow rewrite · payment-svc</div>'
        "<p>I walked the Connected Intelligence Graph. This one needs a human "
        "on it before merge.</p>"
        '<div class="bot-chips">'
        '<span class="chip warn">verdict REVIEW</span>'
        '<span class="chip">confidence 54%</span>'
        '<span class="chip bad">regression 46%</span>'
        "</div>",
    ),
    ("me", "What breaks if it ships?"),
    (
        "bot",
        '<div class="b-title">Blast radius · 3 services</div>'
        "<ul>"
        "<li><code>payment-svc</code> — changed directly</li>"
        "<li><code>order-svc</code> — 1 hop upstream</li>"
        "<li><code>notification-svc</code> — 2 hops upstream</li>"
        "</ul>"
        "<p>Checkout is the customer flow at risk, and "
        "<code>INC-204</code> hit this exact path before.</p>",
    ),
    ("me", "Which tests should I run?"),
    (
        "bot",
        '<div class="b-title">Targeted plan · 3 of 24 tests</div>'
        "<ul>"
        "<li><code>pay-test-refund</code> — covers the changed file</li>"
        "<li><code>pay-test-gateway</code> — same service</li>"
        "<li><code>order-test-checkout</code> — caught <code>INC-204</code></li>"
        "</ul>"
        '<div class="bot-chips"><span class="chip ok">87.5% suite cut</span></div>',
    ),
    ("me", "Post that summary on the GitHub PR."),
    (
        "bot",
        "<p>Ready to comment on <code>rizwanrnt/dummy-ecommerce</code> PR "
        "<b>#1</b>. I never post without your approval.</p>"
        '<div class="bot-chips">'
        '<span class="chip warn">awaiting confirmation</span>'
        "</div>",
    ),
)

_SCRIPT = """
<script>
(function () {
  const doc = window.parent.document;
  const win = window.parent;
  const ID = "__DOCK_ID__";
  const KEY = "aegis-bot-dock-state";
  const REPLY = __REPLY__;
  const MIN_W = 300;
  const MIN_H = 240;
  const THINKING_MS = 850;

  // Streamlit reruns re-execute this loader; keep the existing panel so a rerun
  // never resets the size the user dragged to or the messages they sent.
  if (doc.getElementById(ID)) { return; }

  const dock = doc.createElement("div");
  dock.id = ID;
  dock.className = "botdock";
  dock.innerHTML = __MARKUP__;
  doc.body.appendChild(dock);

  let state = { w: 380, h: 520, collapsed: false };
  try {
    const saved = JSON.parse(win.localStorage.getItem(KEY) || "null");
    if (saved) { state = Object.assign(state, saved); }
  } catch (err) { /* no stored state yet, or storage unavailable */ }

  const save = function () {
    try { win.localStorage.setItem(KEY, JSON.stringify(state)); }
    catch (err) { /* storage unavailable */ }
  };

  const thread = dock.querySelector(".bd-thread");
  const toBottom = function () {
    if (thread) { thread.scrollTop = thread.scrollHeight; }
  };

  const apply = function () {
    const capW = Math.max(MIN_W, win.innerWidth - 44);
    const capH = Math.max(MIN_H, win.innerHeight - 44);
    state.w = Math.min(Math.max(state.w, MIN_W), capW);
    state.h = Math.min(Math.max(state.h, MIN_H), capH);
    dock.style.width = state.w + "px";
    dock.style.height = state.h + "px";
    dock.classList.toggle("collapsed", !!state.collapsed);
  };

  apply();
  toBottom();

  dock.querySelector(".bd-head").addEventListener("click", function () {
    state.collapsed = !state.collapsed;
    apply();
    save();
    if (!state.collapsed) { toBottom(); }
  });

  /* ---- resizing: grip sits top-left because the panel is anchored bottom-right ---- */

  const grip = dock.querySelector(".bd-grip");
  grip.addEventListener("pointerdown", function (ev) {
    ev.preventDefault();
    ev.stopPropagation();
    const x0 = ev.clientX;
    const y0 = ev.clientY;
    const w0 = state.w;
    const h0 = state.h;
    dock.classList.add("resizing");
    doc.body.style.userSelect = "none";

    // Pointer capture keeps the drag alive when the cursor crosses an iframe.
    try { grip.setPointerCapture(ev.pointerId); } catch (err) { /* ignore */ }

    const move = function (e) {
      state.w = w0 - (e.clientX - x0);
      state.h = h0 - (e.clientY - y0);
      apply();
    };
    const done = function () {
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", done);
      grip.removeEventListener("pointercancel", done);
      dock.classList.remove("resizing");
      doc.body.style.userSelect = "";
      save();
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", done);
    grip.addEventListener("pointercancel", done);
  });

  /* ---- conversation: every message gets the same hard-coded reply ---- */

  const input = dock.querySelector(".bd-input");
  const send = dock.querySelector(".bd-send");
  const typingBubble = dock.querySelector(".bubble.typing");
  const typingTurn = typingBubble ? typingBubble.parentNode : null;

  const addTurn = function (role, text) {
    const turn = doc.createElement("div");
    turn.className = role === "me" ? "turn me" : "turn";
    const bubble = doc.createElement("div");
    bubble.className = "bubble";
    // textContent, not innerHTML: whatever was typed stays inert markup-wise.
    bubble.textContent = text;
    turn.appendChild(bubble);
    // Insert above the typing dots so they stay pinned to the bottom.
    if (typingTurn) { thread.insertBefore(turn, typingTurn); }
    else { thread.appendChild(turn); }
    toBottom();
  };

  let pending = false;
  const submit = function () {
    if (pending) { return; }
    const text = (input.value || "").trim();
    if (!text) { return; }
    input.value = "";
    addTurn("me", text);
    pending = true;
    send.disabled = true;
    win.setTimeout(function () {
      addTurn("bot", REPLY);
      pending = false;
      send.disabled = false;
    }, THINKING_MS);
  };

  send.addEventListener("click", submit);
  input.addEventListener("keydown", function (ev) {
    // Keep keystrokes away from Streamlit's global keyboard shortcuts.
    ev.stopPropagation();
    if (ev.key === "Enter") {
      ev.preventDefault();
      submit();
    }
  });

  win.addEventListener("resize", apply);
})();
</script>
"""


def _turn_html(role: str, body: str, *, delay: float) -> str:
    css = "turn me" if role == "me" else "turn"
    inner = html_escape(body) if role == "me" else body
    return (
        f'<div class="{css}" style="animation-delay:{delay:.2f}s">'
        f'<div class="bubble">{inner}</div></div>'
    )


def bot_dock_markup() -> str:
    """Inner markup of the docked window."""
    turns = "".join(
        _turn_html(role, body, delay=index * 0.1)
        for index, (role, body) in enumerate(TRANSCRIPT)
    )
    typing = (
        f'<div class="turn" style="animation-delay:{len(TRANSCRIPT) * 0.1 + 0.2:.2f}s">'
        '<div class="bubble typing"><i></i><i></i><i></i></div></div>'
    )
    return (
        '<div class="bd-grip" title="Drag to resize"></div>'
        '<div class="bd-head" title="Click to collapse or expand">'
        '<div class="bot-ava">AI</div>'
        '<div class="bd-who">'
        '<div class="bot-id">AEGIS PR Bot</div>'
        '<div class="bot-sub">Grounded in the Connected Intelligence Graph</div>'
        "</div>"
        '<span class="bot-flag">Preview</span>'
        '<span class="bd-caret">&#9662;</span>'
        "</div>"
        f'<div class="bd-thread">{turns}{typing}</div>'
        '<div class="bd-composer">'
        '<input class="bd-input" type="text" autocomplete="off" spellcheck="false"'
        ' placeholder="Ask about a pull request&hellip;" />'
        '<button class="bd-send" type="button">Send</button>'
        "</div>"
    )


def bot_dock_script() -> str:
    """Hidden-iframe payload that mounts the docked window on the page body."""
    return (
        _SCRIPT.replace("__MARKUP__", json.dumps(bot_dock_markup()))
        .replace("__REPLY__", json.dumps(REPLY))
        .replace("__DOCK_ID__", DOCK_ID)
    )
