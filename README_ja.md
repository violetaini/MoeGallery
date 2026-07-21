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
  <a href="https://anime.chitanda.net/">公開サイト</a> |
  <a href="https://anime.chitanda.net/api-docs">API ドキュメント</a> |
  <a href="https://github.com/violetaini/MoeGallery/releases">リリース</a>
</p>

MoeGallery は、アニメ作品の画像を整理・公開するためのセルフホスト型メディアライブラリです。閲覧者向けのギャラリーと管理者向けの管理画面を備え、画像、作品、キャラクター、レーティングなどの情報を一元管理できます。一括インポート、画像処理、API 連携にも対応しています。

## クイックスタート

以下のインストール方法は、systemd を採用している Linux ディストリビューション向けです。インストーラーはビルド済みのリリースパッケージを取得するため、デプロイ先に Node.js をインストールする必要はありません。

```bash
curl -fsSLO https://github.com/violetaini/MoeGallery/releases/latest/download/install.sh
sudo bash install.sh
```

初回実行時に、サービスの待ち受けアドレスだけを選択します。

- `127.0.0.1`: サーバー内部からのみ接続を受け付けます。Nginx やホスティングパネルでリバースプロキシを構成する場合に推奨します。
- `0.0.0.0`: すべてのネットワークインターフェースで待ち受け、LAN または公開 IP アドレスから直接アクセスできます。

既定のポートは `8111` です。インストールが完了すると、初回セットアップ用の URL が表示されます。既定の待ち受けアドレスを使用する場合は、サーバー上で次の URL を開きます。

```text
http://127.0.0.1:8111/install
```

別の端末からセットアップする場合は、先にリバースプロキシまたは SSH トンネルを設定してください。`0.0.0.0` を選択した場合は、`http://SERVER_IP:8111/install` に直接アクセスできます。

続いて Web 画面でデータベースを選択し、管理者アカウントを作成します。MoeGallery はセッション署名用シークレットと初期 API キーを自動生成し、データベースのマイグレーション、ストレージディレクトリの初期化、インストール状態の記録を行います。

| データベース | セットアップ |
| --- | --- |
| SQLite | SQLite を選択して続行します。データベースファイルは既定のアプリケーションディレクトリに保存されるため、パスの入力は不要です。 |
| MySQL / MariaDB | 空のデータベースと専用のアプリケーションユーザーを作成し、セットアップ画面で接続情報を入力します。 |

対話なしでインストールし、すべてのネットワークインターフェースで待ち受ける場合：

```bash
sudo bash install.sh --host 0.0.0.0 --port 8111 --non-interactive
```

インストーラーが設定するのは MoeGallery 本体のみです。ドメイン、TLS 証明書、ファイアウォール、CDN、リバースプロキシは別途設定してください。待ち受けアドレス、サービス管理、MySQL の準備、手動インストールについては、[デプロイガイド（英語）](docs/deployment.md)を参照してください。

## インストール内容

- 既定のインストール先は `/opt/moegallery` です。
- `moegallery.service` という systemd サービスを 1 つ作成します。
- ログインシェルと root 権限を持たない専用の `moegallery` サービスユーザーを作成します。このユーザーは MoeGallery の実行とアプリケーションディレクトリの読み書きに使用され、管理画面にログインする管理者アカウントとは別です。`--user` を指定すれば、既存のシステムユーザーも利用できます。
- 組み込みランチャーが FastAPI の起動、更新、ヘルスチェック、ロールバックを管理します。
- FastAPI が API とビルド済みフロントエンドを同じポートで配信します。

更新機能はメインサービスに組み込まれているため、更新専用のサービスや、パスワードなしで sudo を実行するための設定は追加されません。

## 主な機能

- 画面全体を使ったホームスライドショー。表示する画像は管理画面で指定でき、未指定の場合はライブラリからランダムに選ばれます。
- 検索、並べ替え、作品・キャラクター・レーティングによる絞り込みに対応した Masonry（メイソンリー）形式のギャラリー。
- ページ末尾での自動読み込みと、次に表示する画像の先読み。
- 画像をクリックすると現在のページ上に詳細を表示し、画像ごとの固定 URL からも直接アクセスできます。
- 背景画像、ポスター、アバター、ページネーションを備えたメディアライブラリ形式の作品・キャラクターページ。
- レーティングは `safe`、`sensitive`、`hidden` の 3 種類で固定されています。
- 管理画面では表形式と Masonry 形式を切り替えられ、どちらも一括操作に対応しています。
- ファイルのプレビュー、重複チェック、処理キュー、再試行、メタデータ設定に対応した一括アップロード。
- CSV、JSON、XLSX、XLSM 形式の一括インポート用テンプレート。
- 初回セットアップ時に SQLite または MySQL/MariaDB を選択可能。
- HttpOnly 管理者セッション、CSRF 検証、ログイン試行回数の制限、API キー、安全なランダム値から自動生成されるセッションシークレット。
- GitHub の新しいリリースの確認、更新パッケージの検証、データベースのバックアップとマイグレーション、ヘルスチェック、失敗時の自動ロールバックを管理画面から実行できます。

## 画像処理

| アップロード形式 | 保存形式 | ブラウザでの表示 |
| --- | --- | --- |
| 一般的な静止画 | WebP に変換 | WebP のプレビュー画像とサムネイル |
| GIF などのアニメーション画像 | 元のアニメーション形式を保持 | 静止画の WebP プレビュー画像とサムネイル |
| JXR または HDR 画像 | `nclx / mdcv / clli` メタデータを含む HDR AVIF に変換 | 通常のページでは SDR WebP のプレビュー画像とサムネイル |
| その他の高ビット深度画像 | 対応形式の場合は HDR 原画像を保持 | 通常のページでは SDR WebP のプレビュー画像とサムネイル |

対応している主なファイル拡張子：

```text
.jpg .jpeg .png .webp .gif .bmp .tif .tiff .heif .heic .avif .jxr
```

拡張子だけでなく、画像を実際にデコードできるかどうかも確認します。拡張子を偽装したファイルや、サーバーでデコードできないファイルは受け付けません。

## 更新とバックアップ

インストール後は、**管理画面 > 更新センター** からアップデートできます。更新パッケージのダウンロードと検証中もサイトは利用できます。Web サービスが短時間停止するのは、ファイルの置き換えとデータベースのマイグレーションを行う間だけです。新しいバージョンの起動後に `/api/health` のヘルスチェックに失敗した場合は、更新前のアプリケーションとデータベースを復元し、旧バージョンを再起動します。

手動でバックアップする場合：

```bash
sudo -u moegallery bash /opt/moegallery/scripts/backup_before_upgrade.sh \
  --app-dir /opt/moegallery
```

SQLite では SQLite Backup API を使って整合性のあるバックアップを作成します。MySQL/MariaDB では `mysqldump --single-transaction --no-tablespaces` を使用するため、サーバーに MySQL クライアントツールが必要です。

## ドキュメント

- [デプロイガイド（英語）](docs/deployment.md)
- [デプロイガイド（簡体字中国語）](docs/deployment_zh.md)
- [API 運用ガイド（英語）](docs/api/operations-guide.md)
- 管理者ログイン後に利用できる対話型 API ドキュメント：`/api-docs`
- OpenAPI ドキュメント：`docs/api/openapi.json`

## 開発

ローカル開発には Python 3.11 以降と Node.js 20 以降が必要です。

```bash
# バックエンド
python -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
cd backend
../.venv/bin/uvicorn app.main:app --reload --port 8000

# 別のターミナルでフロントエンドを起動
cd frontend
npm ci
npm run dev
```

フロントエンドの開発サーバーは `http://127.0.0.1:5173` で起動し、API とストレージへのリクエストをローカルの `8000` ポートで動作するバックエンドへ転送します。

## 主なルート

```text
/                ホームスライドショー
/gallery         画像ギャラリー
/works           作品
/characters      キャラクター
/tags            レーティング
/admin            管理画面
/install          初回セットアップ
/api-docs         管理者向け API ドキュメント
```

## セキュリティ

- `.env`、`installed.lock`、データベース、アップロード画像、バックアップ、秘密鍵を Git に登録しないでください。
- 管理画面をインターネットに公開する前に HTTPS を設定してください。
- MoeGallery 専用の MySQL アカウントを作成し、MySQL の root やその他の管理者アカウントは使用しないでください。
- リリースパッケージの SHA256 検証を無効にしないでください。GitHub プロキシが必要な場合は、信頼できるものだけを使用してください。
- セキュリティ上の問題を見つけた場合は、認証情報や攻撃手順を公開せず、非公開で報告してください。

## ライセンス

MoeGallery は [MIT License](LICENSE) で公開されています。
