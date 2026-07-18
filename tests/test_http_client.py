"""Unit tests for http_client.py — token resolution and header building."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from http_client import build_headers, get_session, resolve_token  # noqa: E402


class TestResolveToken(unittest.TestCase):
    def test_explicit_token_wins(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env_tok"}):
            self.assertEqual(resolve_token("explicit"), "explicit")

    def test_falls_back_to_env(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env_tok"}):
            self.assertEqual(resolve_token(None), "env_tok")

    def test_none_when_no_token_anywhere(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(resolve_token(None))


class TestBuildHeaders(unittest.TestCase):
    def test_api_headers_have_api_version(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            h = build_headers(None)
        self.assertEqual(h["Accept"], "application/vnd.github+json")
        self.assertIn("X-GitHub-Api-Version", h)
        self.assertNotIn("Authorization", h)

    def test_download_headers_ask_for_octet_stream(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            h = build_headers(None, for_download=True)
        self.assertEqual(h["Accept"], "application/octet-stream")
        self.assertNotIn("X-GitHub-Api-Version", h)

    def test_token_becomes_bearer_auth(self):
        h = build_headers("ghp_abc")
        self.assertEqual(h["Authorization"], "Bearer ghp_abc")

    def test_env_token_used_when_none_passed(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "env_tok"}):
            h = build_headers(None)
        self.assertEqual(h["Authorization"], "Bearer env_tok")

    def test_user_agent_always_present(self):
        self.assertIn("User-Agent", build_headers(None))
        self.assertIn("User-Agent", build_headers("t", for_download=True))


class TestSession(unittest.TestCase):
    def test_session_is_cached_singleton(self):
        self.assertIs(get_session(), get_session())

    def test_session_has_https_adapter_mounted(self):
        s = get_session()
        self.assertIn("https://", s.adapters)


if __name__ == "__main__":
    unittest.main(verbosity=2)
