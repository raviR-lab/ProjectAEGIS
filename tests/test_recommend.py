"""Unit tests for Jira ticket ranking against a GitHub PR."""

import unittest

from aegis.graph.recommend import rank_jira_stories


STORIES = [
    {"key": "AEG-1", "title": "Secure demo token issuance", "epic": "platform", "status": "done"},
    {"key": "AEG-2", "title": "Customer order history API", "epic": "commerce", "status": "done"},
    {"key": "AEG-4", "title": "Support refunds via the payment gateway", "epic": "payments", "status": "in_progress"},
]


class RankJiraStoriesTest(unittest.TestCase):
    def test_auth_change_picks_token_ticket(self):
        ranked = rank_jira_stories(
            STORIES,
            pr_title="chore(auth): rotate demo signing key to v2",
            files=[{"path": "auth-svc/src/token.ts", "microservice": "auth-svc", "domain": "platform"}],
        )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["key"], "AEG-1")

    def test_payment_change_picks_refund_ticket(self):
        ranked = rank_jira_stories(
            STORIES,
            pr_title="feat(payment): gateway refund validation",
            files=[
                {"path": "payment-svc/src/refund.ts", "microservice": "payment-svc", "domain": "payments"},
                {"path": "payment-svc/src/gateway.ts", "microservice": "payment-svc", "domain": "payments"},
            ],
        )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["key"], "AEG-4")

    def test_wrong_ticket_in_title_still_prefers_file_domain(self):
        ranked = rank_jira_stories(
            STORIES + [
                {
                    "key": "AEG-5",
                    "title": "Add dark mode to admin console",
                    "epic": "platform",
                    "status": "to_do",
                }
            ],
            pr_title="feat(admin): dark mode tokens for AEG-5",
            files=[
                {"path": "payment-svc/src/charge.ts", "microservice": "payment-svc", "domain": "payments"},
            ],
            linked_keys=["AEG-5"],
        )
        self.assertTrue(ranked)
        self.assertEqual(ranked[0]["key"], "AEG-4")
        ranked = rank_jira_stories(
            STORIES,
            pr_title="docs: fix typo",
            files=[{"path": "README.md", "microservice": None, "domain": None}],
        )
        self.assertEqual(ranked, [])


if __name__ == "__main__":
    unittest.main()
