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
    status: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"


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
