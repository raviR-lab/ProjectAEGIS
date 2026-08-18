"""Unit tests for GitHub → Neo4j sync helpers."""

import unittest

from aegis.graph.sync import prs_from_github_payload, story_keys_in_text


class StoryKeyParseTest(unittest.TestCase):
    def test_finds_jira_key_in_title(self):
        self.assertEqual(
            story_keys_in_text("chore(auth): rotate demo signing key for AEG-1"),
            ["AEG-1"],
        )

    def test_finds_multiple_and_dedupes(self):
        self.assertEqual(
            story_keys_in_text("feat: AEG-4 and AEG-4 again", "See AEG-2"),
            ["AEG-4", "AEG-2"],
        )

    def test_empty(self):
        self.assertEqual(story_keys_in_text(""), [])
        self.assertEqual(story_keys_in_text("no ticket here"), [])


class GithubPayloadTest(unittest.TestCase):
    def test_normalizes_gh_list_with_files(self):
        pulls = prs_from_github_payload([
            {
                "number": 3,
                "title": "feat(admin): dark mode for AEG-5",
                "author": {"login": "rizwanrnt"},
                "baseRefName": "main",
                "headRefName": "feat/aeg-5",
                "state": "OPEN",
                "body": "",
                "files": [{"path": "payment-svc/src/charge.ts", "additions": 12, "deletions": 1}],
            }
        ])
        self.assertEqual(len(pulls), 1)
        self.assertEqual(pulls[0]["number"], 3)
        self.assertEqual(pulls[0]["base"], "main")
        self.assertEqual(pulls[0]["files"][0]["path"], "payment-svc/src/charge.ts")
        self.assertEqual(pulls[0]["files"][0]["additions"], 12)

    def test_normalizes_rest_filename_field(self):
        pulls = prs_from_github_payload([
            {
                "number": 1,
                "title": "refund",
                "user": {"login": "dev"},
                "base": {"ref": "main"},
                "head": {"ref": "feat"},
                "state": "open",
                "files": [{"filename": "payment-svc/src/refund.ts", "additions": 4, "deletions": 0}],
            }
        ])
        self.assertEqual(pulls[0]["files"][0]["path"], "payment-svc/src/refund.ts")

    def test_skips_empty_numbers(self):
        self.assertEqual(prs_from_github_payload([{"title": "no number"}]), [])


if __name__ == "__main__":
    unittest.main()
