"""Config-only MCP status helpers (no live npx / network)."""

import unittest

from aegis.integrations.github_client import github_configured
from aegis.integrations.jira_client import jira_configured, project_key


class McpConfigHelpersTest(unittest.TestCase):
    def test_github_configured_is_bool(self):
        self.assertIsInstance(github_configured(), bool)

    def test_jira_configured_is_bool(self):
        self.assertIsInstance(jira_configured(), bool)

    def test_project_key_default(self):
        self.assertTrue(project_key())
        self.assertEqual(project_key(), project_key().upper())
