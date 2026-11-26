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

# Retry budget. NOTE: urllib3 classifies an SSLError as neither a "connect"
# nor a "read" error, so ONLY ``total`` governs how often a dropped TLS
# connection is retried — setting connect=/read= here would be decorative.
# total=4 with backoff_factor=1.0 retries at ~0s, 2s, 4s, 8s, i.e. it rides out
# a disruption lasting up to ~14s instead of giving up after ~3s.
RETRY_TOTAL = 4
RETRY_BACKOFF = 1.0
RETRY_JITTER = 0.3        # spreads out the burst when "全部重新整理" fires

# One Session per thread. Worker threads are short-lived (one per refresh or
# download), so this both removes the documented thread-safety hazard of
# sharing a Session across threads and prevents a pool of idle connections
# from going stale between operations. Within a single operation the session
# is still reused, which is where connection pooling actually pays off.
_local = threading.local()


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


def _build_session() -> requests.Session:
    session = requests.Session()
    if Retry is not None:
        kwargs = dict(
            total=RETRY_TOTAL,
            backoff_factor=RETRY_BACKOFF,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]),
            raise_on_status=False,
        )
        try:  # backoff_jitter needs urllib3 >= 2.0
            retry = Retry(backoff_jitter=RETRY_JITTER, **kwargs)
        except TypeError:  # pragma: no cover - urllib3 1.x fallback
            retry = Retry(**kwargs)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
    return session


def get_session() -> requests.Session:
    """Return this thread's Session (connection pooling + retries).

    Each thread gets its own Session; see the note on ``_local`` above.
    """
    session = getattr(_local, "session", None)
    if session is None:
        session = _build_session()
        _local.session = session
    return session


# A connection that was killed mid-flight surfaces with different wording
# depending on where it died (TLS layer vs socket layer), but the cause and the
# advice are the same, so they must map to the same message.
_DROPPED_MARKERS = (
    "UNEXPECTED_EOF",
    "EOF occurred",
    "Connection aborted",
    "RemoteDisconnected",
    "Connection reset",
    "ConnectionResetError",
)


def friendly_error(exc: BaseException) -> str:
    """Turn a network exception into a short, actionable message.

    Shared by every caller that surfaces a failure to the user, so refresh and
    download report the same wording for the same underlying problem. Anything
    that is not a recognised network error (e.g. a GitHubError we raised
    ourselves) is passed through unchanged.
    """
    text = str(exc)
    if isinstance(exc, requests.exceptions.Timeout):
        return (f"連線 GitHub 逾時（單次超過 {TIMEOUT_API} 秒）。\n"
                "請檢查網路或稍後再試。")
    if (isinstance(exc, requests.exceptions.SSLError)
            or any(marker in text for marker in _DROPPED_MARKERS)):
        return ("與 GitHub 的連線被中途切斷。\n"
                f"已自動重試 {RETRY_TOTAL} 次仍失敗，這通常是暫時性的。\n"
                "常見原因：防毒／防火牆的 HTTPS 掃描、VPN、公司網路或連線不穩。\n"
                "請稍後再按一次；若持續發生，可嘗試關閉防毒的 HTTPS/SSL 掃描。")
    if isinstance(exc, requests.exceptions.ConnectionError):
        return ("無法連線到 GitHub（連線被拒絕，或 DNS 查不到）。\n"
                f"已自動重試 {RETRY_TOTAL} 次。請確認網路、VPN 或防火牆設定後再試。")
    return text
