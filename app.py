"""GitHub Release Downloader — Tkinter GUI.

Track multiple GitHub repos, see each one's latest release (tag / title / date),
and download its release assets into a chosen folder. ``.exe`` files are placed
as-is; ``.zip`` files are extracted; the auto-generated "Source code" archives
are skipped.
"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, List, Optional

from downloader import run_job_download
from github_api import (
    GitHubError,
    get_latest_release,
    get_tag_commit_message,
    parse_repo_url,
)
from store import Job, load_jobs, load_settings, save_jobs, save_settings

APP_TITLE = "GitHub Release Downloader"


class App:
    """Top-level application: input bar + scrollable list of job cards."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("780x580")
        self.root.minsize(620, 420)

        self.ui_queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self.cards: List["JobCard"] = []
        self._settings = load_settings()

        self._build_top_bar()
        self._build_job_list()

        for job in load_jobs():
            self._add_card(job)

        self.root.after(100, self._drain_queue)

    # ------------------------------------------------------------------ UI
    def _build_top_bar(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top, text="GitHub Repo 連結：").grid(row=0, column=0, sticky="w", pady=2)
        self.url_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.url_var).grid(
            row=0, column=1, columnspan=2, sticky="we", padx=4, pady=2)
        ttk.Button(top, text="＋ 加入", command=self._on_add).grid(
            row=0, column=3, sticky="we", padx=4, pady=2)

        ttk.Label(top, text="下載資料夾：").grid(row=1, column=0, sticky="w", pady=2)
        self.dest_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.dest_var).grid(
            row=1, column=1, sticky="we", padx=4, pady=2)
        ttk.Button(top, text="瀏覽…", command=self._browse_dest).grid(
            row=1, column=2, sticky="we", padx=4, pady=2)

        ttk.Label(top, text="GitHub Token（選填）：").grid(row=2, column=0, sticky="w", pady=2)
        saved_token = self._settings.get("token") or os.environ.get("GITHUB_TOKEN", "")
        self.token_var = tk.StringVar(value=saved_token)
        ttk.Entry(top, textvariable=self.token_var, show="*").grid(
            row=2, column=1, sticky="we", padx=4, pady=2)
        ttk.Button(top, text="儲存", command=self._save_token).grid(
            row=2, column=2, sticky="we", padx=4, pady=2)

        top.columnconfigure(1, weight=1)

    def _build_job_list(self) -> None:
        container = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        container.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.list_frame = ttk.Frame(self.canvas)

        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self._window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._window, width=e.width),
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event) -> None:
        delta = -1 if getattr(event, "delta", 0) > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    # -------------------------------------------------------------- actions
    def _browse_dest(self) -> None:
        folder = filedialog.askdirectory()
        if folder:
            self.dest_var.set(folder)

    def _on_add(self) -> None:
        url = self.url_var.get().strip()
        dest = self.dest_var.get().strip()
        try:
            owner, repo = parse_repo_url(url)
        except GitHubError as exc:
            messagebox.showerror(APP_TITLE, str(exc))
            return
        if not dest:
            messagebox.showwarning(APP_TITLE, "請先選擇下載資料夾。")
            return

        job = Job(repo_url=url, owner=owner, repo=repo, dest_folder=dest)
        card = self._add_card(job)
        self.persist()
        self.url_var.set("")
        card.refresh()  # immediately fetch latest release info

    def _add_card(self, job: Job) -> "JobCard":
        card = JobCard(self.list_frame, app=self, job=job)
        card.pack(fill=tk.X, pady=6, padx=2)
        self.cards.append(card)
        return card

    def remove_card(self, card: "JobCard") -> None:
        if card in self.cards:
            self.cards.remove(card)
        card.destroy()
        self.persist()

    def persist(self) -> None:
        save_jobs([c.job for c in self.cards])

    def token(self) -> Optional[str]:
        return self.token_var.get().strip() or None

    def _save_token(self) -> None:
        self._settings["token"] = self.token_var.get().strip()
        save_settings(self._settings)
        messagebox.showinfo(APP_TITLE, "已儲存 Token，下次開啟會自動帶入，所有工作都會使用它。")

    # ------------------------------------------------------------ threading
    def submit(self, fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def post(self, fn: Callable[[], None]) -> None:
        """Queue a callable to run on the Tk main thread."""
        self.ui_queue.put(fn)

    def _drain_queue(self) -> None:
        try:
            while True:
                self.ui_queue.get_nowait()()
        except queue.Empty:
            pass
        except Exception:
            pass
        self.root.after(100, self._drain_queue)


class JobCard(ttk.LabelFrame):
    """A single tracked repo: release info, folder picker, refresh/download."""

    def __init__(self, master, app: App, job: Job) -> None:
        super().__init__(master, text=job.full_name, padding=10)
        self.app = app
        self.job = job
        self._busy = False
        self._release: Optional[dict] = None
        self._build()

    def _build(self) -> None:
        self.release_var = tk.StringVar(value=self._release_text())
        ttk.Label(self, textvariable=self.release_var, foreground="#555",
                  wraplength=700, justify="left").grid(
            row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

        ttk.Label(self, text="資料夾：").grid(row=1, column=0, sticky="w")
        self.dest_var = tk.StringVar(value=self.job.dest_folder)
        self.dest_var.trace_add("write", self._on_dest_change)
        ttk.Entry(self, textvariable=self.dest_var).grid(
            row=1, column=1, columnspan=2, sticky="we", padx=4)
        ttk.Button(self, text="瀏覽…", command=self._browse).grid(row=1, column=3, sticky="we")

        btns = ttk.Frame(self)
        btns.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 4))
        self.refresh_btn = ttk.Button(btns, text="重新整理", command=self.refresh)
        self.refresh_btn.pack(side=tk.LEFT)
        self.download_btn = ttk.Button(btns, text="下載", command=self._on_download)
        self.download_btn.pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text="移除", command=self._on_remove).pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.grid(row=3, column=0, columnspan=4, sticky="we", pady=(4, 2))

        self.status_var = tk.StringVar(value=self.job.status or "")
        ttk.Label(self, textvariable=self.status_var, foreground="#357",
                  wraplength=700, justify="left").grid(
            row=4, column=0, columnspan=4, sticky="w")

        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

    def _release_text(self) -> str:
        if self.job.latest_tag:
            parts = [f"最新 release：{self.job.latest_tag}"]
            if self.job.release_name and self.job.release_name != self.job.latest_tag:
                parts.append(self.job.release_name)
            if self.job.published_at:
                parts.append(self.job.published_at[:10])
            line = "　|　".join(parts)
            if self.job.commit_message:
                line += f"\nCommit：{self.job.commit_message}"
            return line
        return "尚未取得 release 資訊，請按「重新整理」或直接按「下載」。"

    def _on_dest_change(self, *_) -> None:
        self.job.dest_folder = self.dest_var.get()
        self.app.persist()

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest_var.get() or None)
        if folder:
            self.dest_var.set(folder)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.refresh_btn.config(state=state)
        self.download_btn.config(state=state)

    def _status(self, text: str) -> None:
        self.status_var.set(text)
        self.job.status = text

    def _apply_release(self, release: dict, commit_message: Optional[str] = None) -> None:
        self._release = release
        self.job.latest_tag = release.get("tag_name", "")
        self.job.release_name = release.get("name") or ""
        self.job.published_at = release.get("published_at") or ""
        if commit_message is not None:
            self.job.commit_message = commit_message
        self.release_var.set(self._release_text())

    # ----------------------------------------------------------- refresh
    def refresh(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self._status("重新整理中…")
        token, owner, repo = self.app.token(), self.job.owner, self.job.repo

        def work() -> None:
            try:
                release = get_latest_release(owner, repo, token=token)
                commit_msg = get_tag_commit_message(
                    owner, repo, release.get("tag_name", ""), token=token)
            except Exception as exc:
                msg = str(exc)
                self.app.post(lambda: self._refresh_done(None, None, msg))
                return
            self.app.post(lambda: self._refresh_done(release, commit_msg, None))

        self.app.submit(work)

    def _refresh_done(self, release: Optional[dict], commit_msg: Optional[str],
                      error: Optional[str]) -> None:
        self._set_busy(False)
        if error:
            self._status(f"錯誤：{error}")
        else:
            assert release is not None
            self._apply_release(release, commit_msg)
            self._status("已更新 release 資訊 ✓")
        self.app.persist()

    # ---------------------------------------------------------- download
    def _on_download(self) -> None:
        if self._busy:
            return
        dest = self.dest_var.get().strip()
        if not dest:
            messagebox.showwarning(APP_TITLE, "請先選擇下載資料夾。")
            return
        self._set_busy(True)
        self.progress["value"] = 0
        self._status("取得最新 release 中…")
        token, owner, repo = self.app.token(), self.job.owner, self.job.repo

        def on_progress(p: int) -> None:
            self.app.post(lambda: self.progress.config(value=p))

        def on_log(m: str) -> None:
            self.app.post(lambda: self._status(m))

        def work() -> None:
            try:
                # Always re-fetch the latest release so the download reflects
                # the newest tag without needing a separate "重新整理" click.
                release = get_latest_release(owner, repo, token=token)
                commit_msg = get_tag_commit_message(
                    owner, repo, release.get("tag_name", ""), token=token)
                self.app.post(lambda: self._apply_release(release, commit_msg))
                run_job_download(release, dest, token=token,
                                 progress_cb=on_progress, log_cb=on_log)
            except Exception as exc:
                msg = str(exc)
                self.app.post(lambda: self._download_done(msg))
                return
            self.app.post(lambda: self._download_done(None))

        self.app.submit(work)

    def _download_done(self, error: Optional[str]) -> None:
        self._set_busy(False)
        if error:
            self._status(f"下載失敗：{error}")
        else:
            self.progress["value"] = 100
        self.app.persist()

    def _on_remove(self) -> None:
        if self._busy and not messagebox.askyesno(APP_TITLE, "工作進行中，確定要移除嗎？"):
            return
        self.app.remove_card(self)


def _write_crash_log(text: str) -> None:
    """Write startup crash info to Desktop so the user can find it."""
    import traceback
    import pathlib
    desktop = pathlib.Path.home() / "Desktop"
    if not desktop.exists():
        desktop = pathlib.Path.home()
    log = desktop / "GitHubReleaseDownloader_crash.log"
    try:
        log.write_text(text, encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    try:
        # Use the OS certificate store so HTTPS works in frozen builds even
        # if certifi's CA bundle is missing or stale.
        try:
            import truststore
            truststore.inject_into_ssl()
        except Exception:
            pass
        root = tk.Tk()
        try:
            style = ttk.Style()
            for theme in ("vista", "clam"):
                if theme in style.theme_names():
                    style.theme_use(theme)
                    break
        except tk.TclError:
            pass
        App(root)
        root.mainloop()
    except Exception:
        import traceback
        detail = traceback.format_exc()
        _write_crash_log(detail)
        try:
            import tkinter.messagebox as mb
            mb.showerror(
                "GitHubReleaseDownloader — 啟動失敗",
                f"程式啟動時發生錯誤，詳細記錄已寫到桌面：\n"
                f"GitHubReleaseDownloader_crash.log\n\n{detail[:600]}",
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
