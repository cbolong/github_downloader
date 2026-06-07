"""Select, download and extract GitHub release assets."""
from __future__ import annotations

import os
import tempfile
import zipfile
from typing import Callable, List, Optional

import requests

_TIMEOUT = 30
_CHUNK = 64 * 1024

ProgressCb = Callable[[int], None]  # percent 0-100
LogCb = Callable[[str], None]


def is_source_archive(name: str) -> bool:
    """True for GitHub's auto-generated "Source code" archives, which we skip.

    GitHub keeps these out of a release's ``assets`` array (they live in the
    ``zipball_url`` / ``tarball_url`` fields), so this is mainly a defensive
    double-check against anything literally named like the source archives.
    """
    return name.strip().lower().startswith("source code")


def select_assets(release: dict) -> List[dict]:
    """Pick the assets we should download from a release JSON.

    Uses only the uploaded ``assets`` array, then drops anything that still
    looks like a source-code archive.
    """
    assets = release.get("assets") or []
    return [a for a in assets if not is_source_archive(a.get("name", ""))]


def _auth_headers(token: Optional[str]) -> dict:
    headers = {
        "User-Agent": "github-release-downloader",
        "Accept": "application/octet-stream",
    }
    token = token or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def download_asset(
    asset: dict,
    target_path: str,
    token: Optional[str] = None,
    progress_cb: Optional[ProgressCb] = None,
) -> str:
    """Stream a single asset to ``target_path``, reporting percent progress.

    Prefers the API asset URL with ``Accept: application/octet-stream`` (works
    for private repos too); ``requests`` follows the 302 to the CDN and drops
    the auth header on the cross-host redirect automatically.
    """
    url = asset.get("url") or asset.get("browser_download_url")
    if not url:
        raise RuntimeError(f"資產缺少下載連結：{asset.get('name')}")

    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    with requests.get(url, headers=_auth_headers(token), stream=True, timeout=_TIMEOUT) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        last_pct = -1
        with open(target_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=_CHUNK):
                if not chunk:
                    continue
                fh.write(chunk)
                done += len(chunk)
                if progress_cb and total:
                    pct = min(100, int(done * 100 / total))
                    if pct != last_pct:
                        progress_cb(pct)
                        last_pct = pct
    if progress_cb:
        progress_cb(100)
    return target_path


def _is_within(base: str, target: str) -> bool:
    base = os.path.abspath(base)
    target = os.path.abspath(target)
    try:
        return os.path.commonpath([base, target]) == base
    except ValueError:  # different drives on Windows
        return False


def extract_zip(zip_path: str, dest_dir: str) -> None:
    """Safely extract a zip into ``dest_dir`` (guards against zip-slip)."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            target = os.path.join(dest_dir, member)
            if not _is_within(dest_dir, target):
                raise RuntimeError(f"Zip 含不安全路徑，已中止：{member}")
        zf.extractall(dest_dir)


def terminate_if_running(exe_path: str, log_cb: Optional[LogCb] = None) -> None:
    """If a process is running from exe_path, terminate it before we overwrite.

    Best-effort: never raises, so it cannot block a download.
    Only acts when the file already exists on disk.
    Uses psutil for reliable cross-platform process enumeration; if psutil is
    not installed the function is a silent no-op.
    """
    if not os.path.isfile(exe_path):
        return
    try:
        import psutil  # optional dependency; not available in tests on Linux CI
    except ImportError:
        return

    abs_path = os.path.abspath(exe_path).lower()
    for proc in psutil.process_iter(["pid", "exe", "name"]):
        try:
            proc_exe = proc.info.get("exe") or ""
            if not proc_exe:
                continue
            if os.path.abspath(proc_exe).lower() != abs_path:
                continue
            # Found a matching process.
            pid = proc.info["pid"]
            name = proc.info["name"] or "unknown"
            if log_cb:
                log_cb(f"偵測到 {name}（PID {pid}）正在執行，正在關閉…")
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
            if log_cb:
                log_cb("已關閉執行中的程序，繼續下載…")
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            # NoSuchProcess  — process exited between iter and terminate (race)
            # AccessDenied   — process needs admin rights to kill; skip silently,
            #                  the download will fail with a clear OS error
            pass


def run_job_download(
    release: dict,
    dest_dir: str,
    token: Optional[str] = None,
    progress_cb: Optional[ProgressCb] = None,
    log_cb: Optional[LogCb] = None,
) -> None:
    """Download (and extract zips) every non-source asset into ``dest_dir``."""

    def log(msg: str) -> None:
        if log_cb:
            log_cb(msg)

    assets = select_assets(release)
    if not assets:
        raise RuntimeError("這個 release 沒有可下載的檔案（已排除 source code）。")

    os.makedirs(dest_dir, exist_ok=True)
    count = len(assets)
    for idx, asset in enumerate(assets, start=1):
        name = asset.get("name", "asset")
        prefix = f"[{idx}/{count}] {name}"

        if name.lower().endswith(".zip"):
            log(f"{prefix}：下載中…")
            with tempfile.TemporaryDirectory() as tmp:
                tmp_zip = os.path.join(tmp, name)
                download_asset(asset, tmp_zip, token=token, progress_cb=progress_cb)
                log(f"{prefix}：解壓中…")
                extract_zip(tmp_zip, dest_dir)
            log(f"{prefix}：完成（已解壓）")
        else:
            target_path = os.path.join(dest_dir, name)
            if name.lower().endswith(".exe"):
                terminate_if_running(target_path, log_cb=log_cb)
            log(f"{prefix}：下載中…")
            download_asset(asset, target_path, token=token, progress_cb=progress_cb)
            log(f"{prefix}：完成")

    log("全部完成 ✓")
