"""Config-only MCP status helpers (no live npx / network)."""

import unittest

from aegis.integrations.github_client import github_configured
from aegis.integrations.jira_client import jira_configured, project_key
from aegis.integrations.mcp_runtime import mcp_status_failed, mcp_status_unconfigured


class McpConfigHelpersTest(unittest.TestCase):
    def test_github_configured_is_bool(self):
        self.assertIsInstance(github_configured(), bool)

    def test_jira_configured_is_bool(self):
        self.assertIsInstance(jira_configured(), bool)

    def test_project_key_default(self):
        self.assertTrue(project_key())
        self.assertEqual(project_key(), project_key().upper())

    def test_status_helpers(self):
        missing = mcp_status_unconfigured("not set")
        self.assertFalse(missing["configured"])
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"], "not set")

        class _Err(RuntimeError):
            status = 401
            body = "Unauthorized"

        failed = mcp_status_failed(_Err("boom"))
        self.assertTrue(failed["configured"])
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["status"], 401)
        self.assertEqual(failed["body"], "Unauthorized")
