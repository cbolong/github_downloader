# GitHub Release Downloader

一個 Windows 桌面 GUI 小工具，用來**追蹤多個 GitHub repo 的最新 Release，並一鍵下載 release 內的檔案**。

- 輸入 repo 連結後按「＋ 加入」，即建立一筆追蹤工作（job）
- 每筆 job 顯示最新 release 的 **tag、標題、發佈日期**
- 可隨時為每筆 job 重新選擇下載資料夾
- 「重新整理」會重新抓取該 repo 最新的 release（以 latest tag 為主）
- 「下載」會把 release 內的檔案抓到指定資料夾：
  - `.exe` → 直接放入資料夾
  - `.zip` → 自動解壓到資料夾
  - 自動產生的 **Source code (zip / tar.gz) 不會被下載**
- job 清單會自動保存，下次開啟程式自動還原

## 取得執行檔（.exe）

每次推送都會由 GitHub Actions 在 Windows 上自動編譯 `.exe`：

1. 進到 repo 的 **Actions** 分頁
2. 點選最新一筆 **Build Windows EXE** 工作流程
3. 在頁面下方 **Artifacts** 下載 `GitHubReleaseDownloader`
4. 解壓後即可執行 `GitHubReleaseDownloader.exe`（免安裝）

推送 `v*` 標籤（如 `v1.0.0`）時，`.exe` 也會自動附到對應的 GitHub Release。

## 使用方式

1. 開啟 `GitHubReleaseDownloader.exe`
2. 在「GitHub Repo 連結」輸入例如 `https://github.com/cbolong/github_downloader`
3. 選好「下載資料夾」後按「＋ 加入」
4. 在下方卡片按「重新整理」查看最新 release，按「下載」開始下載
5. 如需 private repo 或避免速率限制，可在「GitHub Token（選填）」填入個人存取權杖

## 本機開發 / 執行

需要 Python 3.11+。

```bash
pip install -r requirements.txt
python app.py
```

> GUI 使用內建的 Tkinter，Linux 上若提示找不到模組，請先安裝系統套件（例如 Debian/Ubuntu 的 `python3-tk`）。

### 跑測試

```bash
python tests/test_logic.py
```

### 本機自行編譯 .exe（在 Windows 上）

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --windowed --name GitHubReleaseDownloader app.py
# 產物在 dist/GitHubReleaseDownloader.exe
```

## 設定與資料

- 追蹤清單存於 `%APPDATA%\GitHubReleaseDownloader\jobs.json`（無 `APPDATA` 時退回 `~/.github_release_downloader/`）
- 可用環境變數 `GITHUB_TOKEN` 提供權杖（UI 的 Token 欄位優先）

## License

[MIT](LICENSE)
