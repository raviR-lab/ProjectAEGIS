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

    def test_identity_when_unmapped(self):
        self.assertEqual(resolve_github_pr_number(1), 1)
        self.assertEqual(resolve_github_pr_number(2), 2)


class FormatMarkdownTest(unittest.TestCase):
    def test_contains_verdict_and_marker(self):
        report = AegisReport(
            pr_number=1,
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
        self.assertNotIn("CIG PR:", md)
        self.assertIn("pay-test-refund", md)

    def test_includes_suggested_jira(self):
        report = AegisReport(
            pr_number=2,
            verdict="REJECT",
            story_alignment={"alignment": "GAPS"},
            agent_outputs={"alignment": "GAPS", "raw": {}},
            story_suggestions=[
                {
                    "key": "AEG-1",
                    "title": "Secure demo token issuance",
                    "epic": "platform",
                    "reasons": ["epic 'platform' matches the files' product area"],
                }
            ],
        )
        md = format_report_markdown(report)
        self.assertIn("Suggested Jira ticket", md)
        self.assertIn("AEG-1", md)
