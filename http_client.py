"""Shared HTTP layer: one place for timeouts, auth headers, retries.

Both github_api.py (JSON API calls) and downloader.py (asset streaming) go
through here so token injection, timeouts and the retry policy have a single
source of truth. Change auth or timeout behaviour in ONE place.
"""
from __future__ import annotations

import os
import threading
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

try:  # urllib3 ships with requests; import path is stable
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover - defensive
    Retry = None  # type: ignore

# Single source of truth for network tuning.
TIMEOUT_API = 20          # seconds, for small JSON API calls
TIMEOUT_DOWNLOAD = 30     # seconds, for (streamed) asset downloads
CHUNK = 64 * 1024         # bytes per streamed chunk

_API_ACCEPT = "application/vnd.github+json"
_DOWNLOAD_ACCEPT = "application/octet-stream"
_USER_AGENT = "github-release-downloader"

_session_lock = threading.Lock()
_session: Optional[requests.Session] = None


def resolve_token(token: Optional[str]) -> Optional[str]:
    """Return the explicit token, else fall back to the GITHUB_TOKEN env var."""
    return token or os.environ.get("GITHUB_TOKEN")


def build_headers(token: Optional[str], *, for_download: bool = False) -> dict:
    """Build request headers with optional bearer auth.

    ``for_download=True`` asks GitHub for the raw asset bytes; otherwise we ask
    for the JSON API representation.
    """
    headers = {
        "Accept": _DOWNLOAD_ACCEPT if for_download else _API_ACCEPT,
        "User-Agent": _USER_AGENT,
    }
    if not for_download:
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    resolved = resolve_token(token)
    if resolved:
        headers["Authorization"] = f"Bearer {resolved}"
    return headers


def get_session() -> requests.Session:
    """Return a process-wide Session with connection pooling + retries.

    Retries transient failures (connection errors and 5xx / 429) with
    exponential backoff, which smooths over brief network hiccups. Created
    lazily and cached; safe to call from multiple threads.
    """
    global _session
    if _session is not None:
        return _session
    with _session_lock:
        if _session is not None:  # re-check inside the lock
            return _session
        session = requests.Session()
        if Retry is not None:
            retry = Retry(
                total=3,
                connect=3,
                read=3,
                backoff_factor=0.5,  # 0.5s, 1s, 2s between attempts
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(["GET"]),
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
        _session = session
        return _session
