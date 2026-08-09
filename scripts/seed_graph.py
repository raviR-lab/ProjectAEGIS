"""Seed the CIG with a realistic e-commerce topology and demo PRs.

Usage: python scripts/seed_graph.py [--pr 482]
Without --pr it seeds the graph and runs a full analysis for PR #482
(high blast radius) and PR #500 (isolated change) for comparison.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from aegis.graph import ingest, queries, schema  # noqa: E402
from aegis.graph.neo4j import CIGClient  # noqa: E402

MICROSERVICES = {
    "payment-svc": dict(domain="payments", owner="billing-team", tech="python"),
    "order-svc": dict(domain="commerce", owner="checkout-team", tech="python"),
    "inventory-svc": dict(domain="commerce", owner="checkout-team", tech="go"),
    "auth-svc": dict(domain="platform", owner="platform-team", tech="python"),
    "notification-svc": dict(domain="platform", owner="platform-team", tech="go"),
}

# consumer DEPENDS_ON dependency
DEPENDENCIES = [
    ("order-svc", "payment-svc"),
    ("order-svc", "inventory-svc"),
    ("notification-svc", "order-svc"),
]

FILES = [
    ("payment-svc/src/charge.py", "payment-svc", "python"),
    ("payment-svc/src/refund.py", "payment-svc", "python"),
    ("payment-svc/src/gateway.py", "payment-svc", "python"),
    ("order-svc/src/checkout.py", "order-svc", "python"),
    ("order-svc/src/order_api.py", "order-svc", "python"),
    ("inventory-svc/src/stock.py", "inventory-svc", "go"),
    ("auth-svc/src/token.py", "auth-svc", "python"),
]

TESTS = [
    ("pay-test-charge", "test_charge", "payment", "unit", "payment,critical", 0.4),
    ("pay-test-refund", "test_refund", "payment", "unit", "payment", 0.3),
    ("pay-test-gateway", "test_gateway", "payment", "integration", "payment,external", 4.2),
    ("ord-test-checkout", "test_checkout", "order", "integration", "order,payment", 6.5),
    ("ord-test-api", "test_order_api", "order", "api", "order", 1.8),
    ("inv-test-stock", "test_stock_reservation", "inventory", "unit", "inventory", 0.2),
    ("auth-test-token", "test_token_validation", "auth", "unit", "auth", 0.1),
]

TEST_COVERAGE = [
    ("pay-test-charge", "payment-svc/src/charge.py"),
    ("pay-test-refund", "payment-svc/src/refund.py"),
    ("pay-test-gateway", "payment-svc/src/gateway.py"),
    ("ord-test-checkout", "order-svc/src/checkout.py"),
    ("ord-test-api", "order-svc/src/order_api.py"),
    ("inv-test-stock", "inventory-svc/src/stock.py"),
    ("auth-test-token", "auth-svc/src/token.py"),
]

ROUTES = [
    ("payment-svc", "POST", "/payments/charge"),
    ("payment-svc", "POST", "/payments/refund"),
    ("order-svc", "POST", "/orders/checkout"),
    ("order-svc", "GET", "/orders"),
    ("inventory-svc", "POST", "/inventory/reserve"),
    ("auth-svc", "POST", "/auth/token"),
]

FLOWS = [
    ("Checkout Payment", "Customer pays for an order at checkout",
     [("POST", "/payments/charge"), ("POST", "/orders/checkout")]),
    ("Order Refund", "Customer receives a refund for a cancelled order",
     [("POST", "/payments/refund")]),
    ("Order History", "Customer views past orders",
     [("GET", "/orders")]),
]

STORIES = [
    ("AEG-221", "Support refunds via the payment gateway", "in_progress", 5, "Payments"),
    ("AEG-207", "Optimize stock reservation during checkout", "done", 3, "Commerce"),
]

INCIDENTS = [
    ("INC-1042", "S1", "resolved", "Payment gateway timeout on charge", "payment-svc", "pay-test-charge"),
    ("INC-1011", "S2", "resolved", "Stock over-reservation in checkout", "inventory-svc", "inv-test-stock"),
]

PRS = [
    (
        482, "feat: route refunds through gateway", "alice", "main", "aeg-221",
        "AEG-221",
        [
            {"path": "payment-svc/src/refund.py", "additions": 42, "deletions": 3},
            {"path": "payment-svc/src/gateway.py", "additions": 11, "deletions": 0},
        ],
    ),
    (
        500, "chore: rotate auth signing keys", "bob", "main", "aeg-999",
        None,
        [
            {"path": "auth-svc/src/token.py", "additions": 2, "deletions": 2},
        ],
    ),
]


def seed(cig) -> None:
    schema.install_schema(cig)

    for name, props in MICROSERVICES.items():
        ingest.ingest_microservice(cig, name, **props)
    for consumer, dependency in DEPENDENCIES:
        ingest.ingest_dependency(cig, consumer, dependency)

    for path, ms, lang in FILES:
        ingest.ingest_code_file(cig, path, language=lang, microservice=ms)

    for id_, name, suite, ttype, tags, duration in TESTS:
        ingest.ingest_test_case(cig, id_, name, suite=suite, test_type=ttype,
                                tags=tags, avg_duration_s=duration)
    for test_id, path in TEST_COVERAGE:
        ingest.link_test_coverage(cig, test_id, path)

    for ms, method, path in ROUTES:
        ingest.ingest_api_route(cig, ms, method, path)
    for name, description, routes in FLOWS:
        ingest.ingest_customer_flow(cig, name, description, *routes)

    for key, title, status, points, epic in STORIES:
        ingest.ingest_jira_story(cig, key, title, status=status, points=points, epic=epic)

    for id_, severity, status, cause, ms, test in INCIDENTS:
        ingest.ingest_incident(cig, id_, severity, status=status, root_cause=cause,
                               microservice=ms, detected_by_test=test)

    for number, title, author, base, head, story, changes in PRS:
        ingest.ingest_pull_request(cig, number, title, author, base=base, head=head)
        ingest.ingest_pr_changes(cig, number, changes)
        if story:
            ingest.link_pr_to_story(cig, number, story)


def analyze(cig, pr_number: int) -> None:
    radius = queries.blast_radius(cig, pr_number)
    tests = queries.recommended_tests(cig, pr_number)
    features = queries.risk_features(cig, pr_number)

    print(f"\n=== PR #{pr_number} analysis ===")
    print(json.dumps(radius, indent=2, default=str))
    print("\nRecommended tests:")
    for t in tests:
        print(f"  - {t['id']} ({t['source']})")
    print("\nRisk features:")
    print(json.dumps(features, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pr", type=int, default=None,
                        help="Analyze a single PR after seeding")
    args = parser.parse_args()

    cig = CIGClient()
    try:
        seed(cig)
        print("Seeded. Graph stats:")
        print(json.dumps(queries.graph_stats(cig), indent=2, default=str))

        if args.pr:
            analyze(cig, args.pr)
        else:
            analyze(cig, 482)
            analyze(cig, 500)
    finally:
        cig.close()


if __name__ == "__main__":
    main()
