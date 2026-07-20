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
  <a href="https://anime.chitanda.net/">Live Site</a> |
  <a href="https://anime.chitanda.net/api-docs">API Docs</a> |
  <a href="https://github.com/violetaini/MoeGallery/releases">Releases</a>
</p>

MoeGallery は、公開ギャラリーと管理パネルを備えたセルフホスト型アニメ画像メディアライブラリです。画像、作品、キャラクター、レーティング、メタデータ、画像処理、API を一元管理できます。

## クイックスタート

推奨インストーラーは systemd を使用する Linux 向けで、ビルド済み Release をインストールします。デプロイに Node.js は不要です。

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
sudo bash install.sh
```

インストーラーが確認するのは待受方式だけです。

- `127.0.0.1`: ローカルアクセス、または自分で設定するリバースプロキシ向け。推奨。
- `0.0.0.0`: 公開ネットワークまたは LAN から直接アクセス。

既定のポートは `8111` です。起動後に次を開きます。

```text
http://SERVER_IP:8111/install
```

Web インストーラーがデータベース、管理者、マイグレーション、セッション秘密鍵、API Key、ストレージ、インストールロックを初期化します。

| データベース | セットアップ |
| --- | --- |
| SQLite | SQLite を選択して続行します。保存場所は MoeGallery が決定します。 |
| MySQL / MariaDB | 空のデータベースと専用ユーザーを作成してから接続情報を入力します。 |

非対話で公開待受を設定する例：

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

MoeGallery はドメイン、TLS 証明書、ファイアウォール、リバースプロキシを設定しません。詳細は[デプロイガイド](docs/deployment.md)を参照してください。

## インストール内容

- 既定のインストール先は `/opt/moegallery`。
- systemd unit は `moegallery.service` の 1 つだけ。
- 専用の非 root ユーザー `moegallery`。
- FastAPI の起動とパネル更新を管理する組み込みランチャー。
- 同じポートから配信されるビルド済みフロントエンド。

独立した updater サービスや updater 用 sudoers ルールは使用しません。

## 主な機能

- 管理画面から画像を選べる全画面ホームスライドショー。
- 検索、作品/キャラクター/レーティング絞り込み、並べ替え、自動読み込み、プリフェッチ対応ギャラリー。
- 画像詳細オーバーレイと直接アクセス用詳細ルート。
- 背景、ポスター、アバター、ページングを備えた作品・キャラクターページ。
- `safe`、`sensitive`、`hidden` の固定レーティング。
- クラシック表とウォーターフォールの管理表示、一括操作。
- 一括アップロード、重複事前検査、処理キュー、再試行、メタデータ関連付け。
- CSV、JSON、XLSX、XLSM インポートテンプレート。
- SQLite と MySQL/MariaDB。
- HttpOnly 管理者セッション、CSRF 検証、ログイン制限、API Key、自動生成される強力な秘密鍵。
- パネルからの Release 確認、チェックサム検証、バックアップ、マイグレーション、ヘルスチェック、自動復元。

## 画像パイプライン

| 入力 | 原画像 | ブラウザプレビュー |
| --- | --- | --- |
| 通常の静止画 | WebP に変換 | WebP preview / thumbnail |
| GIF / アニメーション | アニメーションを保持 | 静止 WebP preview / thumbnail |
| JXR / HDR | `nclx / mdcv / clli` 付き HDR AVIF | SDR WebP preview / thumbnail |
| その他の高ビット深度画像 | 互換性のある HDR 原画像を保持 | SDR WebP preview / thumbnail |

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

拡張子と実際のデコーダー対応を検証し、偽装ファイルやデコード不能なファイルは拒否します。

## 更新とバックアップ

インストール後は **管理画面 > 更新センター** から更新します。組み込みランチャーが稼働中に Release をダウンロードして検証し、インストールとマイグレーションの間だけ Web 子プロセスを停止します。再起動後のヘルスチェックに失敗した場合は、更新前のアプリケーションとデータベースを復元します。

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_before_upgrade.sh \
  --app-dir /opt/moegallery
```

SQLite は SQLite backup API、MySQL/MariaDB は `mysqldump --single-transaction` を使用します。

## ドキュメント

- [Deployment guide](docs/deployment.md)
- [中国語デプロイガイド](docs/deployment_zh.md)
- [API operations guide](docs/api/operations-guide.md)
- 管理者ログイン後の対話型 API ドキュメント: `/api-docs`

## 開発

Python 3.11 以降と Node.js 20 以降が必要です。

```bash
python -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
cd backend && ../.venv/bin/uvicorn app.main:app --reload --port 8000

cd frontend
npm ci
npm run dev
```

## セキュリティ

- `.env`、`installed.lock`、データベース、アップロード画像、バックアップ、秘密鍵を Git に登録しないでください。
- 信頼できないネットワークから管理画面を公開する前に HTTPS を設定してください。
- MySQL には管理者ではなく専用ユーザーを使用してください。
- Release の SHA256 検証を維持し、信頼できる GitHub プロキシだけを使用してください。

## ライセンス

MoeGallery は [MIT License](LICENSE) で公開されています。
