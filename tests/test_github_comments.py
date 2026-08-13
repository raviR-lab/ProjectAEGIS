"""Unit tests for GitHub comment formatting and CIG→GitHub PR mapping."""

import unittest

from aegis.core.orchestrator import AegisReport
from aegis.integrations.github_comments import (
    MARKER,
    format_report_markdown,
    parse_pr_map,
    resolve_github_pr_number,
)


class PrMapTest(unittest.TestCase):
    def test_parse_pr_map(self):
        self.assertEqual(parse_pr_map("482:1,500:2"), {482: 1, 500: 2})
        self.assertEqual(parse_pr_map(""), {})
        self.assertEqual(parse_pr_map("nope"), {})

    def test_demo_defaults(self):
        self.assertEqual(resolve_github_pr_number(482), 1)
        self.assertEqual(resolve_github_pr_number(500), 2)
        self.assertEqual(resolve_github_pr_number(1), 1)


class FormatMarkdownTest(unittest.TestCase):
    def test_contains_verdict_and_marker(self):
        report = AegisReport(
            pr_number=482,
            verdict="REVIEW",
            merge_confidence=54.0,
            regression_probability=0.46,
            blast_radius={"affected_services": ["payment-svc"], "files": []},
            recommended_tests=[{"id": "pay-test-refund", "source": "direct_file_coverage"}],
            agent_outputs={"alignment": "ALIGNED", "raw": {}},
            story_alignment={"alignment": "ALIGNED"},
        )
        md = format_report_markdown(report)
        self.assertIn(MARKER, md)
        self.assertIn("`REVIEW`", md)
        self.assertIn("GitHub PR:** #1", md)
        self.assertIn("CIG PR:** #482", md)
        self.assertIn("pay-test-refund", md)
