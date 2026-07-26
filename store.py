"""Job model and JSON persistence for the downloader's tracked repos."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from typing import List


@dataclass
class Job:
    repo_url: str
    owner: str
    repo: str
    dest_folder: str = ""
    latest_tag: str = ""
    release_name: str = ""
    published_at: str = ""
    commit_message: str = ""
    downloaded_tag: str = ""   # tag the user last downloaded (may lag latest_tag)
    downloaded_at: str = ""    # local time of that download, "YYYY-MM-DD HH:MM"
    status: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


def version_state(latest_tag: str, downloaded_tag: str) -> str:
    """Classify a job's update status for display.

    Returns one of:
      - "never_downloaded": nothing recorded as downloaded yet
      - "update_available": a newer tag exists on GitHub than what was downloaded
      - "up_to_date": the downloaded tag matches the latest known tag (or the
        latest tag is unknown, in which case we can only say what we have)

    Pure function (no I/O) so the UI badge logic is unit-testable.
    """
    if not downloaded_tag:
        return "never_downloaded"
    if latest_tag and latest_tag != downloaded_tag:
        return "update_available"
    return "up_to_date"


def _config_dir() -> str:
    base = os.environ.get("APPDATA")
    if base:
        path = os.path.join(base, "GitHubReleaseDownloader")
    else:
        path = os.path.join(os.path.expanduser("~"), ".github_release_downloader")
    os.makedirs(path, exist_ok=True)
    return path


def _jobs_file() -> str:
    return os.path.join(_config_dir(), "jobs.json")


def load_jobs() -> List[Job]:
    """Load the saved job list, tolerating a missing or corrupt file."""
    path = _jobs_file()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []

    known = {f.name for f in fields(Job)}
    jobs: List[Job] = []
    for item in data:
        if isinstance(item, dict) and {"repo_url", "owner", "repo"} <= item.keys():
            jobs.append(Job(**{k: v for k, v in item.items() if k in known}))
    return jobs


def save_jobs(jobs: List[Job]) -> None:
    """Atomically persist the job list as JSON."""
    path = _jobs_file()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump([asdict(j) for j in jobs], fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _settings_file() -> str:
    return os.path.join(_config_dir(), "settings.json")


def load_settings() -> dict:
    """Load saved app settings (e.g. the GitHub token), tolerating errors."""
    path = _settings_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> None:
    """Atomically persist app settings as JSON."""
    path = _settings_file()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
