"""Unit tests for the CIG query layer using a canned client.

Validates the Python-side assembly of blast radius, test selection and
risk features. Cypher execution itself requires a live Neo4j and is
verified via scripts/seed_graph.py once the stack is up.
"""

import unittest

from aegis.graph import queries

PR = 482
CHANGED = ["payment-svc"]
ALL = ["notification-svc", "order-svc", "payment-svc"]

FILES_ROWS = [
    {"path": "payment-svc/src/refund.py", "additions": 42, "deletions": 3,
     "microservice": "payment-svc", "covered_by_tests": ["pay-test-refund"]},
    {"path": "payment-svc/src/gateway.py", "additions": 11, "deletions": 0,
     "microservice": "payment-svc", "covered_by_tests": ["pay-test-gateway"]},
]

UPSTREAM_ROWS = [
    {"service": "order-svc", "hops": 1},
    {"service": "notification-svc", "hops": 2},
]

DETAIL_ROWS = [
    {"service": "payment-svc",
     "routes": ["POST /payments/charge", "POST /payments/refund"],
     "flows": ["Checkout Payment", "Order Refund"],
     "incidents": ["INC-1042"],
     "tests": ["pay-test-charge", "pay-test-refund", "pay-test-gateway"]},
    {"service": "order-svc",
     "routes": ["POST /orders/checkout", "GET /orders"],
     "flows": ["Checkout Payment", "Order History"],
     "incidents": [],
     "tests": ["ord-test-checkout", "ord-test-api"]},
    {"service": "notification-svc",
     "routes": [],
     "flows": [],
     "incidents": ["INC-2099"],
     "tests": []},
]

REGRESSION_ROWS = [
    {"id": "pay-test-charge", "name": "test_charge", "suite": "payment",
     "type": "unit", "duration": 0.4, "incident_ids": ["INC-1042"]},
    {"id": "notif-test-alert", "name": "test_alert_delivery", "suite": "notification",
     "type": "unit", "duration": 0.2, "incident_ids": ["INC-2099"]},
]

STORY_ROWS = [
    {"key": "AEG-221", "title": "Support refunds via the gateway", "epic": "Payments", "status": "in_progress"},
]

ALIGN_FILE_ROWS = [
    {"path": "payment-svc/src/refund.py", "microservice": "payment-svc", "domain": "payments"},
    {"path": "payment-svc/src/gateway.py", "microservice": "payment-svc", "domain": "payments"},
]

MISALIGN_FILE_ROWS = [
    {"path": "payment-svc/src/refund.py", "microservice": "payment-svc", "domain": "payments"},
    {"path": "payment-svc/src/charge.py", "microservice": "payment-svc", "domain": "payments"},
]

MISALIGN_STORY_ROWS = [
    {"key": "AEG-999", "title": "Add dark mode to admin console", "epic": "Platform", "status": "in_progress"},
]

SUITE_ROWS = [{"total": 24}]

RELEASE_ROWS = [
    {"version": "v1.9.0", "deployed_at": "2026-07-16T09:00:00Z", "status": "live",
     "notes": "gateway fixes", "services": ["payment-svc", "order-svc"]},
]

OPEN_INCIDENT_ROWS = [
    {"id": "INC-2099", "severity": "S2",
     "root_cause": "Order status emails not delivered", "service": "notification-svc"},
]

RESOLVED_ROWS = [{"resolved": ["INC-1042"]}]

STATS_ROWS = [
    {"label": "Microservice", "count": 5},
    {"label": "Release", "count": 3},
]


class FakeClient:
    def run(self, query, **params):
        if "MODIFIES" in query and "COVERS" in query:
            return FILES_ROWS
        if "EXPOSES" in query:
            return DETAIL_ROWS
        if "DETECTS" in query:
            return REGRESSION_ROWS
        if "length" in query:
            return UPSTREAM_ROWS
        if "collect(DISTINCT {key" in query or "RETURN collect(DISTINCT {key" in query:
            return [{"stories": STORY_ROWS}]
        if "MATCH (pr" in query and "BELONGS_TO" in query and "RETURN f.path" in query:
            return ALIGN_FILE_ROWS
        if "TestCase" in query and "count(t)" in query:
            return SUITE_ROWS
        if "RELEASED_IN" in query:
            return RELEASE_ROWS
        if "inc.status = 'open'" in query or 'inc.status = "open"' in query:
            return OPEN_INCIDENT_ROWS
        if "inc.status = 'resolved'" in query or 'inc.status = "resolved"' in query:
            return RESOLVED_ROWS
        if "labels(n)[0]" in query:
            return STATS_ROWS
        if "()-[r]->()" in query:
            return [{"rel": "RELEASED_IN", "count": 4}]
        raise AssertionError(f"unexpected query: {query[:80]}")


class QueryLayerTest(unittest.TestCase):
    def setUp(self):
        self.cig = FakeClient()

    def test_blast_radius(self):
        r = queries.blast_radius(self.cig, PR)
        self.assertEqual(r["changed_services"], CHANGED)
        self.assertEqual(r["affected_services"], ALL)
        self.assertEqual(r["upstream_hops"], {"order-svc": [1], "notification-svc": [2]})
        self.assertEqual(len(r["services_detail"]), 3)

    def test_recommended_tests_priority(self):
        tests = queries.recommended_tests(self.cig, PR)
        ids = [t["id"] for t in tests]
        sources = [t["source"] for t in tests]
        self.assertEqual(
            ids,
            ["pay-test-gateway", "pay-test-refund",
             "ord-test-api", "ord-test-checkout", "pay-test-charge",
             "notif-test-alert"],
        )
        self.assertEqual(sources[:2], ["direct_file_coverage", "direct_file_coverage"])
        self.assertIn("affected_service_coverage", sources)
        self.assertIn("regression_history", sources)
        self.assertEqual(ids.count("pay-test-charge"), 1)

    def test_risk_features(self):
        f = queries.risk_features(self.cig, PR)
        self.assertEqual(f["num_files"], 2)
        self.assertEqual(f["churn"], 56)
        self.assertEqual(f["num_affected_services"], 3)
        self.assertEqual(f["past_incidents"], ["INC-1042"])
        self.assertEqual(f["file_test_coverage_ratio"], 1.0)
        self.assertEqual(f["affected_flows"], ["Checkout Payment", "Order History", "Order Refund"])

    def test_story_alignment_aligned(self):
        a = queries.story_alignment(self.cig, PR)
        self.assertEqual(a["alignment"], "ALIGNED")
        self.assertEqual([s["key"] for s in a["linked_stories"]], ["AEG-221"])
        self.assertTrue(all(f["aligned"] for f in a["files"]))
        self.assertEqual(len(a["files"]), 2)

    def test_suite_size(self):
        self.assertEqual(queries.suite_size(self.cig), 24)

    def test_release_history(self):
        releases = queries.release_history(self.cig)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0]["version"], "v1.9.0")
        self.assertEqual(releases[0]["services"], ["payment-svc", "order-svc"])

    def test_open_incidents(self):
        incidents = queries.open_incidents(self.cig)
        self.assertEqual(len(incidents), 1)
        self.assertEqual(incidents[0]["id"], "INC-2099")
        self.assertEqual(incidents[0]["service"], "notification-svc")


class MisalignedClient(FakeClient):
    def run(self, query, **params):
        if "collect(DISTINCT {key" in query:
            return [{"stories": MISALIGN_STORY_ROWS}]
        if "MATCH (pr" in query and "BELONGS_TO" in query and "RETURN f.path" in query:
            return MISALIGN_FILE_ROWS
        return super().run(query, **params)


class StoryAlignmentGapsTest(unittest.TestCase):
    def test_gaps(self):
        a = queries.story_alignment(MisalignedClient(), PR)
        self.assertEqual(a["alignment"], "GAPS")


if __name__ == "__main__":
    unittest.main()
