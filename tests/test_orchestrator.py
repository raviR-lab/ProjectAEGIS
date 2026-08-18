"""Unit tests for orchestrator report assembly and number parsing."""

import unittest

from aegis.core.orchestrator import (
    AegisReport,
    CONFIDENCE_MAX,
    GAP_RISK,
    LLM_RISK_WEIGHT,
    SCORE_MAX,
    SECURITY_FAIL_RISK,
    SECURITY_REVIEW_RISK,
    _extract_number,
    breakage_parts,
    deterministic_regression,
    deterministic_security,
    deterministic_verdict,
    format_report,
    quality_risk,
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

    def test_never_exceeds_score_cap(self):
        features = {
            "churn": 50_000,
            "num_affected_services": 20,
            "past_incidents": ["INC-1", "INC-2", "INC-3", "INC-4"],
            "affected_flows": ["Checkout", "Refund"],
            "file_test_coverage_ratio": 0.0,
        }
        self.assertEqual(deterministic_regression(features), SCORE_MAX)
        self.assertEqual(SCORE_MAX, 0.98)
        self.assertEqual(CONFIDENCE_MAX, 98.0)

    def test_gaps_raise_breakage_above_one_percent(self):
        features = {
            "churn": 8,
            "num_affected_services": 1,
            "past_incidents": [],
            "affected_flows": [],
            "file_test_coverage_ratio": 1.0,
            "alignment_gap_ratio": 1.0,
        }
        aligned = deterministic_regression(features, alignment="ALIGNED", security="PASS")
        gapped = deterministic_regression(features, alignment="GAPS", security="PASS")
        self.assertLessEqual(aligned, 0.05)
        self.assertAlmostEqual(gapped, aligned + GAP_RISK, places=3)
        self.assertGreater(gapped, 0.20)

    def test_security_review_raises_breakage(self):
        features = {
            "churn": 8,
            "num_affected_services": 1,
            "past_incidents": [],
            "affected_flows": [],
            "file_test_coverage_ratio": 1.0,
        }
        plain = deterministic_regression(features, alignment="ALIGNED", security="PASS")
        review = deterministic_regression(features, alignment="ALIGNED", security="REVIEW")
        fail = deterministic_regression(features, alignment="ALIGNED", security="FAIL")
        self.assertAlmostEqual(review, plain + SECURITY_REVIEW_RISK, places=3)
        self.assertAlmostEqual(fail, plain + SECURITY_FAIL_RISK, places=3)
        self.assertGreater(review, 0.15)

    def test_gaps_plus_security_stack(self):
        stacked = quality_risk(alignment="GAPS", security="REVIEW", gap_ratio=1.0)
        self.assertAlmostEqual(stacked, GAP_RISK + SECURITY_REVIEW_RISK, places=3)
        features = {
            "churn": 8,
            "num_affected_services": 1,
            "past_incidents": [],
            "affected_flows": [],
            "file_test_coverage_ratio": 1.0,
            "alignment_gap_ratio": 1.0,
        }
        p = deterministic_regression(features, alignment="GAPS", security="REVIEW")
        self.assertGreater(p, 0.40)

    def test_all_pr_analysts_have_a_term(self):
        parts = breakage_parts(
            {
                "churn": 200,
                "num_affected_services": 3,
                "past_incidents": ["INC-1"],
                "affected_flows": ["Checkout"],
                "file_test_coverage_ratio": 0.0,
                "num_files": 2,
                "alignment_gap_ratio": 1.0,
            },
            alignment="GAPS",
            security="REVIEW",
            recommended_tests=[],
            llm_regression=0.4,
        )
        self.assertEqual(
            set(parts),
            {"pr_reviewer", "security", "blast_radius", "risk_analyzer", "test_selector"},
        )
        self.assertGreater(parts["pr_reviewer"], 0)
        self.assertGreater(parts["security"], 0)
        self.assertGreater(parts["blast_radius"], 0)
        self.assertGreater(parts["risk_analyzer"], 0)
        self.assertGreater(parts["test_selector"], 0)
        self.assertAlmostEqual(
            parts["risk_analyzer"],
            min(0.15, 200 / 1000.0) + LLM_RISK_WEIGHT * 0.4,
            places=3,
        )

    def test_llm_risk_adds_not_replaces(self):
        features = {
            "churn": 0,
            "num_affected_services": 1,
            "past_incidents": [],
            "affected_flows": [],
            "file_test_coverage_ratio": 1.0,
            "alignment_gap_ratio": 1.0,
        }
        without = deterministic_regression(features, alignment="GAPS", security="PASS")
        with_llm = deterministic_regression(
            features, alignment="GAPS", security="PASS", llm_regression=1.0,
        )
        self.assertAlmostEqual(with_llm, without + LLM_RISK_WEIGHT, places=3)


class DeterministicVerdictTest(unittest.TestCase):
    def test_aligned_safe_approve(self):
        self.assertEqual(deterministic_verdict(95.0, "ALIGNED", 0.005), "APPROVE")

    def test_aligned_risky_review(self):
        self.assertEqual(deterministic_verdict(54.4, "ALIGNED", 0.456), "REVIEW")

    def test_regression_above_one_percent_not_approve(self):
        self.assertEqual(deterministic_verdict(95.0, "ALIGNED", 0.011), "REVIEW")
        self.assertEqual(deterministic_verdict(95.0, "ALIGNED", 0.05), "REVIEW")
        self.assertEqual(deterministic_verdict(95.0, "ALIGNED", 0.01), "APPROVE")

    def test_gaps_reject(self):
        self.assertEqual(deterministic_verdict(55.8, "GAPS", 0.442), "REJECT")

    def test_gaps_low_risk_still_reject(self):
        self.assertEqual(deterministic_verdict(95.0, "GAPS", 0.05), "REJECT")
        self.assertEqual(
            deterministic_verdict(95.0, "GAPS", 0.05, security="REVIEW"), "REJECT"
        )

    def test_low_confidence_reject(self):
        self.assertEqual(deterministic_verdict(20.0, "ALIGNED", 0.8), "REJECT")

    def test_security_review_blocks_approve(self):
        self.assertEqual(
            deterministic_verdict(95.0, "ALIGNED", 0.05, security="REVIEW"), "REVIEW"
        )

    def test_security_fail_rejects(self):
        self.assertEqual(
            deterministic_verdict(95.0, "ALIGNED", 0.05, security="FAIL"), "REJECT"
        )


class DeterministicSecurityTest(unittest.TestCase):
    def test_auth_path_needs_review(self):
        result = deterministic_security(
            [{"path": "auth-svc/src/token.ts", "microservice": "auth-svc"}]
        )
        self.assertEqual(result["level"], "REVIEW")
        self.assertIn("token", result["findings"])

    def test_plain_payment_passes(self):
        result = deterministic_security(
            [{"path": "payment-svc/src/refund.py", "microservice": "payment-svc"}]
        )
        self.assertEqual(result["level"], "PASS")

    def test_sensitive_with_incidents_fails(self):
        result = deterministic_security(
            [{"path": "auth-svc/src/token.py", "microservice": "auth-svc"}],
            past_incidents=["INC-3301"],
        )
        self.assertEqual(result["level"], "FAIL")


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
