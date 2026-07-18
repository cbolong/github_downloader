"""Unit tests for downloader.py — asset selection, zip safety, progress,
process termination and the overall download orchestration. No real network."""
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import downloader  # noqa: E402
from downloader import (  # noqa: E402
    _make_overall_progress,
    download_asset,
    extract_zip,
    is_source_archive,
    run_job_download,
    select_assets,
    terminate_if_running,
)


class TestSelectAssetsEdgeCases(unittest.TestCase):
    def test_uppercase_exe_extension(self):
        release = {"assets": [
            {"name": "App-Setup.EXE", "url": "u1"},
            {"name": "bundle.zip", "url": "u2"},
        ]}
        self.assertEqual([a["name"] for a in select_assets(release)], ["App-Setup.EXE"])

    def test_uppercase_zip_extension_when_no_exe(self):
        release = {"assets": [{"name": "Portable.ZIP", "url": "u1"}]}
        self.assertEqual([a["name"] for a in select_assets(release)], ["Portable.ZIP"])

    def test_exe_substring_not_at_end_is_not_treated_as_exe(self):
        # "notes.exe.txt" is NOT an exe; with no real exe/zip it falls through.
        release = {"assets": [{"name": "notes.exe.txt", "url": "u1"}]}
        self.assertEqual([a["name"] for a in select_assets(release)], ["notes.exe.txt"])

    def test_only_source_archives_returns_empty(self):
        release = {"assets": [
            {"name": "Source code (zip)", "url": "u1"},
            {"name": "Source code (tar.gz)", "url": "u2"},
        ]}
        self.assertEqual(select_assets(release), [])

    def test_missing_assets_key(self):
        self.assertEqual(select_assets({}), [])
        self.assertEqual(select_assets({"assets": None}), [])


class TestIsSourceArchive(unittest.TestCase):
    def test_variants(self):
        self.assertTrue(is_source_archive("Source code (zip)"))
        self.assertTrue(is_source_archive("  source code (tar.gz)  "))
        self.assertFalse(is_source_archive("mysource.zip"))
        self.assertFalse(is_source_archive(""))


class TestOverallProgress(unittest.TestCase):
    def test_single_file_maps_directly(self):
        seen = []
        cb = _make_overall_progress(0, 1, seen.append)
        for p in (0, 50, 100):
            cb(p)
        self.assertEqual(seen, [0, 50, 100])

    def test_second_of_two_files_lands_in_upper_band(self):
        seen = []
        cb = _make_overall_progress(1, 2, seen.append)  # file index 1 of 2
        cb(0)
        cb(100)
        self.assertEqual(seen, [50, 100])  # band [50, 100]

    def test_none_callback_returns_none(self):
        self.assertIsNone(_make_overall_progress(0, 3, None))

    def test_values_clamped_to_0_100(self):
        seen = []
        cb = _make_overall_progress(0, 1, seen.append)
        cb(150)
        cb(-10)
        self.assertTrue(all(0 <= v <= 100 for v in seen))


class TestDownloadAsset(unittest.TestCase):
    def test_missing_url_raises(self):
        with self.assertRaises(RuntimeError):
            download_asset({"name": "x.exe"}, "/tmp/whatever/x.exe")


class TestExtractZip(unittest.TestCase):
    def test_normal_extract(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            zip_path = os.path.join(d, "a.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                zf.writestr("hello.txt", "hi")
                zf.writestr("sub/deep.txt", "deep")
            dest = os.path.join(d, "out")
            extract_zip(zip_path, dest)
            self.assertTrue(os.path.isfile(os.path.join(dest, "hello.txt")))
            self.assertTrue(os.path.isfile(os.path.join(dest, "sub", "deep.txt")))

    def test_zip_slip_is_blocked(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            zip_path = os.path.join(d, "evil.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                # Malicious member trying to escape the dest dir.
                zf.writestr("../../escape.txt", "pwned")
            dest = os.path.join(d, "out")
            with self.assertRaises(RuntimeError):
                extract_zip(zip_path, dest)


class TestTerminateIfRunning(unittest.TestCase):
    def test_nonexistent_file_is_noop(self):
        logs = []
        terminate_if_running("/no/such/file.exe", log_cb=logs.append)
        self.assertEqual(logs, [])

    def test_existing_idle_file_no_kill_log(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            path = f.name
            f.write(b"x")
        try:
            logs = []
            terminate_if_running(path, log_cb=logs.append)
            self.assertFalse(any("正在關閉" in m for m in logs))
        finally:
            os.unlink(path)


class TestRunJobDownload(unittest.TestCase):
    def setUp(self):
        # Patch network + process bits so we test orchestration only.
        self._orig_download = downloader.download_asset
        self._orig_terminate = downloader.terminate_if_running
        self._orig_extract = downloader.extract_zip
        downloader.terminate_if_running = lambda *a, **k: None

    def tearDown(self):
        downloader.download_asset = self._orig_download
        downloader.terminate_if_running = self._orig_terminate
        downloader.extract_zip = self._orig_extract

    def test_empty_assets_raises(self):
        with self.assertRaises(RuntimeError):
            run_job_download({"assets": []}, "/tmp/x")

    def test_progress_is_monotonic_and_ends_at_100(self):
        def fake_dl(asset, target, token=None, progress_cb=None):
            for p in (0, 50, 100):
                if progress_cb:
                    progress_cb(p)
            return target
        downloader.download_asset = fake_dl

        import tempfile
        events = []
        release = {"assets": [
            {"name": "a.exe", "url": "u1"},
            {"name": "b.exe", "url": "u2"},
        ]}
        with tempfile.TemporaryDirectory() as d:
            run_job_download(release, d, progress_cb=events.append, log_cb=lambda m: None)
        self.assertTrue(all(events[i] <= events[i + 1] for i in range(len(events) - 1)),
                        f"progress went backwards: {events}")
        self.assertEqual(events[-1], 100)

    def test_zip_asset_takes_extract_branch(self):
        calls = {"downloaded": [], "extracted": []}

        def fake_dl(asset, target, token=None, progress_cb=None):
            calls["downloaded"].append(os.path.basename(target))
            return target

        def fake_extract(zip_path, dest):
            calls["extracted"].append(os.path.basename(zip_path))

        downloader.download_asset = fake_dl
        downloader.extract_zip = fake_extract

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            run_job_download({"assets": [{"name": "pkg.zip", "url": "u"}]}, d,
                             log_cb=lambda m: None)
        self.assertEqual(calls["extracted"], ["pkg.zip"])

    def test_exe_asset_calls_terminate(self):
        terminated = []
        downloader.download_asset = lambda a, t, token=None, progress_cb=None: t
        downloader.terminate_if_running = lambda p, log_cb=None: terminated.append(p)

        import tempfile
        with tempfile.TemporaryDirectory() as d:
            run_job_download({"assets": [{"name": "tool.exe", "url": "u"}]}, d,
                             log_cb=lambda m: None)
        self.assertEqual(len(terminated), 1)
        self.assertTrue(terminated[0].endswith("tool.exe"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
