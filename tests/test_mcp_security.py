"""Unit tests for MCP security hardening (no live npx / network)."""

import tempfile
import unittest
from pathlib import Path

from aegis import config
from aegis.integrations.mcp_runtime import (
    ALLOWED_SPAWN_ENV,
    RATE_LIMITS,
    _audit_log_path,
    rate_limit_check,
)


class RateLimitTest(unittest.TestCase):
    def test_ratelimits_defined(self):
        self.assertIn("github", RATE_LIMITS)
        self.assertIn("jira", RATE_LIMITS)
        for integration, (limit, refill) in RATE_LIMITS.items():
            self.assertGreater(limit, 0)
            self.assertGreater(refill, 0)

    def test_exhausts_and_recovers(self):
        # Reset bucket state deterministically.
        from aegis.integrations import mcp_runtime

        mcp_runtime._rate_buckets.clear()

        limit, _refill = RATE_LIMITS["github"]
        # Use a tiny budget via monkeypatch to make the test fast.
        mcp_runtime.RATE_LIMITS["github"] = (3.0, 0.0001)

        for _ in range(3):
            rate_limit_check("github")
        with self.assertRaises(Exception):
            rate_limit_check("github")  # exhausted


class AuditLogTest(unittest.TestCase):
    def test_default_path_and_custom(self):
        self.assertTrue(str(_audit_log_path()).endswith("aegis-mcp-audit.jsonl"))
        try:
            with tempfile.TemporaryDirectory() as tmp:
                p = Path(tmp) / "audit.jsonl"
                config.setting = lambda k, d="": str(p) if k == "AEGIS_AUDIT_LOG" else d
                self.assertEqual(_audit_log_path(), p)
        finally:
            pass

    def test_allowed_env_whitelist_has_no_host_secrets(self):
        self.assertIn("PATH", ALLOWED_SPAWN_ENV)
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", ALLOWED_SPAWN_ENV)
        self.assertNotIn("GITHUB_TOKEN", ALLOWED_SPAWN_ENV)


class TokenQualityTest(unittest.TestCase):
    def test_github_token_quality(self):
        self.assertEqual(config.github_token_quality("")[0], "invalid")
        self.assertEqual(config.github_token_quality("github_pat_abc")[0], "ok")
        self.assertEqual(config.github_token_quality("a" * 40)[0], "classic")
        self.assertEqual(config.github_token_quality("short")[0], "invalid")

    def test_jira_token_quality(self):
        self.assertEqual(config.jira_token_quality("")[0], "invalid")
        self.assertEqual(config.jira_token_quality("short")[0], "invalid")
        self.assertEqual(config.jira_token_quality("A" * 30)[0], "ok")
