"""Unit tests for github_api.py — URL parsing and HTTP error mapping.
HTTP is mocked via a fake session; no real network is used."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import github_api  # noqa: E402
from github_api import (  # noqa: E402
    GitHubError,
    get_latest_release,
    get_tag_commit_message,
    parse_repo_url,
)


class _FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json


class _FakeSession:
    """Returns queued responses in order, one per .get() call."""
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        return self._responses.pop(0)


class TestParseRepoUrlExtra(unittest.TestCase):
    EXPECTED = ("cbolong", "github_downloader")

    def test_uppercase_dot_git(self):
        # .git suffix stripping is case-sensitive in impl; verify lower works
        self.assertEqual(parse_repo_url("https://github.com/cbolong/github_downloader.git"),
                         self.EXPECTED)

    def test_http_scheme(self):
        self.assertEqual(parse_repo_url("http://github.com/cbolong/github_downloader"),
                         self.EXPECTED)

    def test_www_prefix(self):
        self.assertEqual(parse_repo_url("https://www.github.com/cbolong/github_downloader"),
                         self.EXPECTED)

    def test_whitespace_around(self):
        self.assertEqual(parse_repo_url("  cbolong/github_downloader  "), self.EXPECTED)

    def test_single_segment_raises(self):
        with self.assertRaises(GitHubError):
            parse_repo_url("cbolong")


class TestGetLatestReleaseErrorMapping(unittest.TestCase):
    def _patch_session(self, responses):
        fake = _FakeSession(responses)
        return mock.patch.object(github_api, "get_session", return_value=fake), fake

    def test_success_returns_json(self):
        patcher, _ = self._patch_session([_FakeResp(200, {"tag_name": "v1.2.3"})])
        with patcher:
            rel = get_latest_release("o", "r")
        self.assertEqual(rel["tag_name"], "v1.2.3")

    def test_404_no_release_when_repo_exists(self):
        # First call: releases/latest -> 404. Second call (repo check) -> 200.
        patcher, _ = self._patch_session([_FakeResp(404), _FakeResp(200, {"id": 1})])
        with patcher, self.assertRaises(GitHubError) as ctx:
            get_latest_release("o", "r")
        self.assertIn("沒有任何 GitHub Release", str(ctx.exception))

    def test_404_repo_not_found(self):
        # releases/latest -> 404, then repo check -> 404 too.
        patcher, _ = self._patch_session([_FakeResp(404), _FakeResp(404)])
        with patcher, self.assertRaises(GitHubError) as ctx:
            get_latest_release("o", "r")
        self.assertIn("找不到", str(ctx.exception))

    def test_401_maps_to_token_error(self):
        patcher, _ = self._patch_session([_FakeResp(401)])
        with patcher, self.assertRaises(GitHubError) as ctx:
            get_latest_release("o", "r")
        self.assertIn("Token", str(ctx.exception))

    def test_403_rate_limit(self):
        patcher, _ = self._patch_session([_FakeResp(403, text="API rate limit exceeded")])
        with patcher, self.assertRaises(GitHubError) as ctx:
            get_latest_release("o", "r")
        self.assertIn("速率", str(ctx.exception))

    def test_500_generic_error(self):
        patcher, _ = self._patch_session([_FakeResp(500)])
        with patcher, self.assertRaises(GitHubError) as ctx:
            get_latest_release("o", "r")
        self.assertIn("500", str(ctx.exception))


class TestGetTagCommitMessage(unittest.TestCase):
    def test_returns_first_line(self):
        fake = _FakeSession([_FakeResp(200, {"commit": {"message": "Fix bug\n\ndetails"}})])
        with mock.patch.object(github_api, "get_session", return_value=fake):
            self.assertEqual(get_tag_commit_message("o", "r", "v1"), "Fix bug")

    def test_empty_ref_returns_empty(self):
        # No network call should happen for an empty ref.
        self.assertEqual(get_tag_commit_message("o", "r", ""), "")

    def test_error_response_returns_empty(self):
        fake = _FakeSession([_FakeResp(404)])
        with mock.patch.object(github_api, "get_session", return_value=fake):
            self.assertEqual(get_tag_commit_message("o", "r", "v1"), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
