<div align="center">

<img src="frontend/public/avatar.webp" alt="MoeGallery" width="120" />

# **MoeGallery**

[![Release](https://img.shields.io/github/v/release/violetaini/MoeGallery?style=for-the-badge)](https://github.com/violetaini/MoeGallery/releases/latest)
[![Frontend](https://img.shields.io/badge/Frontend-Vue%203%20%2B%20Vite-42b883?style=for-the-badge)](frontend/package.json)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20SQLAlchemy-009688?style=for-the-badge)](backend/requirements.txt)
[![Database](https://img.shields.io/badge/Database-MySQL%20%2F%20SQLite-2563eb?style=for-the-badge)](.env.example)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)

</div>

<p align="center">
  <a href="README.md">English</a> |
  <a href="README_zh.md">简体中文</a> |
  <a href="README_zh-TW.md">繁體中文</a> |
  <a href="README_ja.md">日本語</a>
</p>

<p align="center">
  <a href="https://anime.chitanda.net/">線上站點</a> |
  <a href="https://anime.chitanda.net/api-docs">API 文件</a> |
  <a href="https://github.com/violetaini/MoeGallery/releases">Release</a>
</p>

MoeGallery 是一個自託管的二次元圖片媒體庫，包含訪客畫廊與管理後台，可維護圖片、作品、角色、分級、元資料、圖片處理任務與 API。

## 快速安裝

建議安裝器適用於使用 systemd 的 Linux，並直接安裝已建置的 Release。部署時不需要 Node.js。

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
sudo bash install.sh
```

安裝程式只詢問監聽方式：

- `127.0.0.1`：僅本機存取或自行設定反向代理，建議使用。
- `0.0.0.0`：直接透過公網或區域網路存取。

預設連接埠為 `8111`。服務啟動後開啟：

```text
http://伺服器IP:8111/install
```

網頁安裝器會完成資料庫選擇、管理員帳號、資料庫遷移、登入密鑰、API Key、儲存目錄與安裝鎖初始化。

| 資料庫 | 操作 |
| --- | --- |
| SQLite | 選擇 SQLite 後繼續，資料庫檔案位置由 MoeGallery 決定。 |
| MySQL / MariaDB | 先建立空資料庫及專用帳號，再填入連線資訊。 |

無人值守並直接監聽公網：

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

MoeGallery 不建立網域、TLS 憑證、防火牆規則或反向代理站點。完整選項與手動部署請參閱[部署說明](docs/deployment.md)。

## 安裝內容

- 預設安裝到 `/opt/moegallery`。
- 只建立一個 `moegallery.service` systemd 服務。
- 建立專用的非 root 使用者 `moegallery`。
- 內建啟動器負責啟動 FastAPI 並協調面板更新。
- 後端在同一連接埠直接提供已建置的前端。

專案不再安裝獨立 updater 服務，也不再寫入 updater sudoers 規則。

## 主要功能

- 可由後台指定圖片的全螢幕首頁幻燈片。
- 瀑布流圖庫，支援搜尋、作品/角色/分級篩選、排序、自動載入與預載。
- 圖片詳情浮層及獨立詳情路由。
- 媒體庫風格的作品頁與角色頁，支援背景、封面、頭像和分頁。
- 固定 `safe`、`sensitive`、`hidden` 三種分級。
- 提供公開隨機圖片 API，可依作品、角色 ID、中文名、日文原名、別名、分級與方向篩選，並可分別設定桌面與手機的預設方向。
- 經典表格與瀑布畫廊兩種後台管理模式，並支援批次操作。
- 批次上傳、重複預檢、處理佇列、失敗重試與元資料綁定。
- CSV、JSON、XLSX、XLSM 批次匯入範本。
- SQLite 與 MySQL/MariaDB 部署選擇。
- HttpOnly 管理員工作階段、CSRF 驗證、登入限流、API Key 與自動產生的強密鑰。
- 面板 Release 檢查、更新包校驗、資料庫備份、遷移、健康檢查及失敗自動復原。

## 圖片管線

| 來源 | 原圖入庫 | 瀏覽器預覽 |
| --- | --- | --- |
| 一般靜態圖片 | 轉為 WebP | WebP 預覽圖與縮圖 |
| GIF / 動圖 | 保留動畫格式 | 靜態 WebP 預覽圖與縮圖 |
| JXR / HDR | 轉為帶有 `nclx / mdcv / clli` 的 HDR AVIF | SDR WebP 預覽圖與縮圖 |
| 其他高位元深度圖片 | 保留相容的 HDR 原圖 | SDR WebP 預覽圖與縮圖 |

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

後端會同時驗證副檔名與實際解碼能力，偽裝或無法解碼的檔案會被拒絕。

## 更新與備份

安裝完成後透過**後台 > 更新中心**更新。內建啟動器會先在線下載並校驗 Release，安裝與遷移時短暫停止 Web 子行程，重新啟動後執行健康檢查；失敗時會復原更新前的程式與資料庫備份。

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_before_upgrade.sh \
  --app-dir /opt/moegallery
```

SQLite 使用 SQLite backup API；MySQL/MariaDB 使用 `mysqldump --single-transaction`。

## 文件

- [Deployment guide](docs/deployment.md)
- [部署說明（簡體中文）](docs/deployment_zh.md)
- [API 維運指南](docs/api/operations-guide.md)
- 管理員登入後的互動式 API 文件：`/api-docs`

## 本機開發

需要 Python 3.11 或更新版本，以及 Node.js 20 或更新版本。

```bash
python -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

cd frontend
npm ci
npm run dev
```

## 安全

- 不要將 `.env`、`installed.lock`、資料庫、上傳圖片、備份或私鑰提交到 Git。
- 透過不受信任的網路開放管理員登入前，請自行設定 HTTPS。
- MySQL 應使用專用帳號，不要使用資料庫管理員帳號。
- 保持 Release SHA256 校驗，只設定可信任的 GitHub 代理。

## 授權

MoeGallery 使用 [MIT License](LICENSE)。
