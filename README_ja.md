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
  <a href="https://anime.chitanda.net/">Live Site</a> |
  <a href="https://anime.chitanda.net/api-docs">API Docs</a> |
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

## 概要

MoeGallery は、アニメ系イラスト、スクリーンショット、作品、キャラクター、レーティング、画像メタデータを整理するためのセルフホスト型画像メディアライブラリです。閲覧用の公開ギャラリーと、アップロード、関連付け、編集、インポート、保守を行う管理パネルを提供します。

このプロジェクトは「画像版 Jellyfin」に近い構成です。フロントエンドはギャラリー閲覧、作品ページ、キャラクターページ、レーティング、ホームスライドショー、画像詳細オーバーレイを担当し、バックエンドはアップロード、メタデータ、ストレージ、重複チェック、画像変換、バックグラウンドジョブ、認証、API ドキュメントを担当します。

## 機能

- 管理画面で指定できる全画面ホームスライドショー。未指定の場合はギャラリーからランダムに選択します。
- ウォーターフォール形式の画像ギャラリー、検索、作品/キャラクター/レーティングによるフィルター、最新/ランダム/お気に入り数/解像度による並び替え。
- 画像クリックで現在のページ上に詳細オーバーレイを表示し、直接アクセス用の詳細ルートも保持します。
- 作品ページとキャラクターページは、メディアライブラリ風の背景、ポスター、アバター、ページ分割されたセクション、管理編集ページに対応します。
- 固定レーティング: `safe`、`sensitive`、`hidden`。
- 管理画面の画像管理は、クラシックテーブル表示とウォーターフォール表示を切り替え可能です。
- 一括アップロードは、プレビュー、ページ分割、重複事前チェック、タスクキュー、状態ポーリング、アップロード前の単体削除に対応します。
- CSV、JSON、XLSX、XLSM テンプレートによる一括メタデータインポート。
- 管理者プロフィール、アバター、パスワード、画像管理表示モード、アップロード worker 設定、ホーム/一覧背景画像を管理画面から変更できます。
- システムヘルスでは、データベース、ストレージ整合性、アップロードキュー、ffmpeg、JXR デコード、AVIF エンコード、HDR metadata patch 能力を確認できます。
- HttpOnly Cookie セッション、CSRF 検証、ログイン総当たり対策、運用 API Key、インストールロック、強力な `AGMS_AUTH_SECRET` を備えています。

## 画像パイプライン

| 入力 | 保存方針 | プレビュー方針 |
| --- | --- | --- |
| 通常の静止画 | 原画像を WebP に変換 | WebP preview / thumbnail を生成 |
| GIF / アニメーション画像 | 元形式を保持 | 静止 WebP preview / thumbnail を生成 |
| JXR / HDR 画像 | JXR を HDR AVIF に変換し、`nclx / mdcv / clli` を書き込み | SDR WebP preview / thumbnail を生成 |
| 8-bit 以外の画像 | HDR / 高ビット深度の原画像を保持 | SDR WebP preview / thumbnail を生成 |

対応する主なアップロード拡張子:

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

バックエンドは拡張子と実際のデコード可否の両方を検証します。ホワイトリスト外のファイル、デコードできないファイル、画像を装った非画像ファイルは拒否されます。

## ルート

```text
/                         ホームスライドショー
/gallery                  画像ギャラリー
/images/:id               画像詳細
/works                    作品一覧
/works/:id                作品詳細
/characters               キャラクター一覧
/characters/:id           キャラクター詳細
/tags                     レーティングページ
/search                   検索ページ
/admin                    管理パネル
/install                  初回インストールウィザード
/api-docs                 管理 API ドキュメント
```

## 技術スタック

| レイヤー | 技術 |
| --- | --- |
| Frontend | Vue 3, Vite, Pinia, Vue Router, Element Plus |
| Backend | FastAPI, SQLAlchemy, Alembic, Pydantic |
| Database | ローカル開発は SQLite、本番は MySQL/MariaDB |
| Image processing | Pillow, pillow-heif, imagecodecs, ffmpeg |
| Deployment | systemd, Nginx, BaoTa/Linux bare metal |

## 要件

- Python 3.12 以上
- Node.js 20 以上
- 本番環境では MySQL 8.x / MariaDB 11.x、ローカル開発では SQLite
- AVIF/AV1 エンコード対応の ffmpeg

## 開発

バックエンド:

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

フロントエンド:

```bash
cd frontend
npm install
npm run dev
```

Vite 開発サーバーは既定で `http://127.0.0.1:5173/` で起動します。

## 設定

`.env.example` を `.env` にコピーし、デプロイ環境に合わせて調整します。

```text
AGMS_DATABASE_URL                  SQLite または MySQL の SQLAlchemy URL
AGMS_STORAGE_PATH                  原画像、プレビュー、サムネイル、タスクファイルの保存ルート
AGMS_ADMIN_USERNAME                初期フォールバック管理者名
AGMS_ADMIN_PASSWORD                初期フォールバック管理者パスワード
AGMS_AUTH_SECRET                   セッション署名用の強力な秘密鍵。インストーラーが生成
AGMS_AUTH_TOKEN_TTL_SECONDS        管理者セッションの有効期間
AGMS_COOKIE_SECURE                 HTTPS 配下では true を推奨
AGMS_MAX_UPLOAD_SIZE               最大アップロードサイズ
AGMS_PREVIEW_MAX_SIZE              プレビュー画像の最長辺
AGMS_THUMBNAIL_MAX_SIZE            サムネイル画像の最長辺
AGMS_CORS_ORIGINS                  許可するブラウザー origin
```

`AGMS_AUTH_SECRET` は API Key ではありません。バックエンドの管理者セッションを署名・検証するための秘密値であり、外部に公開してはいけません。インストーラーが自動生成します。インストーラーを使わない場合は、次のように強力な値を生成してください。

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 初回インストール

`installed.lock` が存在せず、対象データベースに有効な Alembic バージョンがない場合、フロントエンドは `/install` に入ります。

インストーラーは SQLite または MySQL を初期化できます。

- SQLite: データベースパスはアプリケーションが決定します。
- MySQL: ホスト、ポート、データベース名、ユーザー名、パスワードを入力します。
- Storage: プロジェクトの `storage/` ディレクトリを使用します。
- Admin: 最初の管理者ユーザー名とパスワードを設定します。
- Secret: 自動生成され `.env` に書き込まれます。

インストール成功後、アプリは `.env` の書き込み、マイグレーション、管理者アカウント初期化、`installed.lock` 作成を行い、必要に応じてバックエンド再起動を求めます。

## デプロイ

ディレクトリを作成し、バックエンド依存関係をインストールします。

```bash
sudo mkdir -p /opt/anime-gallery
sudo rsync -a ./ /opt/anime-gallery/
sudo bash /opt/anime-gallery/scripts/create_linux_dirs.sh

cd /opt/anime-gallery
sudo python3 -m venv venv
sudo /opt/anime-gallery/venv/bin/pip install -r backend/requirements.txt
sudo cp .env.example .env
```

本番 MySQL の例:

```sql
CREATE DATABASE anime_gallery
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'anime_gallery'@'127.0.0.1' IDENTIFIED BY 'change-this-db-password';
GRANT ALL PRIVILEGES ON anime_gallery.* TO 'anime_gallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

`AGMS_DATABASE_URL` を設定します。

```env
AGMS_DATABASE_URL=mysql+pymysql://anime_gallery:change-this-db-password@127.0.0.1:3306/anime_gallery?charset=utf8mb4
```

マイグレーションを実行し、フロントエンドをビルドします。

```bash
cd /opt/anime-gallery/backend
sudo -u www-data /opt/anime-gallery/venv/bin/alembic upgrade head

cd /opt/anime-gallery/frontend
npm install
npm run build
```

systemd と Nginx の例をインストールします。

```bash
sudo cp /opt/anime-gallery/scripts/anime-gallery.service /etc/systemd/system/anime-gallery.service
sudo systemctl daemon-reload
sudo systemctl enable --now anime-gallery

sudo cp /opt/anime-gallery/scripts/nginx-anime-gallery.conf /etc/nginx/sites-available/anime-gallery.conf
sudo ln -s /etc/nginx/sites-available/anime-gallery.conf /etc/nginx/sites-enabled/anime-gallery.conf
sudo nginx -t
sudo systemctl reload nginx
```

Nginx 例の `gallery.example.com` を自分のドメインに変更し、本番環境では HTTPS を有効にしてください。

## Release パッケージでのデプロイ

GitHub Releases にはビルド済みデプロイアーカイブが含まれます。

```text
MoeGallery-vX.Y.Z.zip
MoeGallery-vX.Y.Z.tar.gz
SHA256SUMS.txt
```

アーカイブには、バックエンドソース、Alembic マイグレーション、ビルド済み `frontend/dist`、デプロイスクリプト、ドキュメント、`.env.example`、空の `storage/` と `logs/` ディレクトリが含まれます。`.env`、データベースファイル、アップロード画像、ログ、仮想環境、`node_modules`、秘密鍵は含まれません。

Release パッケージをデプロイする例:

```bash
sudo mkdir -p /opt/anime-gallery
sudo tar -xzf MoeGallery-vX.Y.Z.tar.gz -C /opt/anime-gallery --strip-components=1

cd /opt/anime-gallery
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r backend/requirements.txt
sudo cp .env.example .env
```

その後、`.env` を編集し、マイグレーションを実行し、systemd サービスと Nginx 設定を有効化します。既存環境を更新する場合は、事前に `.env`、`storage/`、データベースをバックアップしてください。

## Release 自動化

このリポジトリは `.github/workflows/release.yml` により GitHub Releases の自動発行に対応しています。

タグからリリースを作成する場合:

```bash
git tag v0.1.0
git push origin v0.1.0
```

または GitHub Actions 画面で `Release` workflow を手動実行し、`v0.1.0` のようなバージョンを入力します。

workflow は Node.js と Python をセットアップし、バックエンド構文を確認し、フロントエンドをビルドし、`scripts/package_release.py` でパッケージを作成し、workflow artifact をアップロードして GitHub Release を作成または更新します。

## ESA/CDN 配下の実クライアント IP

Alibaba Cloud ESA/CDN 配下で運用する場合、エッジが提供する実クライアント IP をバックエンドへ渡してください。Nginx 例は `ali-real-client-ip` を優先し、`ali-cdn-real-ip` と `true-client-ip` にも対応し、最後に `$remote_addr` へフォールバックします。

バックエンドもこれらのヘッダーを理解し、loopback/private のリバースプロキシから来た転送ヘッダーのみを信頼します。本番環境では、セキュリティグループ、ファイアウォール、または origin 認証ヘッダーで origin への直接アクセスを制限し、実 IP ヘッダーの偽装を防いでください。

## API

OpenAPI ドキュメント:

```text
/api-docs
/api-docs/openapi.json
/openapi.json
```

API ドキュメントには管理者認証が必要です。運用自動化では、管理者セッション Cookie または設定済み operations API key を使用できます。

## セキュリティ

- 管理画面の書き込み操作には有効な HttpOnly セッション Cookie が必要です。
- セッション Cookie 付きの unsafe request には CSRF token header が必要です。
- ログイン失敗はクライアント IP とユーザー名の両方でレート制限されます。
- API Key は運用自動化専用であり、ブラウザーへ公開してはいけません。
- `/storage/*` はバックエンド管理ルート経由で配信され、private/hidden ファイルをパスだけで匿名取得することはできません。
- バックエンドを複数 worker または複数インスタンスで動かす場合、ログインレート制限のカウンターは Redis などの共有ストアへ移行してください。
- `.env`、データベースダンプ、アップロードメディア、秘密鍵を公開リポジトリへコミットしないでください。

## ライセンス

このプロジェクトのソースコードは [MIT License](LICENSE) の下で公開されています。

アップロード画像、キャラクター/作品画像、インポートされたメタデータ、ユーザー提供メディアは、このリポジトリのライセンス範囲に自動的には含まれません。
