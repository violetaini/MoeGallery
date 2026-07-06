<div align="center">

<img src="frontend/public/avatar.webp" alt="MoeGallery" width="120" />

# **MoeGallery**

[![Version](https://img.shields.io/badge/Version-0.1.0-7c3aed?style=for-the-badge)](frontend/package.json)
[![Frontend](https://img.shields.io/badge/Frontend-Vue%203%20%2B%20Vite-42b883?style=for-the-badge)](frontend/package.json)
[![Backend](https://img.shields.io/badge/Backend-FastAPI%20%2B%20SQLAlchemy-009688?style=for-the-badge)](backend/requirements.txt)
[![Database](https://img.shields.io/badge/Database-MySQL%20%2F%20SQLite-2563eb?style=for-the-badge)](.env.example)
[![HDR](https://img.shields.io/badge/HDR-JXR%20%2B%20AVIF-f97316?style=for-the-badge)](backend/app/utils/image_process.py)
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
  <a href="https://github.com/violetaini/MoeGallery">GitHub</a>
</p>

<p align="center">
  <code>anime-gallery</code>
  <code>image-gallery</code>
  <code>media-library</code>
  <code>vue</code>
  <code>vite</code>
  <code>fastapi</code>
  <code>mysql</code>
  <code>sqlite</code>
  <code>webp</code>
  <code>avif</code>
  <code>hdr</code>
</p>

## 關於

MoeGallery 是一個面向二次元圖片收藏與整理的自託管媒體庫，用於管理插畫、截圖、作品、角色、分級與圖片元資料。它提供面向訪客的前台畫廊，也提供用於上傳、綁定、編輯、匯入和維護的後台面板。

專案定位接近「圖片版本 Jellyfin」：前台負責圖庫瀏覽、作品頁、角色頁、分級、首頁幻燈片和圖片詳情浮層；後台負責上傳、元資料、儲存、重複檢測、圖片轉碼、後台任務、登入鑑權和 API 文件。

## 功能

- 全螢幕視覺首頁，幻燈片圖片可在後台指定，未指定時從圖庫隨機選擇。
- 圖片庫支援瀑布流、搜尋、按作品/角色/分級篩選，以及按最新、隨機、收藏數、解析度排序。
- 圖片點擊後在目前頁面開啟詳情浮層，同時保留獨立圖片詳情路由。
- 作品頁和角色頁支援媒體庫風格背景、封面、頭像、分頁區域和後台編輯頁。
- 固定分級系統：`safe`、`sensitive`、`hidden`。
- 後台圖片管理支援經典表格和瀑布畫廊兩種模式。
- 批次上傳支援預覽、分頁、重複預檢、任務佇列、狀態輪詢，以及上傳前單張移除。
- 批次匯入支援 CSV、JSON、XLSX、XLSM 範本。
- 後台偏好可維護管理員資料、頭像、密碼、圖片管理顯示模式、上傳 worker 參數和首頁/列表背景圖。
- 系統健康面板檢查資料庫、儲存一致性、上傳佇列、ffmpeg、JXR 解碼、AVIF 編碼和 HDR metadata patch 能力。
- 後台安全包含 HttpOnly Cookie 會話、CSRF 校驗、登入防爆破、維運 API Key、安裝鎖和強隨機 `AGMS_AUTH_SECRET`。

## 圖片管線

| 來源 | 入庫策略 | 預覽策略 |
| --- | --- | --- |
| 普通靜態圖片 | 原圖轉 WebP | 產生 WebP preview 和 thumbnail |
| GIF / 動圖 | 保留原格式 | 產生靜態 WebP preview 和 thumbnail |
| JXR / HDR 圖片 | JXR 轉 HDR AVIF，寫入 `nclx / mdcv / clli` | 產生 SDR WebP preview 和 thumbnail |
| 非 8-bit 圖片 | 保留 HDR / 高位元深度原圖 | 產生 SDR WebP preview 和 thumbnail |

允許上傳的常見副檔名包括：

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

後端會同時校驗檔案副檔名和實際解碼能力。不在白名單內、無法解碼或偽裝成圖片的檔案會被拒絕。

## 路由

```text
/                         首頁幻燈片
/gallery                  圖片庫
/images/:id               圖片詳情
/works                    作品列表
/works/:id                作品詳情
/characters               角色列表
/characters/:id           角色詳情
/tags                     分級頁
/search                   搜尋頁
/admin                    後台面板
/install                  首次安裝精靈
/api-docs                 後台 API 文件
```

## 技術棧

| 層級 | 技術 |
| --- | --- |
| 前端 | Vue 3, Vite, Pinia, Vue Router, Element Plus |
| 後端 | FastAPI, SQLAlchemy, Alembic, Pydantic |
| 資料庫 | 本機開發使用 SQLite，生產環境使用 MySQL/MariaDB |
| 圖片處理 | Pillow, pillow-heif, imagecodecs, ffmpeg |
| 部署 | systemd, Nginx, 寶塔/Linux 裸機 |

## 環境需求

- Python 3.12 或更新版本
- Node.js 20 或更新版本
- 生產環境使用 MySQL 8.x / MariaDB 11.x，本機開發可用 SQLite
- 支援 AVIF/AV1 編碼的 ffmpeg

## 本機開發

後端：

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

前端：

```bash
cd frontend
npm install
npm run dev
```

Vite 開發伺服器預設執行於 `http://127.0.0.1:5173/`。

## 配置

複製 `.env.example` 為 `.env`，按部署環境調整配置。

```text
AGMS_DATABASE_URL                  SQLite 或 MySQL SQLAlchemy 連線字串
AGMS_STORAGE_PATH                  原圖、預覽圖、縮圖和任務檔案的儲存根目錄
AGMS_ADMIN_USERNAME                初始備援管理員使用者名稱
AGMS_ADMIN_PASSWORD                初始備援管理員密碼
AGMS_AUTH_SECRET                   會話簽章強密鑰，由安裝器產生
AGMS_AUTH_TOKEN_TTL_SECONDS        管理員會話有效期
AGMS_COOKIE_SECURE                 HTTPS 後建議設為 true
AGMS_MAX_UPLOAD_SIZE               最大上傳大小
AGMS_PREVIEW_MAX_SIZE              預覽圖最長邊
AGMS_THUMBNAIL_MAX_SIZE            縮圖最長邊
AGMS_CORS_ORIGINS                  允許的瀏覽器來源
```

`AGMS_AUTH_SECRET` 不是 API Key。它用於後端簽發和校驗管理員會話，必須保密。安裝器會自動產生；如果繞過安裝器，請手動產生強隨機值：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 首次安裝

當 `installed.lock` 不存在，且目標資料庫沒有有效 Alembic 版本時，前端會進入 `/install`。

安裝器支援初始化 SQLite 或 MySQL：

- SQLite：資料庫路徑由程式決定。
- MySQL：填寫主機、連接埠、資料庫名、使用者名稱和密碼。
- 儲存：使用專案 `storage/` 目錄。
- 管理員：設定第一個管理員帳號和密碼。
- 密鑰：自動產生並寫入 `.env`。

安裝成功後，程式會寫入 `.env`、執行遷移、初始化管理員帳號、建立 `installed.lock`，必要時提示重啟後端。

## 部署

建立目錄並安裝後端依賴：

```bash
sudo mkdir -p /opt/anime-gallery
sudo rsync -a ./ /opt/anime-gallery/
sudo bash /opt/anime-gallery/scripts/create_linux_dirs.sh

cd /opt/anime-gallery
sudo python3 -m venv venv
sudo /opt/anime-gallery/venv/bin/pip install -r backend/requirements.txt
sudo cp .env.example .env
```

生產 MySQL 範例：

```sql
CREATE DATABASE anime_gallery
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'anime_gallery'@'127.0.0.1' IDENTIFIED BY 'change-this-db-password';
GRANT ALL PRIVILEGES ON anime_gallery.* TO 'anime_gallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

設定 `AGMS_DATABASE_URL`：

```env
AGMS_DATABASE_URL=mysql+pymysql://anime_gallery:change-this-db-password@127.0.0.1:3306/anime_gallery?charset=utf8mb4
```

執行遷移並建置前端：

```bash
cd /opt/anime-gallery/backend
sudo -u www-data /opt/anime-gallery/venv/bin/alembic upgrade head

cd /opt/anime-gallery/frontend
npm install
npm run build
```

安裝 systemd 和 Nginx 範例：

```bash
sudo cp /opt/anime-gallery/scripts/anime-gallery.service /etc/systemd/system/anime-gallery.service
sudo systemctl daemon-reload
sudo systemctl enable --now anime-gallery

sudo cp /opt/anime-gallery/scripts/nginx-anime-gallery.conf /etc/nginx/sites-available/anime-gallery.conf
sudo ln -s /etc/nginx/sites-available/anime-gallery.conf /etc/nginx/sites-enabled/anime-gallery.conf
sudo nginx -t
sudo systemctl reload nginx
```

把 Nginx 範例中的 `gallery.example.com` 改成自己的網域，生產環境啟用 HTTPS。

## Release 包部署

GitHub Releases 會提供預建部署包：

```text
MoeGallery-vX.Y.Z.zip
MoeGallery-vX.Y.Z.tar.gz
SHA256SUMS.txt
```

壓縮包包含後端原始碼、Alembic 遷移、已建置的 `frontend/dist`、部署腳本、文件、`.env.example`，以及空的 `storage/` 和 `logs/` 目錄。壓縮包不會包含 `.env`、資料庫檔案、上傳圖片、日誌、虛擬環境、`node_modules` 或私鑰。

部署 Release 包：

```bash
sudo mkdir -p /opt/anime-gallery
sudo tar -xzf MoeGallery-vX.Y.Z.tar.gz -C /opt/anime-gallery --strip-components=1

cd /opt/anime-gallery
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r backend/requirements.txt
sudo cp .env.example .env
```

然後編輯 `.env`、執行遷移、安裝 systemd 服務並啟用 Nginx 配置。已有部署升級前應先備份 `.env`、`storage/` 和資料庫。

## 自動 Release

倉庫已透過 `.github/workflows/release.yml` 支援自動發布 GitHub Releases。

透過 tag 發布：

```bash
git tag v0.1.0
git push origin v0.1.0
```

也可以在 GitHub Actions 頁面手動執行 `Release` workflow，填寫 `v0.1.0` 這樣的版本號。

workflow 會安裝 Node.js 和 Python、檢查後端語法、建置前端、執行 `scripts/package_release.py` 打包、上傳 workflow artifact，並建立或更新 GitHub Release。

## ESA/CDN 後的真實客戶端 IP

如果站點套了阿里雲 ESA/CDN，需要把邊緣節點提供的真實客戶端 IP 傳給後端。範例 Nginx 配置優先使用 `ali-real-client-ip`，相容 `ali-cdn-real-ip` 和 `true-client-ip`，最後回退到 `$remote_addr`。

後端也會識別這些標頭，並且只信任來自本機/內網反向代理的轉發標頭。生產環境建議透過安全組、防火牆或回源鑑權限制源站直連，避免外部偽造真實 IP 標頭。

## API

OpenAPI 文件地址：

```text
/api-docs
/api-docs/openapi.json
/openapi.json
```

API 文件需要管理員認證。維運自動化可以使用管理員會話 Cookie 或已配置的 operations API key。

## 安全說明

- 後台寫操作需要有效的 HttpOnly 會話 Cookie。
- 帶會話 Cookie 的非安全請求必須包含 CSRF token header。
- 登入失敗會同時按客戶端 IP 和使用者名稱限流。
- API Key 只用於維運自動化，不應暴露給瀏覽器。
- `/storage/*` 透過後端受控路由輸出，私有/隱藏檔案不能直接按路徑匿名取得。
- 如果後端使用多 worker 或多實例，登入限流計數應遷移到 Redis 等共享儲存。
- 不要把 `.env`、資料庫備份、上傳媒體和私鑰提交到公開倉庫。

## 授權

本專案原始碼基於 [MIT License](LICENSE) 開源。

上傳圖片、角色作品圖、匯入元資料和使用者提供的媒體內容不會自動包含在本倉庫授權範圍內。
