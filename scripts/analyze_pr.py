"""Run an AEGIS PR analysis or deployment assessment from the terminal.

Usage:
  python scripts/analyze_pr.py --pr 482
  python scripts/analyze_pr.py --deploy "v1.12.0" --services payment-svc order-svc
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aegis.core.orchestrator import AegisOrchestrator, format_report  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, help="Pull request number to analyze")
    parser.add_argument("--deploy", metavar="VERSION", help="Run deployment assessment")
    parser.add_argument("--services", nargs="*", help="Services in the release")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    orchestrator = AegisOrchestrator()
    if args.pr:
        report = orchestrator.analyze_pr(args.pr, verbose=args.verbose)
        print(format_report(report))
    elif args.deploy:
        services = args.services or []
        result = orchestrator.assess_deployment(args.deploy, services, verbose=args.verbose)
        for key, value in result.items():
            print(f"{key}: {value}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
