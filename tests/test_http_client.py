"""Unit tests for http_client.py — token resolution and header building."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import threading  # noqa: E402

import requests  # noqa: E402

from http_client import (  # noqa: E402
    RETRY_TOTAL,
    build_headers,
    friendly_error,
    get_session,
    resolve_token,
)


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
    def test_session_is_cached_within_a_thread(self):
        self.assertIs(get_session(), get_session())

    def test_session_has_https_adapter_mounted(self):
        s = get_session()
        self.assertIn("https://", s.adapters)

    def test_each_thread_gets_its_own_session(self):
        """Sharing one Session across threads is a documented hazard, and
        'refresh all' deliberately runs many requests at once."""
        seen = {}

        def grab(name):
            seen[name] = get_session()

        threads = [threading.Thread(target=grab, args=(n,)) for n in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertIsNot(seen["a"], seen["b"])

    def test_retry_budget_rides_out_a_multi_second_outage(self):
        """A dropped TLS connection is retried on the `total` counter only, so
        `total` must be big enough to outlast a brief network/middlebox glitch."""
        retry = get_session().adapters["https://"].max_retries
        self.assertEqual(retry.total, RETRY_TOTAL)
        self.assertGreaterEqual(retry.total, 4)
        # Sum of backoffs must cover more than a couple of seconds.
        cur, window = retry, 0.0
        from urllib3.exceptions import SSLError as U3SSLError
        for _ in range(retry.total):
            cur = cur.increment("GET", "/x", error=U3SSLError("eof"))
            window += cur.get_backoff_time()
        self.assertGreater(window, 10.0, f"retry window only {window}s")


class TestFriendlyError(unittest.TestCase):
    def test_ssl_eof_gets_actionable_text(self):
        exc = requests.exceptions.SSLError(
            "HTTPSConnectionPool(host='api.github.com', port=443): Max retries "
            "exceeded (Caused by SSLError(SSLEOFError(8, '[SSL: "
            "UNEXPECTED_EOF_WHILE_READING] EOF occurred')))")
        msg = friendly_error(exc)
        self.assertIn("連線被中途切斷", msg)
        self.assertIn("防毒", msg)
        self.assertNotIn("HTTPSConnectionPool", msg)  # no raw dump

    def test_timeout_message(self):
        self.assertIn("逾時", friendly_error(requests.exceptions.Timeout("slow")))

    def test_dropped_connection_variants_share_one_message(self):
        """SSLEOFError and 'Connection aborted' are the same problem for the
        user, so both must get the same actionable advice."""
        for text in ("('Connection aborted.', RemoteDisconnected('Remote end "
                     "closed connection without response'))",
                     "('Connection reset by peer')"):
            msg = friendly_error(requests.exceptions.ConnectionError(text))
            self.assertIn("連線被中途切斷", msg)
            self.assertIn("防毒", msg)

    def test_refused_connection_message(self):
        msg = friendly_error(
            requests.exceptions.ConnectionError("Failed to establish a new connection"))
        self.assertIn("無法連線到 GitHub", msg)

    def test_unknown_exception_passes_through(self):
        self.assertEqual(friendly_error(ValueError("某個訊息")), "某個訊息")

    def test_our_own_errors_are_not_rewritten(self):
        from github_api import GitHubError
        original = "cbolong/x 目前沒有任何 GitHub Release。"
        self.assertEqual(friendly_error(GitHubError(original)), original)


if __name__ == "__main__":
    unittest.main(verbosity=2)
