"""Pure-logic unit tests (no network, no GUI) — runnable on any platform."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from downloader import is_source_archive, select_assets  # noqa: E402
from github_api import GitHubError, parse_repo_url  # noqa: E402


class TestParseRepoUrl(unittest.TestCase):
    EXPECTED = ("cbolong", "github_downloader")

    def test_https(self):
        self.assertEqual(parse_repo_url("https://github.com/cbolong/github_downloader"), self.EXPECTED)

    def test_trailing_slash(self):
        self.assertEqual(parse_repo_url("https://github.com/cbolong/github_downloader/"), self.EXPECTED)

    def test_dot_git(self):
        self.assertEqual(parse_repo_url("https://github.com/cbolong/github_downloader.git"), self.EXPECTED)

    def test_extra_path(self):
        self.assertEqual(
            parse_repo_url("https://github.com/cbolong/github_downloader/tree/main/src"), self.EXPECTED)

    def test_no_scheme(self):
        self.assertEqual(parse_repo_url("github.com/cbolong/github_downloader"), self.EXPECTED)

    def test_ssh(self):
        self.assertEqual(parse_repo_url("git@github.com:cbolong/github_downloader.git"), self.EXPECTED)

    def test_short_form(self):
        self.assertEqual(parse_repo_url("cbolong/github_downloader"), self.EXPECTED)

    def test_invalid(self):
        with self.assertRaises(GitHubError):
            parse_repo_url("not-a-url")

    def test_empty(self):
        with self.assertRaises(GitHubError):
            parse_repo_url("   ")


class TestAssetSelection(unittest.TestCase):
    def _release(self):
        return {
            "tag_name": "v1.0.0",
            "assets": [
                {"name": "app-windows.exe", "browser_download_url": "http://x/app.exe", "url": "http://api/1"},
                {"name": "app-bundle.zip", "browser_download_url": "http://x/app.zip", "url": "http://api/2"},
                {"name": "Source code (zip)", "browser_download_url": "http://x/src.zip", "url": "http://api/3"},
                {"name": "Source code (tar.gz)", "browser_download_url": "http://x/src.tgz", "url": "http://api/4"},
            ],
        }

    def test_is_source_archive(self):
        self.assertTrue(is_source_archive("Source code (zip)"))
        self.assertTrue(is_source_archive("source code (tar.gz)"))
        self.assertFalse(is_source_archive("app-windows.exe"))
        self.assertFalse(is_source_archive("release.zip"))

    def test_select_excludes_source_code(self):
        names = [a["name"] for a in select_assets(self._release())]
        self.assertEqual(names, ["app-windows.exe", "app-bundle.zip"])

    def test_select_empty_when_no_assets(self):
        self.assertEqual(select_assets({"assets": []}), [])
        self.assertEqual(select_assets({}), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
