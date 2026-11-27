# GitHub Release Downloader

一個 Windows 桌面 GUI 小工具，用來**追蹤多個 GitHub repo 的最新 Release，並一鍵下載 release 內的檔案**。
專為「我手上這版是不是最新的？」這個問題設計——打開程式就能一眼掃完所有追蹤的專案。

目前版本：**v1.1.1**

---

## 畫面與資訊呈現

每個追蹤的 repo 是一張卡片，由上到下的資訊密度依重要性排列：

```
┌─ cbolong/ic-monitor ─────────────────────────────────────────┐
│ build-2026-11-26-0308-8a3d822   IC Monitor (8a3d822) · 11-26 │ ← 粗體 tag + 次要資訊
│ Commit：§239 請假統計:今天有人請假時，請圖下面多一條深綠短線     │ ← release tag 對應的 commit 標題
│ ✔ 已下載最新版（build-2026-11-26-0308-8a3d822，11-26 11:21）  │ ← 狀態徽章（三色）
│ 資料夾： D:/tools                                 [瀏覽…]     │
│ [重新整理] [下載] [開啟資料夾] [移除]                          │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                                        │ ← 整體進度（非單檔）
│ 18:00 下載完成 ✓（build-2026-11-26-0308-8a3d822）             │ ← 帶時間戳的狀態
└──────────────────────────────────────────────────────────────┘
```

### 狀態徽章（核心功能）

這是回答「我需不需要更新」的那一行，程式會記住你**實際下載過**的版本：

| 顯示 | 意義 |
|---|---|
| 🔔 **橘色**「有新版可下載！（目前已下載：`<舊版>`）」 | GitHub 上的 tag 比你手上的新 |
| ✔ **綠色**「已下載最新版（`<版本>`，`<時間>`）」 | 手上就是最新的 |
| **灰色**「尚未下載過」 | 這個 repo 還沒下載過任何版本 |

---

## 功能

### 追蹤與更新
- 輸入 repo 連結按「**＋ 加入**」建立追蹤工作（job）
- 「**重新整理**」重抓該 repo 的 latest release
- 「**🔄 全部重新整理**」一鍵更新所有 repo（彼此錯開 200ms，避免連線突波）
- job 清單自動保存，下次開啟自動還原
- 狀態訊息附時間戳（`14:32 已更新 ✓`），知道資訊多新

### 下載規則（exe 優先）
「**下載**」會**先自動抓取最新 release**再下載，不必先按重新整理。選檔規則：

| release 內容 | 下載行為 |
|---|---|
| 有 `.exe` | **只下載 `.exe`**（多個則全部下載），直接放入資料夾 |
| 沒有 exe、有 `.zip` | 下載 `.zip` 並**自動解壓**到資料夾 |
| 兩者都沒有 | 下載其餘檔案 |
| GitHub 自動產生的 **Source code (zip/tar.gz)** | **一律不下載** |

其他下載行為：
- 下載 `.exe` 前會**自動關閉正在執行的同名程式**，避免 Windows「檔案使用中」無法覆蓋
- 多檔下載時進度條顯示**整體進度**，不會每個檔案歸零重來
- zip 解壓有 **zip-slip 路徑穿越防護**
- 「**開啟資料夾**」直接跳到下載目的地

### 網路韌性
- 失敗時自動重試，視窗約 **14 秒**（4 次，退避 0s/2s/4s/8s + 抖動）
- 錯誤訊息是可讀的中文說明，不是原始例外堆疊，例如：
  ```
  與 GitHub 的連線被中途切斷。
  已自動重試 4 次仍失敗，這通常是暫時性的。
  常見原因：防毒／防火牆的 HTTPS 掃描、VPN、公司網路或連線不穩。
  請稍後再按一次；若持續發生，可嘗試關閉防毒的 HTTPS/SSL 掃描。
  ```

### GitHub Token（選填）
- 填入後按「**儲存**」會存到 `settings.json`，下次開啟自動帶入，所有 job 共用
- 用途：存取 **private repo**、提高 API 速率限制（未授權每小時僅 60 次）
- Classic token 需要 `repo` scope；fine-grained token 需開啟對應 repo 的 Contents 讀取權限
- 也可用環境變數 `GITHUB_TOKEN`（UI 欄位優先）

---

## 取得執行檔（.exe）

推送到 `main` 會由 GitHub Actions 在 Windows runner 上自動編譯：

1. 進 repo 的 **Actions** 分頁 → 最新一筆 **Build Windows EXE**
2. 頁面下方 **Artifacts** 下載 `GitHubReleaseDownloader`
3. 解壓後直接執行 `GitHubReleaseDownloader.exe`（免安裝）

也會自動發佈到 [Releases](../../releases)，tag 取自 `VERSION` 檔內容。
**Releases 只保留最新 3 份**，更舊的會自動刪除（連同 tag）。

---

## 使用方式

1. 開啟 `GitHubReleaseDownloader.exe`
2. （若要追蹤 private repo）在「GitHub Token」填入權杖並按「**儲存**」
3. 「GitHub Repo 連結」輸入例如 `https://github.com/cbolong/ic-monitor`
4. 選好「下載資料夾」後按「**＋ 加入**」（加入後會自動抓一次 release 資訊）
5. 之後直接按「**下載**」即可——它會自動抓最新版再下載

支援的連結格式：`https://github.com/owner/repo`、結尾 `/`、`.git`、`git@github.com:owner/repo.git`、`owner/repo`、含子路徑的 URL。

---

## 設定與資料存放

| 檔案 | 內容 |
|---|---|
| `%APPDATA%\GitHubReleaseDownloader\jobs.json` | 追蹤清單（含已下載版本與時間） |
| `%APPDATA%\GitHubReleaseDownloader\settings.json` | GitHub Token |

非 Windows 環境退回 `~/.github_release_downloader/`。
兩個檔案都採**原子寫入**（寫 `.tmp` 再 `os.replace`），且讀取時容忍檔案損毀或缺欄位（會回到預設值，不會崩潰）。

---

## 程式架構

```
app.py          GUI（Tkinter）：視窗、卡片、執行緒調度
  ├── github_api.py    GitHub REST API：URL 解析、抓 release / commit 標題
  ├── downloader.py    選檔、串流下載、解壓、關閉執行中程式
  ├── store.py         Job 資料模型、JSON 持久化、版本狀態判斷
  └── http_client.py   共用 HTTP 層：逾時、headers、Session、重試、錯誤訊息
```

**分層原則**：`app.py` 只處理 UI 與執行緒；所有網路行為集中在 `http_client.py`，
所有 GitHub 語意集中在 `github_api.py`，所有檔案處理集中在 `downloader.py`。
任何網路設定（逾時、重試、token 注入、錯誤措辭）**只在 `http_client.py` 改一處**。

### 執行緒模型
網路與下載都在背景 daemon thread 執行，UI 永遠不會卡住。
背景結果透過 `queue.Queue` 送回主執行緒（`App.post()`），由 `_drain_queue()` 每 100ms 取出執行——
Tkinter 非執行緒安全，所有 widget 操作都必須回到主執行緒。
每個執行緒有自己的 `requests.Session`（`requests.Session` 官方載明非執行緒安全）。

---

## 開發

需要 Python 3.11+。

```bash
pip install -r requirements.txt
python app.py
```

> GUI 使用內建 Tkinter。Linux 若提示找不到模組，請安裝系統套件（Debian/Ubuntu：`python3-tk`）。

### 跑測試

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

目前 **85 個測試**，全部不需要網路與顯示器，任何平台都能跑：

| 測試檔 | 涵蓋 |
|---|---|
| `test_logic.py` | URL 解析、exe 優先選檔 |
| `test_downloader.py` | 選檔邊界、整體進度、zip-slip 防護、關閉程式、下載流程 |
| `test_github_api.py` | HTTP 錯誤映射（404/401/403/500）、commit 標題、共用進入點 |
| `test_store.py` | 持久化 round-trip、壞檔容錯、舊版相容、版本徽章狀態 |
| `test_http_client.py` | token 解析、header 組裝、執行緒區域 Session、重試預算、錯誤措辭 |

### 本機編譯 .exe（Windows）

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed ^
  --hidden-import tkinter --hidden-import tkinter.ttk ^
  --hidden-import tkinter.filedialog --hidden-import tkinter.messagebox ^
  --collect-all tkinter --collect-all certifi ^
  --collect-submodules truststore --hidden-import truststore ^
  --hidden-import psutil --collect-submodules psutil ^
  --name GitHubReleaseDownloader app.py
# 產物：dist/GitHubReleaseDownloader.exe
```

> 這些 `--hidden-import` / `--collect-*` 旗標**不可省略**：
> 少了 tkinter 相關旗標，打包出的 exe 會「閃一下就關」；
> 少了 certifi/truststore，HTTPS 會失敗。

### 發佈新版

把 `VERSION` 檔改成新版號（例如 `v1.1.2`）推上 `main`，CI 就會自動編譯並建立該 tag 的 Release。

---

## 相依套件

| 套件 | 用途 |
|---|---|
| `requests` | HTTP |
| `truststore` | 用 OS 憑證庫做 TLS 驗證（讓打包後的 exe 不依賴 certifi 是否完整） |
| `psutil` | 找出並關閉正在執行的同名 exe |

Tkinter 為 Python 內建，不需安裝。

---

## License

[MIT](LICENSE)
