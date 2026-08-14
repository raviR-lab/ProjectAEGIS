"""Config-only tests for Jenkins + Teams MCP integrations (no live npx/network)."""

import tempfile
import unittest
from pathlib import Path

from aegis import config
from aegis.integrations.jenkins_client import jenkins_configured
from aegis.integrations.mcp_runtime import (
    JENKINS_MCP_PACKAGE,
    TEAMS_MCP_PACKAGE,
    RATE_LIMITS,
    jenkins_mcp_details,
    teams_mcp_details,
)
from aegis.integrations.teams_client import teams_configured


class JenkinsConfigTest(unittest.TestCase):
    def test_package_pinned(self):
        self.assertIn("@kud/mcp-jenkins", JENKINS_MCP_PACKAGE)

    def test_configured_is_bool(self):
        self.assertIsInstance(jenkins_configured(), bool)

    def test_token_quality(self):
        self.assertEqual(config.jenkins_token_quality("")[0], "invalid")
        self.assertEqual(config.jenkins_token_quality("short")[0], "invalid")
        self.assertEqual(config.jenkins_token_quality("A" * 20)[0], "ok")


class TeamsConfigTest(unittest.TestCase):
    def test_package_pinned(self):
        self.assertIn("@floriscornel/teams-mcp", TEAMS_MCP_PACKAGE)

    def test_configured_is_bool(self):
        self.assertIsInstance(teams_configured(), bool)


class McpDetailsTest(unittest.TestCase):
    def test_jenkins_details_no_secret(self):
        details = jenkins_mcp_details()
        blob = " ".join(str(v) for v in details.values())
        self.assertNotIn("MCP_JENKINS_API_TOKEN", blob)
        self.assertIn("transport", details)
        self.assertIn("kind", details)

    def test_teams_details_no_secret(self):
        details = teams_mcp_details()
        self.assertIn("transport", details)
        self.assertIn("read_only", details)
        self.assertIn("kind", details)

    def test_ratelimits_cover_new_integrations(self):
        self.assertIn("jenkins", RATE_LIMITS)
        self.assertIn("teams", RATE_LIMITS)


class NewKeysPersistTest(unittest.TestCase):
    def test_jenkins_and_teams_keys_in_allowlist(self):
        for key in (
            "JENKINS_URL",
            "JENKINS_USER",
            "JENKINS_API_TOKEN",
            "JENKINS_SOURCE",
            "MCP_JENKINS_COMMAND",
            "MCP_JENKINS_PACKAGE",
            "MCP_JENKINS_ARGS",
            "TEAMS_SOURCE",
            "TEAMS_MCP_READ_ONLY",
            "MCP_TEAMS_COMMAND",
            "MCP_TEAMS_PACKAGE",
            "MCP_TEAMS_ARGS",
        ):
            self.assertIn(key, config.MCP_CONFIG_KEYS)

    def test_jenkins_token_is_secret(self):
        self.assertIn("JENKINS_API_TOKEN", config.SECRET_KEYS)

    def test_apply_updates_persists_new_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("", encoding="utf-8")
            saved = config.apply_updates(
                {
                    "JENKINS_URL": "https://ci.example.com",
                    "JENKINS_USER": "builder",
                    "JENKINS_API_TOKEN": "sekret-token-123",
                    "MCP_TEAMS_PACKAGE": "@floriscornel/teams-mcp@0.9.0",
                    "TEAMS_MCP_READ_ONLY": "true",
                },
                env_path=path,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("JENKINS_URL=https://ci.example.com", text)
            self.assertIn("JENKINS_API_TOKEN=sekret-token-123", text)
            self.assertIn("MCP_TEAMS_PACKAGE=@floriscornel/teams-mcp@0.9.0", text)

    def test_apply_updates_skips_empty_jenkins_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("JENKINS_API_TOKEN=keepme\n", encoding="utf-8")
            saved = config.apply_updates({"JENKINS_API_TOKEN": ""}, env_path=path)
            self.assertNotIn("JENKINS_API_TOKEN", saved)
            self.assertIn("JENKINS_API_TOKEN=keepme", path.read_text(encoding="utf-8"))