"""Wipe the CIG and rebuild it from live GitHub PRs + Jira issues.

Usage:
  python scripts/seed_graph.py
  python scripts/seed_graph.py --pr 1
  python scripts/seed_graph.py --keep
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aegis.graph import queries  # noqa: E402
from aegis.graph.neo4j import CIGClient  # noqa: E402
from aegis.graph.sync import SyncError, seed  # noqa: E402


def analyze(cig, pr_number: int) -> None:
    radius = queries.blast_radius(cig, pr_number)
    tests = queries.recommended_tests(cig, pr_number)
    features = queries.risk_features(cig, pr_number)
    alignment = queries.story_alignment(cig, pr_number)
    suite = queries.suite_size(cig)

    print(f"\n=== PR #{pr_number} analysis ===")
    print(f"Story alignment: {alignment['alignment']}")
    print(f"  linked stories: {[s['key'] for s in alignment['linked_stories']]}")
    for f in alignment["files"]:
        print(f"  {f['path']}: aligned={f['aligned']} ({f['reason']})")
    print(json.dumps(radius, indent=2, default=str))
    print(f"\nRecommended tests ({len(tests)} of {suite} in suite):")
    for t in tests:
        print(f"  - {t['id']} ({t['source']})")
    print("\nRisk features:")
    print(json.dumps(features, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, default=None, help="Analyze a PR after sync")
    parser.add_argument(
        "--keep", action="store_true",
        help="Do not wipe existing graph nodes (merge live data on top)",
    )
    args = parser.parse_args()

    cig = CIGClient()
    try:
        try:
            summary = seed(cig, wipe=not args.keep)
        except SyncError as exc:
            raise SystemExit(str(exc)) from exc
        print("Synced live GitHub + Jira. Graph stats:")
        print(json.dumps(queries.graph_stats(cig), indent=2, default=str))
        print("\nIngested:")
        print(json.dumps(summary, indent=2, default=str))

        prs = [p["number"] for p in summary["prs"]]
        if args.pr:
            analyze(cig, args.pr)
        elif prs:
            for number in prs:
                analyze(cig, number)
        else:
            print("No GitHub PRs found to analyze.")
    finally:
        cig.close()


if __name__ == "__main__":
    main()
