"""Persist MCP settings to .env without wiping secrets."""

import tempfile
import unittest
from pathlib import Path

from aegis import config
from aegis.integrations.mcp_runtime import github_mcp_details, jira_mcp_details


class UpsertEnvTest(unittest.TestCase):
    def test_replaces_existing_and_appends_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("# keep\nGITHUB_REPO_OWNER=old\n", encoding="utf-8")
            config.upsert_env_file(
                {"GITHUB_REPO_OWNER": "new-owner", "GITHUB_REPO_NAME": "demo"},
                path,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("# keep", text)
            self.assertIn("GITHUB_REPO_OWNER=new-owner", text)
            self.assertIn("GITHUB_REPO_NAME=demo", text)
            self.assertNotIn("GITHUB_REPO_OWNER=old", text)

    def test_apply_updates_skips_empty_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("GITHUB_TOKEN=keepme\n", encoding="utf-8")
            saved = config.apply_updates(
                {"GITHUB_TOKEN": "", "GITHUB_REPO_OWNER": "rizwanrnt"},
                env_path=path,
            )
            self.assertIn("GITHUB_REPO_OWNER", saved)
            self.assertNotIn("GITHUB_TOKEN", saved)
            self.assertIn("GITHUB_TOKEN=keepme", path.read_text(encoding="utf-8"))


class SettingHelperTest(unittest.TestCase):
    def test_setting_strips_and_defaults(self):
        self.assertEqual(config.setting("AEGIS_MISSING_KEY_XYZ", "  fallback  "), "fallback")
        self.assertEqual(config.setting("AEGIS_MISSING_KEY_XYZ"), "")


class McpDetailsNoSecretsTest(unittest.TestCase):
    def test_github_details_mask_token(self):
        details = github_mcp_details()
        blob = " ".join(str(v) for v in details.values())
        self.assertNotIn("github_pat_", blob.lower())
        self.assertIn("transport", details)
        self.assertIn("package", details)
        self.assertIn("spawn", details)

    def test_jira_details_mask_token(self):
        details = jira_mcp_details()
        blob = " ".join(str(v) for v in details.values())
        self.assertNotIn("ATATT", blob)
        self.assertIn("env_injected", details)
