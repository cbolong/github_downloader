"""GitHub REST API helpers: parse repo URLs and fetch the latest release."""
from __future__ import annotations

import re
from typing import Optional, Tuple

import requests

from http_client import TIMEOUT_API, build_headers, friendly_error, get_session

API_ROOT = "https://api.github.com"


class GitHubError(Exception):
    """Raised when a GitHub API call fails in a way worth showing the user."""


def parse_repo_url(url: str) -> Tuple[str, str]:
    """Extract ``(owner, repo)`` from a GitHub repo URL or ``owner/repo`` string.

    Accepts forms like::

        https://github.com/owner/repo
        https://github.com/owner/repo/
        https://github.com/owner/repo.git
        git@github.com:owner/repo.git
        github.com/owner/repo/tree/main/...
        owner/repo
    """
    if not url or not url.strip():
        raise GitHubError("Repo 連結不可為空。")

    text = url.strip()

    # git@github.com:owner/repo(.git)
    ssh = re.match(r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$", text)
    if ssh:
        return ssh.group("owner"), ssh.group("repo")

    # Strip scheme (https://) and host (github.com/) if present.
    stripped = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", text)
    stripped = re.sub(r"^(www\.)?github\.com/", "", stripped)

    parts = [p for p in stripped.split("/") if p]
    if len(parts) < 2:
        raise GitHubError(f"無法從連結解析出 owner/repo：{url}")

    owner, repo = parts[0], parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def get_latest_release(owner: str, repo: str, token: Optional[str] = None) -> dict:
    """Fetch the latest published (non-draft, non-prerelease) release.

    Returns the parsed JSON dict. Raises :class:`GitHubError` on failure.
    """
    url = f"{API_ROOT}/repos/{owner}/{repo}/releases/latest"
    try:
        resp = get_session().get(url, headers=build_headers(token), timeout=TIMEOUT_API)
    except requests.RequestException as exc:
        raise GitHubError(friendly_error(exc)) from exc

    if resp.status_code == 404:
        # Distinguish "repo not accessible" from "repo exists but no releases".
        _check_repo_exists(owner, repo, token)
        raise GitHubError(
            f"{owner}/{repo} 目前沒有任何 GitHub Release。\n"
            "（Repo 存在，但尚未在 GitHub 上建立過 Release。）"
        )
    if resp.status_code == 401:
        raise GitHubError("GitHub Token 無效或權限不足。")
    if resp.status_code == 403 and "rate limit" in resp.text.lower():
        raise GitHubError("已達 GitHub API 速率限制，請設定 GitHub Token 後再試。")
    if not resp.ok:
        raise GitHubError(f"GitHub API 錯誤（HTTP {resp.status_code}）。")

    return resp.json()


def _check_repo_exists(owner: str, repo: str, token: Optional[str]) -> None:
    """Raise a clear error if the repo itself is not accessible."""
    try:
        r = get_session().get(
            f"{API_ROOT}/repos/{owner}/{repo}",
            headers=build_headers(token),
            timeout=TIMEOUT_API,
        )
    except requests.RequestException:
        return  # network issue; let the caller handle
    if r.status_code == 404:
        hint = "（若為私人 repo，請先在上方填入有效的 GitHub Token 並按「儲存」。）"
        raise GitHubError(f"找不到 {owner}/{repo}，或目前 Token 無權存取。\n{hint}")
    if r.status_code == 401:
        raise GitHubError("GitHub Token 無效或權限不足，無法存取此 repo。")


def fetch_release_info(owner: str, repo: str,
                       token: Optional[str] = None) -> Tuple[dict, str]:
    """Fetch the latest release AND its tag's commit title in one call.

    This is the single entry point used by BOTH the refresh and the download
    flows in the UI, so the two paths can never drift apart. Raises
    :class:`GitHubError` if the release cannot be fetched; the commit title is
    best-effort and degrades to an empty string.
    """
    release = get_latest_release(owner, repo, token=token)
    commit_msg = get_tag_commit_message(
        owner, repo, release.get("tag_name", ""), token=token)
    return release, commit_msg


def get_tag_commit_message(owner: str, repo: str, ref: str,
                           token: Optional[str] = None) -> str:
    """Return the title (first line) of the commit a tag/ref points to.

    Best-effort: returns an empty string on any failure so it never blocks
    showing the release info.
    """
    if not ref:
        return ""
    try:
        resp = get_session().get(
            f"{API_ROOT}/repos/{owner}/{repo}/commits/{ref}",
            headers=build_headers(token),
            timeout=TIMEOUT_API,
        )
        if not resp.ok:
            return ""
        message = (resp.json().get("commit") or {}).get("message", "")
        return message.strip().splitlines()[0] if message.strip() else ""
    except (requests.RequestException, ValueError, KeyError):
        return ""
