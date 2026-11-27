# 交接文件 — GitHub Release Downloader

> 給下一位接手的開發者（或下一個 AI session）。
> **先讀這份，再動程式。** 這裡記錄的是「為什麼這樣做」，README 記錄的是「它會做什麼」。
> 本文件最後更新：v1.1.1

---

## 1. 現況快照

| 項目 | 狀態 |
|---|---|
| 版本 | `v1.1.1`（版號來源：repo 根目錄的 `VERSION` 檔） |
| 分支 | 開發與發佈都在 **`main`**（本專案目前不走 PR 流程） |
| 程式碼 | 5 個模組，約 1,100 行 |
| 測試 | **85 個，全部通過**，不需網路與顯示器 |
| CI | GitHub Actions，推 `main` 即編譯 Windows exe 並發佈 Release |
| 平台 | 使用者端是 **Windows**；開發/CI 測試在 Linux 也能跑 |

```bash
# 接手後第一件事：確認基準線是綠的
python -m unittest discover -s tests -p "test_*.py" -v   # 應該 85 passed
```

---

## 2. 這個軟體解決什麼問題

使用者（repo 擁有者本人）手上有多個自己的專案，每個專案都會用 CI 發佈 Windows exe 到 GitHub Releases。
他需要一個常駐的小工具：**打開就知道哪些專案有新版、按一下就把最新 exe 抓到指定資料夾**。

所以兩個設計重心是：
1. **一目瞭然** — 不用點進去就知道「我手上這版是不是最新」
2. **一鍵完成** — 按「下載」就該拿到最新版，不該要求先按「重新整理」

---

## 3. 模組與資料流

```
app.py (GUI / 執行緒)
  │
  │  使用者按「重新整理」或「下載」
  ▼
背景 daemon thread
  │
  ├─► github_api.fetch_release_info(owner, repo, token)   ← 兩條路徑共用的唯一進入點
  │     ├─ get_latest_release()      GET /repos/{o}/{r}/releases/latest
  │     └─ get_tag_commit_message()  GET /repos/{o}/{r}/commits/{tag}
  │
  └─► downloader.run_job_download(release, dest, ...)
        ├─ select_assets()          exe 優先規則
        ├─ terminate_if_running()   關閉執行中的同名 exe（psutil）
        ├─ download_asset()         串流下載 + 進度
        └─ extract_zip()            安全解壓（防 zip-slip）
  │
  ▼  結果透過 App.post() 丟進 queue.Queue
主執行緒 _drain_queue()（每 100ms）→ 更新 widget
```

所有 HTTP 都經過 `http_client.py`：逾時、headers、token 注入、Session、重試、錯誤措辭**只在那裡改**。

### 各模組職責

| 模組 | 職責 | 不該放什麼 |
|---|---|---|
| `app.py` | Tkinter UI、執行緒調度、狀態顯示 | 網路細節、檔案格式判斷 |
| `github_api.py` | GitHub REST 語意、錯誤映射 | UI 文字排版、下載行為 |
| `downloader.py` | 選檔、下載、解壓、關程式 | GitHub API 呼叫 |
| `store.py` | `Job` 模型、JSON 持久化、版本狀態判斷（純函式） | 任何 I/O 以外的業務邏輯 |
| `http_client.py` | 逾時/headers/Session/重試/錯誤措辭 | 任何 GitHub 專屬語意 |

---

## 4. ⚠️ 刻意的設計 — 不要當成 bug 改掉

這一節最重要。以下每一項都是**經過討論後刻意決定**的，而且多半是修過真實 bug 的結果。
如果你覺得某項「看起來很怪」，請先讀它的理由。

### 4.1 按「下載」時一定會重新抓 release（不使用快取）
`JobCard._on_download()` 的 worker 一開始就呼叫 `fetch_release_info()`。
**理由**：使用者明確要求「按下載就該拿到最新版，不要逼我先按重新整理」。
曾經有過 `self._release` 快取，v1.0.3 已移除——**不要再加回來**。

### 4.2 exe 優先，而不是「全部下載」
`downloader.select_assets()` 的順序是 `.exe` → `.zip` → 其他，**只回傳命中的那一層**。
**理由**：使用者的 release 常同時放 `foo.exe` 和 `foo-portable.zip`，他只要 exe。
早期版本下載全部，被回報為 bug（v1.0.5 修正）。
多個 `.exe`（如 x64/x86）則**全部下載**，這也是使用者確認過的。

### 4.3 GitHub 自動產生的 Source code 壓縮檔絕不下載
GitHub API 的 `assets[]` 本來就不含這些（它們在 `zipball_url`/`tarball_url`），
`is_source_archive()` 是**第二道防線**。使用者特別強調過不要下載到 source code，保留它。

### 4.4 下載 exe 前會殺掉同名的執行中程序
`terminate_if_running()` 用 psutil 比對**完整絕對路徑**（不是程序名稱）。
**理由**：Windows 不允許覆蓋執行中的 exe，不先關掉就會下載失敗。
注意幾個刻意的細節：
- 只比對完整路徑 → 避免誤殺其他同名程式
- `AccessDenied` 靜默略過 → 需要管理員權限的程序殺不掉，但下載仍繼續（錯誤訊息會說明）
- 只對 `.exe` 做，zip 不做
- 整個函式是 best-effort，**永遠不拋例外**，不能擋住下載

### 4.5 進度條是「整體進度」，而且單調遞增
`_make_overall_progress(file_index, total_files, cb)` 把每個檔案的 0–100 映射到
`[i/N, (i+1)/N]` 這個區間。
**理由**：早期多檔下載時每個檔案都讓進度條歸零重跑，使用者以為當掉了（v1.0.6 修正）。
`tests/test_downloader.py::test_progress_is_monotonic_and_ends_at_100` 鎖住這個行為，**不要讓它失敗**。

### 4.6 404 要做兩段診斷
`get_latest_release()` 收到 404 時會再打一次 `/repos/{owner}/{repo}` 來區分：
- repo 存在但沒有 release → 「目前沒有任何 GitHub Release」
- repo 不存在或 token 無權限 → 「找不到…或 Token 無權存取」

**理由**：GitHub 對 private repo 未授權時也回 404（而非 403），使用者曾因此困惑很久。
這會多花一次 API 額度，但**只在 404 時觸發**，值得。

### 4.7 重試視窗必須夠長（約 14 秒）
`http_client.RETRY_TOTAL = 4`、`RETRY_BACKOFF = 1.0`、`RETRY_JITTER = 0.3`。
**理由**（v1.1.1 修的真實 bug，有實驗佐證）：
- urllib3 **不把 SSLError 歸類為 connect 或 read 錯誤**，所以只有 `total` 生效
  （舊版寫的 `connect=3, read=3` 完全沒作用，已移除——不要加回去）
- 舊設定 `total=3, backoff=0.5` 只有約 3 秒視窗
- 防毒的 HTTPS 掃描、VPN、公司網路造成的瞬斷常超過 3 秒
  → 使用者頻繁看到 `SSLEOFError(UNEXPECTED_EOF_WHILE_READING)`，但網路其實是好的

`tests/test_http_client.py::test_retry_budget_rides_out_a_multi_second_outage`
會驗證重試視窗 > 10 秒。**調低 `RETRY_TOTAL` 會讓這個測試失敗，那是故意的。**

### 4.8 每個執行緒有自己的 Session
`get_session()` 用 `threading.local()`。
**理由**：
- `requests.Session` 官方載明非執行緒安全，而「全部重新整理」會同時跑多個請求
- 背景 thread 是短命的（一次操作一條），所以也順便避免閒置連線變成死連線
- 單一操作內（抓 release + 抓 commit + 下載多檔）仍共用同一個 Session，pooling 的好處還在

### 4.9 錯誤訊息一律走 `friendly_error()`
refresh 和 download 兩條路徑都呼叫同一個 `http_client.friendly_error()`。
**理由**：同一個網路問題不該出現兩種講法。而且使用者看不懂
`HTTPSConnectionPool(...Max retries exceeded...SSLEOFError...)` 這種原始堆疊。
注意：`SSLError` 和 `ConnectionError`（Connection aborted / reset）**被刻意映射到同一段文字**，
因為對使用者而言是同一個問題、同一個解法。

### 4.10 「全部重新整理」錯開 200ms
`App.refresh_all()` 用 `root.after(index * REFRESH_ALL_STAGGER_MS, card.refresh)`。
**理由**：同一瞬間開 N 條 TLS 連線正是觸發防毒/防火牆攔截與 GitHub abuse detection 的行為。

### 4.11 Releases 只保留 3 份
CI 最後一步會刪掉第 4 份以後的 release 與其 tag。**使用者明確要求的**。

### 4.12 PyInstaller 的那堆旗標不能省
```
--collect-all tkinter      少了 → exe「閃一下就關」
--collect-all certifi      少了 → HTTPS 驗證失敗
--collect-submodules truststore / psutil   少了 → 對應功能靜默失效
```
這些都是踩過的坑，`.github/workflows/build-windows.yml` 裡的那一長串請原樣保留。

### 4.13 版號由 `VERSION` 檔驅動
CI 讀 `VERSION` 的內容當 release tag。**改版就是改這個檔**，不要去手動建 tag。

---

## 5. 曾經提出但被否決的點子

接手時如果想到這些，先知道為什麼沒做：

| 點子 | 否決理由 |
|---|---|
| 程式啟動時自動全部重新整理 | 沒設 token 的使用者每小時只有 60 次 API 額度，會被燒光 |
| 已是最新版就把「下載」按鈕停用 | 會擋掉「檔案壞了想重抓」的正當需求，也違反 4.1 |
| 資料夾輸入框做 debounce 再存檔 | 會引入「關程式前最後幾百毫秒的輸入遺失」的風險，收益趨近於零 |
| 下載時省略抓 commit 標題以加速 | 相對下載時間無感，且會讓 refresh/download 兩條路徑行為分歧（違反 4.9 的共用原則） |
| 在 SSL 失敗時額外清空連線池重試 | 實驗證明 urllib3 的重試本來就會換新連線，是多餘的機制 |

---

## 6. 已知限制與地雷

- **開發環境沒有 tkinter**：Linux 容器通常沒裝 `python3-tk`，所以 `import app` 會失敗。
  測試用 stub 替身繞過（見第 7 節的煙霧測試），不要為此去改 `app.py` 的 import 結構。
- **`app.py` 沒有單元測試**：UI 層靠「stub tkinter 煙霧測試 + 整合模擬」驗證。
  若要動 `app.py`，務必跑第 7 節的完整驗證。
- **Session 靠 GC 回收**：thread-local session 不會顯式 close，隨執行緒結束被回收。
  對桌面應用的請求量而言沒問題，不需要加複雜的生命週期管理。
- **`version_state()` 用字串相等比較版本**，不做語意化版本排序。
  使用者的 tag 格式是 `build-2026-11-26-0308-8a3d822` 這類時間戳，
  「不等於 latest 就是有新版」已經足夠且正確。
- **Windows 專用行為**：`os.startfile`（開資料夾）、殺 exe、`%APPDATA%` 路徑，
  在 Linux/macOS 都有 fallback 但沒有實機驗證過。

---

## 7. 修改後的完整驗證流程

任何改動都請跑完這 5 關，**全綠才算完成**：

```bash
cd /path/to/github_downloader

# 1) 全部編譯
python -m py_compile http_client.py app.py github_api.py downloader.py store.py tests/*.py

# 2) 完整測試套件（應為 85 passed）
python -m unittest discover -s tests -p "test_*.py" -v
```

**3) 對外簽章未變**（`app.py` 依賴這些，簽章一變就是破壞性改動）
```python
github_api.get_latest_release(owner, repo, token=None) -> dict
github_api.fetch_release_info(owner, repo, token=None) -> Tuple[dict, str]
github_api.parse_repo_url(url) -> Tuple[str, str]
downloader.run_job_download(release, dest_dir, token=None, progress_cb=None, log_cb=None) -> None
downloader.select_assets(release) -> List[dict]
http_client.get_session() -> requests.Session
http_client.friendly_error(exc) -> str
store.version_state(latest_tag, downloaded_tag) -> str
```

**4) `app.py` 煙霧測試**（用 stub 取代 tkinter，可抓到命名/匯入錯誤）
```python
import sys, types
class _W:
    def __init__(self,*a,**k): pass
    def __getattr__(self,n): return lambda *a,**k: None
def M(name,**kw):
    m=types.ModuleType(name); [setattr(m,k,v) for k,v in kw.items()]; sys.modules[name]=m; return m
tk=M("tkinter",Tk=_W,Canvas=_W,StringVar=_W,Frame=_W,TclError=Exception,
     TOP="t",X="x",BOTH="b",LEFT="l",RIGHT="r",Y="y",END="e")
M("tkinter.font",nametofont=lambda n:_W())
M("tkinter.filedialog",askdirectory=lambda **k:"")
M("tkinter.messagebox",showerror=lambda *a,**k:None,showwarning=lambda *a,**k:None,
  showinfo=lambda *a,**k:None,askyesno=lambda *a,**k:True)
ttk=M("tkinter.ttk",Frame=_W,Label=_W,Entry=_W,Button=_W,LabelFrame=_W,
      Progressbar=_W,Scrollbar=_W,Style=_W)
tk.font=sys.modules["tkinter.font"]; tk.filedialog=sys.modules["tkinter.filedialog"]
tk.messagebox=sys.modules["tkinter.messagebox"]; tk.ttk=ttk
import app; print("app.py OK")
```

**5) 回歸檢查**（確認第 4 節的刻意設計都還在）
- exe 優先：`select_assets({"assets":[{"name":"a.zip"},{"name":"a.exe"}]})` → 只回 `a.exe`
- source 排除：`is_source_archive("Source code (zip)")` → `True`
- 進度單調遞增且結束於 100
- 徽章三態：`version_state("v2","")`→`never_downloaded`、`("v2","v1")`→`update_available`、`("v2","v2")`→`up_to_date`
- 404 兩段診斷的兩種訊息
- 舊 `jobs.json`（缺新欄位）仍能載入，缺的欄位補預設值

---

## 8. 常見維護任務怎麼做

| 任務 | 做法 |
|---|---|
| 發新版 | 改 `VERSION` 的內容 → 推 `main` → CI 自動編譯並發 Release |
| 調整逾時／重試 | 只改 `http_client.py` 頂部常數（`TIMEOUT_*`、`RETRY_*`），注意 4.7 的測試下限 |
| 改錯誤措辭 | 只改 `http_client.friendly_error()`，兩條路徑自動同步 |
| 加 Job 欄位 | 在 `store.Job` 加帶預設值的欄位即可；`load_jobs()` 會自動忽略未知欄位、補上缺欄位 |
| 改卡片顯示 | 只改 `JobCard._refresh_display()`，它是所有顯示字串的唯一來源 |
| 加新按鈕 | 在 `JobCard._build()` 的 `btns` frame 加；長時間操作記得走 `app.submit()` + `app.post()` |

---

## 9. 版本演進史（踩過的坑）

| 版本 | 內容 |
|---|---|
| v1.0.0 | 初版：Tkinter GUI + CI 編譯 exe |
| v1.0.1 | 修「exe 閃一下就關」（tkinter 未完整打包）、HTTPS 失敗（改用 truststore）、Token 儲存 |
| v1.0.2 | 404 兩段診斷（區分「沒有 release」與「無權限」） |
| v1.0.3 | 顯示 commit 標題；下載改為永遠重抓最新（移除快取） |
| v1.0.4 | 下載 exe 前自動關閉執行中的同名程式（psutil） |
| v1.0.5 | **exe 優先**選檔（原本會把 exe 和 zip 都下載） |
| v1.0.6 | 共用 `http_client`；修進度條倒退；測試 15 → 70 |
| v1.1.0 | UI 大改：已下載版本徽章、全部重新整理、開啟資料夾、時間戳；`fetch_release_info()` 共用進入點 |
| v1.1.1 | **修 SSL `UNEXPECTED_EOF` 間歇失敗**：重試視窗 3s → 14s、thread-local Session、`friendly_error()`、refresh-all 錯開 |

---

## 10. 給下一個 AI session 的提醒

- 使用者是**軟體設計師兼重度使用者**，會仔細看畫面與訊息，也在意架構與可維護性。
- 他要求：**可以共用的程式儘量共用**，避免「改了一個地方忘了改另一個」。
  新增任何跨模組行為前，先看 `http_client.py` 有沒有該放的位置。
- 他要求：**改動必須是必要的**，不要把既有設計當 bug 改掉（第 4 節就是為此而寫）。
- 他要求：**改完要跑完整驗證，不能改壞功能**（第 7 節的 5 關）。
- 回報時請說清楚「為什麼改」與「驗證了什麼」，不要只說「做好了」。
