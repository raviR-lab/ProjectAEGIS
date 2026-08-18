"""Headed Playwright demo: live coding GAP on GitHub PR #3 + Jira AEG-5.

Source of truth
---------------
GitHub: https://github.com/rizwanrnt/dummy-ecommerce/pulls
Jira:   project AEG

  #1  feat(payment): gateway refund validation and audit for AEG-4
      files: payment-svc refund/gateway  → ALIGNED
  #2  chore(auth): rotate demo signing key to v2
      files: auth-svc/src/token.ts
  #3  feat(admin): dark mode tokens for AEG-5
      files: payment-svc/src/charge.ts  → GAPS (Platform ticket, payments code)

Narrative
---------
PR #3 cites live Jira **AEG-5** (admin dark mode / Platform) but the diff is
`payment-svc/src/charge.ts`. AEGIS REJECTS with ALIGNMENT=GAPS and suggests
**AEG-4** (payments) as the better ticket.

Prerequisites
-------------
  docker compose up -d neo4j ollama
  python scripts/seed_graph.py
  streamlit run src/aegis/ui/app.py
  pip install -r requirements-demo.txt && playwright install chromium

Usage
-----
  python scripts/demo_pr_gap.py
  python scripts/demo_pr_gap.py --pause 12 --keep-open
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

from aegis import config
from aegis.graph import schema
from aegis.graph.neo4j import CIGClient
from aegis.graph.sync import refresh_jira_stories, refresh_pull_request

GITHUB_OWNER = "rizwanrnt"
GITHUB_REPO = "dummy-ecommerce"
GITHUB_PULLS = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/pulls"
GITHUB_PR_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/pull/{{n}}"

DEMO_PR = 3
GAP_STORY = "AEG-5"
SUGGESTED_STORY = "AEG-4"


def say(message: str) -> None:
    print(f"\n>>> {message}", flush=True)


def wait_for_dashboard(url: str, timeout_s: float = 45.0) -> None:
    deadline = time.time() + timeout_s
    last_err = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                if 200 <= resp.status < 500:
                    return
        except (urllib.error.URLError, TimeoutError) as exc:
            last_err = exc
        time.sleep(0.6)
    raise RuntimeError(f"Dashboard not reachable at {url}: {last_err}")


def wait_streamlit_idle(page: Page, timeout_ms: int = 90_000) -> None:
    page.wait_for_timeout(400)
    for test_id in ("stSpinner", "stStatusWidget"):
        loc = page.locator(f'[data-testid="{test_id}"]')
        try:
            loc.first.wait_for(state="hidden", timeout=timeout_ms)
        except PlaywrightTimeout:
            pass


def dismiss_github_banners(page: Page) -> None:
    for name in ("Accept", "Accept all", "Got it"):
        btn = page.get_by_role("button", name=name)
        try:
            if btn.count() and btn.first.is_visible():
                btn.first.click(timeout=2000)
        except PlaywrightTimeout:
            pass


def open_pr_analysis(page: Page) -> None:
    page.get_by_role("tab", name="PR Analysis").click()
    page.get_by_text("Pull request", exact=True).wait_for(timeout=20_000)


def select_pr(page: Page, number: int) -> None:
    box = page.locator('[data-testid="stSelectbox"]').filter(has_text="Pull request")
    box.click()
    needle = re.compile(rf"^#{number}\s+[—-]")
    option = page.locator('[role="option"]').filter(has_text=needle)
    if option.count() == 0:
        option = page.get_by_role("option", name=re.compile(rf"^#{number}\b"))
    option.first.click()
    wait_streamlit_idle(page, timeout_ms=20_000)


def click_run_analysis(page: Page) -> None:
    page.get_by_role("button", name="Run AEGIS analysis").click()
    wait_streamlit_idle(page)


def require_live_graph() -> None:
    cig = CIGClient()
    try:
        refresh_jira_stories(cig)
        refresh_pull_request(cig, DEMO_PR)
        rows = cig.run(
            f"MATCH (pr:{schema.PULL_REQUEST} {{number: $n}}) RETURN pr.title AS title",
            n=DEMO_PR,
        )
        if not rows:
            raise RuntimeError(
                f"GitHub PR #{DEMO_PR} is not in the CIG. Run: python scripts/seed_graph.py"
            )
        stories = cig.run(
            f"MATCH (s:{schema.JIRA_STORY} {{key: $k}}) RETURN s.key AS key, s.epic AS epic",
            k=GAP_STORY,
        )
        if not stories:
            raise RuntimeError(f"{GAP_STORY} is not in the CIG. Re-run seed_graph.py")
        say(f"Live gap: PR #{DEMO_PR} → {GAP_STORY} (epic={stories[0].get('epic')})")
    finally:
        cig.close()


def expect_visible(page: Page, text: str, timeout_ms: int = 90_000) -> None:
    page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=timeout_ms)


def act_pause(seconds: float) -> None:
    if seconds > 0:
        time.sleep(seconds)


def github_configured() -> bool:
    return bool(
        config.setting("GITHUB_TOKEN")
        and config.setting("GITHUB_REPO_OWNER")
        and config.setting("GITHUB_REPO_NAME")
    )


def run_demo(args: argparse.Namespace) -> None:
    wait_for_dashboard(args.url)
    say(f"Dashboard is up at {args.url}")
    require_live_graph()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headed, slow_mo=args.slow_mo)
        context = browser.new_context(viewport={"width": 1440, "height": 920})
        github = context.new_page()
        aegis = context.new_page()

        say("Act 1 — GitHub: open dummy-ecommerce pull requests")
        github.goto(GITHUB_PULLS, wait_until="domcontentloaded")
        dismiss_github_banners(github)
        github.get_by_role("link", name=re.compile(r"AEG-5|dark mode", re.I)).first.wait_for(
            timeout=30_000
        )
        act_pause(args.pause)

        say(f"Act 1 — GitHub: open PR #{DEMO_PR} (admin ticket {GAP_STORY}, payment file)")
        github.goto(GITHUB_PR_URL.format(n=DEMO_PR), wait_until="domcontentloaded")
        dismiss_github_banners(github)
        github.get_by_text("AEG-5", exact=False).first.wait_for(timeout=30_000)
        files_tab = github.get_by_role("link", name=re.compile(r"Files changed", re.I))
        if files_tab.count():
            files_tab.first.click()
            github.wait_for_timeout(1200)
        say("GitHub PR #3 cites AEG-5 but touches payment-svc/src/charge.ts")
        act_pause(args.pause)

        say("Act 2 — AEGIS: analyze the same GitHub PR")
        aegis.bring_to_front()
        aegis.goto(args.url, wait_until="domcontentloaded")
        aegis.get_by_role("tab", name="Infrastructure & CIG").wait_for(timeout=30_000)
        wait_streamlit_idle(aegis, timeout_ms=30_000)
        open_pr_analysis(aegis)
        select_pr(aegis, DEMO_PR)
        act_pause(max(args.pause * 0.4, 2))

        say("Act 2 — Run AEGIS (fast). Expect GAPS / REJECT")
        click_run_analysis(aegis)
        expect_visible(aegis, "Misaligned files found")
        expect_visible(aegis, GAP_STORY)
        expect_visible(aegis, SUGGESTED_STORY)
        say(f"Gap: {GAP_STORY} is Platform/admin; charge.ts is payments. Suggest {SUGGESTED_STORY}")
        act_pause(args.pause)

        if github_configured():
            say("Act 3 — Reload GitHub PR to show the AEGIS comment")
            github.bring_to_front()
            github.goto(GITHUB_PR_URL.format(n=DEMO_PR), wait_until="domcontentloaded")
            dismiss_github_banners(github)
            try:
                github.get_by_text("Project AEGIS", exact=False).first.wait_for(timeout=20_000)
                github.get_by_text("Project AEGIS", exact=False).first.scroll_into_view_if_needed()
                say("AEGIS report is on the live GitHub PR conversation")
            except PlaywrightTimeout:
                say("No AEGIS comment visible yet (MCP post may have been skipped)")
            act_pause(args.pause)

        if args.keep_open:
            say("Browser stays open. Press Enter in this terminal to close.")
            try:
                input()
            except EOFError:
                aegis.wait_for_timeout(30_000)

        context.close()
        browser.close()

    say("Demo complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Headed AEGIS coding-GAP demo (PR #3 / AEG-5)")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument("--headed", dest="headed", action="store_true", default=True)
    parser.add_argument("--headless", dest="headed", action="store_false")
    parser.add_argument("--slow-mo", type=int, default=350, help="Playwright slow_mo in ms")
    parser.add_argument("--pause", type=float, default=8.0, help="Seconds to hold each act")
    parser.add_argument("--keep-open", action="store_true", help="Leave the browser open at the end")
    parser.add_argument(
        "--reset-after",
        action="store_true",
        help="Unused (gap lives on GitHub PR #3 / AEG-5)",
    )
    args = parser.parse_args()
    try:
        run_demo(args)
    except PlaywrightTimeout as exc:
        sys.exit(f"Demo timed out waiting for the UI: {exc}")


if __name__ == "__main__":
    main()
