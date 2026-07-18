"""Unit tests for store.py — Job persistence and settings, using a temp
config dir so the real user config is never touched."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import store  # noqa: E402
from store import Job, load_jobs, load_settings, save_jobs, save_settings  # noqa: E402


class _TempConfig:
    """Context manager that points store's config dir at a temp folder."""
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._patch = mock.patch.object(store, "_config_dir", return_value=self._tmp.name)

    def __enter__(self):
        self._patch.start()
        return self._tmp.name

    def __exit__(self, *exc):
        self._patch.stop()
        self._tmp.cleanup()


class TestJobModel(unittest.TestCase):
    def test_full_name(self):
        j = Job(repo_url="x", owner="cbolong", repo="ice_connector")
        self.assertEqual(j.full_name, "cbolong/ice_connector")

    def test_defaults(self):
        j = Job(repo_url="x", owner="o", repo="r")
        self.assertEqual(j.dest_folder, "")
        self.assertEqual(j.commit_message, "")


class TestJobsPersistence(unittest.TestCase):
    def test_round_trip(self):
        with _TempConfig():
            jobs = [
                Job(repo_url="u1", owner="o1", repo="r1", dest_folder="D:/a", latest_tag="v1"),
                Job(repo_url="u2", owner="o2", repo="r2"),
            ]
            save_jobs(jobs)
            loaded = load_jobs()
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].owner, "o1")
            self.assertEqual(loaded[0].dest_folder, "D:/a")
            self.assertEqual(loaded[1].repo, "r2")

    def test_missing_file_returns_empty(self):
        with _TempConfig():
            self.assertEqual(load_jobs(), [])

    def test_corrupt_json_returns_empty(self):
        with _TempConfig() as d:
            with open(os.path.join(d, "jobs.json"), "w") as f:
                f.write("{ this is not valid json ]")
            self.assertEqual(load_jobs(), [])

    def test_old_job_without_new_fields(self):
        # Simulate a jobs.json written by an older version (no commit_message).
        with _TempConfig() as d:
            old = [{"repo_url": "u", "owner": "o", "repo": "r", "dest_folder": "D:/"}]
            with open(os.path.join(d, "jobs.json"), "w") as f:
                json.dump(old, f)
            loaded = load_jobs()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].commit_message, "")  # defaulted

    def test_entry_missing_required_keys_is_skipped(self):
        with _TempConfig() as d:
            data = [
                {"repo_url": "u", "owner": "o", "repo": "r"},  # valid
                {"owner": "o2"},                               # missing repo_url/repo
            ]
            with open(os.path.join(d, "jobs.json"), "w") as f:
                json.dump(data, f)
            loaded = load_jobs()
            self.assertEqual(len(loaded), 1)

    def test_unknown_extra_field_ignored(self):
        with _TempConfig() as d:
            data = [{"repo_url": "u", "owner": "o", "repo": "r", "bogus": 123}]
            with open(os.path.join(d, "jobs.json"), "w") as f:
                json.dump(data, f)
            loaded = load_jobs()
            self.assertEqual(len(loaded), 1)
            self.assertFalse(hasattr(loaded[0], "bogus"))


class TestSettingsPersistence(unittest.TestCase):
    def test_round_trip(self):
        with _TempConfig():
            save_settings({"token": "ghp_secret"})
            self.assertEqual(load_settings().get("token"), "ghp_secret")

    def test_missing_returns_empty_dict(self):
        with _TempConfig():
            self.assertEqual(load_settings(), {})

    def test_corrupt_returns_empty_dict(self):
        with _TempConfig() as d:
            with open(os.path.join(d, "settings.json"), "w") as f:
                f.write("not json")
            self.assertEqual(load_settings(), {})

    def test_non_dict_json_returns_empty(self):
        with _TempConfig() as d:
            with open(os.path.join(d, "settings.json"), "w") as f:
                json.dump(["a", "list"], f)
            self.assertEqual(load_settings(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
