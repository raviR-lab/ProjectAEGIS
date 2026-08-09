"""Unit tests for orchestrator report assembly and number parsing."""

import unittest

from aegis.core.orchestrator import (
    AegisReport,
    _extract_number,
    deterministic_regression,
    deterministic_verdict,
    format_report,
)


class NumberParsingTest(unittest.TestCase):
    def test_extract_number(self):
        text = (
            "REGRESSION_PROBABILITY=0.42\n"
            "MERGE_CONFIDENCE: 71\n"
            "REASON: moderate churn"
        )
        self.assertAlmostEqual(_extract_number(text, "REGRESSION_PROBABILITY", None), 0.42)
        self.assertAlmostEqual(_extract_number(text, "MERGE_CONFIDENCE", None), 71.0)

    def test_extract_number_clamps_probability(self):
        self.assertEqual(_extract_number("REGRESSION_PROBABILITY=1.7", "REGRESSION_PROBABILITY", None), 1.0)
        self.assertIsNone(_extract_number("REGRESSION_PROBABILITY=-0.2", "REGRESSION_PROBABILITY", None))

    def test_extract_number_fallback(self):
        self.assertIsNone(_extract_number("no numbers here", "MERGE_CONFIDENCE", None))
        self.assertEqual(_extract_number("no numbers here", "MERGE_CONFIDENCE", 50.0), 50.0)


class DeterministicRegressionTest(unittest.TestCase):
    def test_high_risk_change(self):
        features = {
            "churn": 800,
            "num_affected_services": 3,
            "past_incidents": ["INC-1"],
            "affected_flows": ["Checkout"],
            "file_test_coverage_ratio": 0.5,
        }
        self.assertGreater(deterministic_regression(features), 0.3)

    def test_low_risk_change(self):
        features = {
            "churn": 4,
            "num_affected_services": 1,
            "past_incidents": [],
            "affected_flows": [],
            "file_test_coverage_ratio": 1.0,
        }
        self.assertLessEqual(deterministic_regression(features), 0.05)


class DeterministicVerdictTest(unittest.TestCase):
    def test_aligned_safe_approve(self):
        self.assertEqual(deterministic_verdict(95.0, "ALIGNED", 0.05), "APPROVE")

    def test_aligned_risky_review(self):
        self.assertEqual(deterministic_verdict(54.4, "ALIGNED", 0.456), "REVIEW")

    def test_gaps_reject(self):
        self.assertEqual(deterministic_verdict(55.8, "GAPS", 0.442), "REJECT")

    def test_low_confidence_reject(self):
        self.assertEqual(deterministic_verdict(20.0, "ALIGNED", 0.8), "REJECT")


class FormatReportTest(unittest.TestCase):
    def test_format_report(self):
        report = AegisReport(
            pr_number=482,
            verdict="REVIEW",
            merge_confidence=60.0,
            regression_probability=0.4,
            deterministic_features={"affected_flows": ["Checkout"], "past_incidents": ["INC-1"]},
            blast_radius={"affected_services": ["order-svc", "payment-svc"]},
            recommended_tests=[{"id": "pay-test-refund", "source": "direct_file_coverage"}],
            agent_outputs={"alignment": "ALIGNED", "raw": {}},
        )
        formatted = format_report(report)
        self.assertIn('"verdict": "REVIEW"', formatted)
        self.assertIn('"pay-test-refund"', formatted)


if __name__ == "__main__":
    unittest.main()
