# Anime Gallery Media Server

Anime Gallery Media Server 是一个本地部署的二次元图片媒体库，定位接近“图片版本 Jellyfin”：前台面向游客展示图片瀑布流、作品、角色和分级，后台用于维护作品、角色、图片与元数据。第一版不使用 Docker，开发环境默认 SQLite，生产部署建议使用 MySQL。

## 1. 项目整体说明

项目核心模型是 `作品 Work - 角色 Character - 图片 Image`，图片通过中间表绑定多个作品、多个角色和多个标签。图片上传后会保存原图，自动生成 preview 与 thumbnail，并记录宽高、大小、MIME、sha256 和 phash。前台作品详情页采用更接近 Jellyfin 的布局，包含背景图、海报、标语、作品元数据，以及按宽度自适应分页的角色区和图片区。分级系统固定为 `safe / sensitive / hidden`。前端使用 Vue 3 + Vite + Element Plus，后端使用 FastAPI + SQLAlchemy + Alembic + Pillow。
当前图片管线按动态范围分流：普通静态图原图统一转成 WebP，动图保留原格式，检测到 HDR 或非 8-bit 图片时保留原始文件，同时继续生成 SDR WebP 的 preview 与 thumbnail。JPEG XR (`.jxr`) 现已支持入库，并会转码为带完整 HDR 静态 metadata 的 AVIF 原图存储：文件中同时写入 `BT.2020 + PQ` 的 `nclx`，以及 `mdcv / clli` 盒。前端详情图和作品背景会根据 `dynamic-range: high` 自动优先取浏览器可直接显示的 HDR 原图，SDR 屏幕继续使用 WebP 衍生图。

后台已加入管理员登录，写接口需要 HttpOnly Cookie 会话并校验 CSRF。作品封面、作品背景图和角色头像都改成“先上传图片，再从图片库里选择绑定”的方式，后续编辑时可以直接替换。

目录结构：

```text
/opt/anime-gallery/
├── backend/
├── frontend/
├── storage/
│   ├── original/
│   ├── preview/
│   └── thumbnail/
├── logs/
└── scripts/
```

开发时当前仓库也使用同样的相对结构。

## 2. 功能清单

- 前台：首页图片瀑布流、关键词搜索、按作品/角色/分级筛选、按最新/随机/收藏数/分辨率排序、加载更多。首页默认不展示带作品或角色关联的图片。
- 前台：图片详情、作品列表与详情、角色列表与详情、分级页、搜索页。
- 前台图片墙点击图片后，在当前页面上方弹出磨砂玻璃浮层显示图片详情；直接地址访问仍保留独立详情页。
- 前台图片详情支持匿名本机收藏/取消收藏，浏览器用 localStorage 记录已收藏图片，避免同一浏览器重复点击反复加数；浏览数也按同一浏览器 24 小时节流，避免刷新页面无限累加。
- 后台：统计首页、管理员登录、图片管理（经典表格 / 瀑布图片墙可切换、点击图片编辑、每页数量设置、批量删除、批量修改元信息）、图片上传、作品管理、角色管理、批量导入、系统设置。
- 后台系统设置包含管理员资料、图片管理显示偏好、上传队列参数和系统健康检查。管理员可修改登录用户名、密码和头像，可在页面中调整上传处理 worker 数和单 worker 连续领取数；系统健康区会展示数据库、存储目录一致性、上传队列、ffmpeg、JXR 和 HDR metadata patch 状态，并在接口异常时显示可重试的错误信息。
- 后台批量导入支持 CSV / JSON / XLSX / XLSM 元数据文件，一行可以只导入作品，也可以同时导入作品下的角色。导入页可下载 CSV / JSON / XLSX / XLSM 模板，模板字段以 `work_*` 和 `character_*` 分组。导入采用“预检 -> 确认导入”两段式流程，按作品名匹配作品，按作品名 + 角色名匹配角色，存在则更新，不存在则创建。
- 后台图片上传页支持真正的批量上传工作流：多文件选择后会逐张生成预览，支持 `JXR` 等浏览器原生不显示的格式；预览区支持分页、点击浮层放大查看，以及在上传前单独删除某一张待上传图片。
- 后台图片上传现在走任务队列：提交后每个文件会进入 `queued / processing / success / failed` 状态，前端轮询显示处理结果。重型 JXR/HDR/AVIF 转码不会再长时间占住上传请求。
- 后台作品主页和角色主页支持直接编辑资料，不必退回列表弹窗；作品页可编辑标题、标语、年份、评分、官网、类型、制作公司等，角色页可编辑名称、别名和简介。
- 后台在移动端会把左侧导航折成顶部横向菜单，工具栏、批量操作和上传任务状态都会改为窄屏单列/卡片式布局。
- 图片上传按 `sha256` 判断完全重复文件；上传前会弹窗列出图库已有重复和本批次内重复。默认跳过重复不会修改已有图片元数据，只有用户确认“合并关系后继续”时，才把本次选择的作品/角色关系合并到已有图片。
- 图片处理：原图保存、preview、thumbnail、宽高、文件大小、MIME、sha256、phash、重复图片检测、动图/HDR 标记、位深与色彩配置记录。
- 上传入口已收紧为“只接受服务器明确支持的图片格式”。当前允许的上传后缀包含 `.jpg/.jpeg/.png/.webp/.gif/.bmp/.tif/.tiff/.heif/.heic/.avif/.jxr`，其中：
  SDR 常规格式覆盖 `.jpg/.jpeg/.png/.webp/.gif/.bmp/.tif/.tiff/.heif/.heic/.avif`
  HDR 来源当前重点支持 `.jxr/.avif/.heif/.heic/.png/.tif/.tiff`
  服务器会拒绝不在支持范围内的图片后缀或无法被后端解码的文件。JXR 会转成带 `nclx / mdcv / clli` 的 HDR AVIF 原图，同时生成 SDR WebP 预览。支持范围以 Pillow 和 `imagecodecs` 可解码格式为准，HEIC/HEIF 依赖 `pillow-heif`，JPEG XR (`.jxr`) 依赖 `imagecodecs`，JXR 到 HDR AVIF 的原图转码依赖系统 `ffmpeg`。
- 当前 JXR 转 HDR AVIF 流程不再依赖 `ffmpeg` 直接暴露 `master_display / max_cll` 命令行参数；后端会在编码完成后自行补写 `mdcv / clli` 盒。
- 历史图片可通过 `backend/scripts_convert_originals_to_webp.py --apply` 批量迁移，脚本会跳过动图和 HDR 原图，并顺带回填 `is_animated / dynamic_range / bit_depth / color_profile` 元数据。
- 元数据：rating 分级、公开/隐藏、来源链接、作者、浏览数、收藏数。
- 部署：systemd 管理后端，Nginx 反向代理 API 与前端静态文件，Nginx 直接暴露 storage 静态目录。

## 3. 数据库设计

主要表：

- `works`：作品中文名、原名、别名、简介、封面图片、背景图、标语、首播年份、时长、社区评分、内容分级、类型、制作公司、官网、状态、排序、时间戳。
- `characters`：所属作品、中文名、原名、别名、简介、头像图片、时间戳。
- `images`：文件名、路径、缩略图、预览图、宽高、大小、MIME、是否动图、动态范围、位深、色彩配置、sha256、phash、rating、来源、作者、公开状态、浏览数、收藏数、时间戳。
- `tags`：名称、类型、别名、时间戳。

多对多表：

- `image_works(image_id, work_id)`
- `image_characters(image_id, character_id)`
- `image_tags(image_id, tag_id)`

迁移文件位于 `backend/alembic/versions/`，其中 `0001_initial_schema.py` 是初始结构，`0002_work_media_metadata.py` 增加作品详情页所需的背景图和媒体元数据字段，`0003_app_settings.py` 增加系统设置表，`0004_image_hdr_metadata.py` 增加图片动态范围与位深元数据。MySQL/MariaDB 部署时，安装器会把 `alembic_version.version_num` 预设或修正为 `VARCHAR(128)`，避免较长迁移 revision id 超过 Alembic 默认 `VARCHAR(32)` 后导致首次安装中断；安装状态判断也要求版本表内存在实际版本号，单独空表不会被误判为已安装。

## 4. 后端代码

入口与配置：

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/database.py`

模型：

- `backend/app/models/image.py`
- `backend/app/models/work.py`
- `backend/app/models/character.py`
- `backend/app/models/tag.py`
- `backend/app/models/associations.py`

API：

- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `backend/app/api/images.py`
- `backend/app/api/works.py`
- `backend/app/api/characters.py`
- `backend/app/api/tags.py`
- `backend/app/api/search.py`
- `backend/app/api/stats.py`
- `backend/app/api/settings.py`
- `backend/app/api/imports.py`
- `backend/app/api/system.py`
- `backend/app/api/upload_tasks.py`

接口补充说明：

- 图片公开列表默认只返回公开且非隐藏内容。
- 首页图片流默认排除绑定了作品或角色的图片。
- 图片列表支持按 `rating=safe|sensitive|hidden` 过滤，前台分级页直接复用这个参数。
- 图片管理页默认排除作品封面和角色头像，避免误操作。
- 图片管理页的筛选项改为作品、角色和分级，不再使用标签参数。
- 图片管理页支持 `PUT /api/images/batch` 批量修改作品、角色、分级、收藏数、来源和作者，支持 `DELETE /api/images/batch` 批量删除图片。
- 上传任务队列使用 `POST /api/upload-tasks` 创建任务，`GET /api/upload-tasks` 或 `GET /api/upload-tasks/{task_id}` 查询状态；任务文件暂存于 `storage/tasks/`，成功后清理暂存文件，失败时保留暂存文件便于排障或后续重试。
- 上传重复预检使用 `POST /api/upload-tasks/check-duplicates`，前端先用 Web Crypto 本地计算文件 `sha256`，后端只接收文件名和哈希清单来查数据库索引，避免预检阶段重复上传整批图片。
- 前台收藏使用 `POST /api/images/{image_id}/favorite` 和 `DELETE /api/images/{image_id}/favorite`，只允许公开且非隐藏图片计数。
- 浏览数使用 `POST /api/images/{image_id}/view` 计数，前端同一浏览器 24 小时内只对同一图片请求一次计数。
- 图片文件名只能单张修改，而且必须保留原始后缀，批量编辑不允许改文件名。
- 系统设置里的图片管理显示模式会写入数据库，可在经典表格和瀑布图片墙之间切换。
- 系统设置里的管理员资料会写入数据库。用户名和头像图片 ID 存在 `app_settings`，密码使用 PBKDF2-SHA256 哈希保存；如果数据库中还没有管理员资料，则继续使用 `.env` 中的 `AGMS_ADMIN_USERNAME` 和 `AGMS_ADMIN_PASSWORD` 作为初始化兜底。
- 系统设置里的上传队列参数会写入数据库，支持调整 `upload_worker_count` 和 `upload_claim_batch_size`；保存后后端会按新参数补齐上传处理 worker。
- 前端列表统一显示展示序号，不直接把数据库主键 ID 暴露给用户；真实 ID 仍用于路由、接口和数据库关联。
- 图片接口会返回 `is_animated / dynamic_range / bit_depth / color_profile`，前端据此在 HDR 屏幕优先请求原图，在 SDR 屏幕继续使用 WebP 预览图。
- 后台写接口需要管理员登录后的 HttpOnly Cookie 会话；非 GET/HEAD/OPTIONS 请求还会校验 `X-CSRF-Token`。
- 登录会话记录存储在 `admin_sessions` 表，服务端只保存会话令牌哈希。退出登录会吊销当前会话；系统设置支持一键轮换 `AGMS_AUTH_SECRET`，轮换后会吊销全部后台会话并要求重新登录。
- 登录接口带基础防爆破保护：`POST /api/auth/login` 会按来源 IP 统计失败次数，默认 5 分钟内最多允许 8 次失败；超过阈值返回 `429 Too many login attempts`，成功登录后清空该 IP 的失败记录。
- `/storage/*` 现已改为后端受控文件路由，不再直接公开挂载 storage 目录。非公开图片和隐藏图片，匿名用户不能通过文件路径直接访问。
- 作品封面、作品背景图和角色头像都复用图片库中的图片记录，不再手填外部图片 ID。
- 作品详情接口会返回背景图和角色头像等嵌套数据，便于前台做 Jellyfin 风格展示。
- `POST /api/imports/metadata` 支持上传 CSV / JSON / XLSX / XLSM 元数据文件，`dry_run=true` 时只做预检，`dry_run=false` 时正式写入作品和角色。
- `GET /api/imports/metadata/template?format=csv|json|xlsx|xlsm` 下载批量导入模板。模板包含一行仅作品示例和一行作品 + 角色示例，后端测试会基于同样字段覆盖四种格式的预检与正式导入。
- `GET /api/system/health` 返回数据库、storage 目录、原图/预览/缩略图数量一致性、上传队列参数、ffmpeg、AVIF 编码、JXR 解码和 HDR metadata patch 能力状态，用于系统设置页部署诊断。

图片处理：

- `backend/app/services/image_service.py`
- `backend/app/services/storage_service.py`
- `backend/app/services/upload_task_service.py`
- `backend/app/utils/image_process.py`
- `backend/app/utils/hash.py`

## 5. 前端代码

入口与路由：

- `frontend/src/main.js`
- `frontend/src/router/index.js`
- `frontend/src/layouts/PublicLayout.vue`
- `frontend/src/layouts/AdminLayout.vue`

前台页面：

- `frontend/src/views/Home.vue`
- `frontend/src/views/ImageDetail.vue`
- `frontend/src/views/WorkList.vue`
- `frontend/src/views/WorkDetail.vue`
- `frontend/src/views/CharacterList.vue`
- `frontend/src/views/CharacterDetail.vue`
- `frontend/src/views/TagList.vue`
- `frontend/src/views/Search.vue`
- `frontend/src/constants/ratings.js`
- `frontend/src/utils/favorites.js`
- `frontend/src/utils/views.js`

前台的图片库、作品、角色、分级四个入口现在统一使用 `frontend/public/hero/` 下的固定高清背景图，不再从业务图片缩略图中抽取背景，避免列表首屏继续出现模糊背景。

后台页面：

- `frontend/src/views/admin/Dashboard.vue`
- `frontend/src/views/admin/ImageManage.vue`
- `frontend/src/views/admin/ImageUpload.vue`
- `frontend/src/views/admin/MetadataImport.vue`
- `frontend/src/views/admin/WorkManage.vue`
- `frontend/src/views/admin/CharacterManage.vue`
- `frontend/src/views/admin/Settings.vue`
- `frontend/src/views/admin/AdminWorkDetail.vue`
- `frontend/src/views/admin/AdminCharacterDetail.vue`

后台设置页 `frontend/src/views/admin/Settings.vue` 负责展示管理员资料、后台偏好、上传队列参数和系统健康。管理员头像可以直接上传，也可以从已上传公开图片中选择；健康接口加载失败时页面会保留明确错误态与重试按钮，避免部署诊断区域空白。

## 6. 部署说明

以下示例基于 Linux 裸机，不使用 Docker。

首次部署时，如果项目根目录不存在 `installed.lock` 且目标数据库还没有有效 Alembic 版本记录，前端会自动进入 `/install` 初始化页面。安装页可选择 SQLite 或 MySQL；选择 SQLite 时数据库文件由系统固定保存到后端默认位置，选择 MySQL 时填写数据库连接。图片存储目录也由系统固定使用项目根目录下的 `storage`，首次安装页不再让用户手动选择。安装页只需要填写管理员账号密码；系统会自动生成登录签名密钥并写入 `.env`，Linux 部署下会尽量把 `.env` 权限收紧到 `0600`。提交成功后会写入 `.env`、执行数据库迁移、初始化管理员资料，并创建 `installed.lock`。这个判断方式参考 lsky-pro：安装锁文件存在即视为已安装；如需重新安装，先备份数据，再删除 `installed.lock` 并清空或更换数据库。

MySQL 首次安装已经用独立测试目录和临时 MariaDB 11.4.8 实例实测通过：安装页选择 MySQL 后会完成迁移、写入 `.env` 与 `installed.lock`，重启后端后安装状态返回 `installed=true / restart_required=false`，管理员账号可登录后台并写入 HttpOnly 会话。

### 6.1 创建目录

```bash
sudo mkdir -p /opt/anime-gallery
sudo rsync -a ./ /opt/anime-gallery/
sudo bash /opt/anime-gallery/scripts/create_linux_dirs.sh
```

### 6.2 后端虚拟环境

```bash
cd /opt/anime-gallery
sudo python3 -m venv venv
sudo /opt/anime-gallery/venv/bin/pip install -r backend/requirements.txt
sudo cp .env.example .env
sudo chown -R www-data:www-data /opt/anime-gallery/backend /opt/anime-gallery/storage /opt/anime-gallery/logs
```

### 6.3 数据库初始化

生产环境建议使用 MySQL 8.x。先创建数据库和专用账号：

```sql
CREATE DATABASE anime_gallery
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'anime_gallery'@'127.0.0.1' IDENTIFIED BY 'change-this-db-password';
GRANT ALL PRIVILEGES ON anime_gallery.* TO 'anime_gallery'@'127.0.0.1';
FLUSH PRIVILEGES;
```

然后在 `/opt/anime-gallery/.env` 中配置：

```env
AGMS_DATABASE_URL=mysql+pymysql://anime_gallery:change-this-db-password@127.0.0.1:3306/anime_gallery?charset=utf8mb4
```

本地开发仍可继续使用 SQLite：

```env
AGMS_DATABASE_URL=sqlite:////opt/anime-gallery/backend/anime_gallery.db
```

确认连接串后执行迁移：

```bash
cd /opt/anime-gallery/backend
sudo -u www-data /opt/anime-gallery/venv/bin/alembic upgrade head
```

开发环境也可以用：

```bash
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload
```

### 6.4 前端构建

```bash
cd /opt/anime-gallery/frontend
npm install
npm run build
```

开发环境：

```bash
cd frontend
npm install
npm run dev
```

### 6.5 systemd

```bash
sudo cp /opt/anime-gallery/scripts/anime-gallery.service /etc/systemd/system/anime-gallery.service
sudo systemctl daemon-reload
sudo systemctl enable --now anime-gallery
sudo systemctl status anime-gallery
```

### 6.6 Nginx

```bash
sudo cp /opt/anime-gallery/scripts/nginx-anime-gallery.conf /etc/nginx/sites-available/anime-gallery.conf
sudo ln -s /etc/nginx/sites-available/anime-gallery.conf /etc/nginx/sites-enabled/anime-gallery.conf
sudo nginx -t
sudo systemctl reload nginx
```

把 `gallery.example.com` 改成你的域名。生产环境建议加 HTTPS，并在 `/admin` 前加登录或反向代理访问控制。

如果站点套了阿里云 ESA/CDN，源站应把 ESA 注入的真实客户端 IP 显式传给后端。项目示例 Nginx 配置会优先使用 `ali-real-client-ip`，兼容 `ali-cdn-real-ip` 和 `true-client-ip`，并回退到 `$remote_addr`。生产环境还应在云防火墙或安全组限制源站直连，只允许 CDN/ESA 回源或增加回源鉴权头，避免外部请求伪造真实 IP 头。

### 6.7 环境变量

`.env.example` 里列出了主要配置项，至少应关注：

- `AGMS_ADMIN_USERNAME`
- `AGMS_ADMIN_PASSWORD`
- `AGMS_DATABASE_URL`
- `AGMS_AUTH_SECRET`
- `AGMS_AUTH_TOKEN_TTL_SECONDS`
- `AGMS_COOKIE_SECURE`
- `AGMS_LOGIN_RATE_LIMIT_WINDOW_SECONDS`
- `AGMS_LOGIN_RATE_LIMIT_MAX_ATTEMPTS`
- `AGMS_UPLOAD_WORKER_COUNT`
- `AGMS_UPLOAD_CLAIM_BATCH_SIZE`

`AGMS_AUTH_SECRET` 不是 API Key，不应该交给用户或外部程序使用。它只用于后端签发和校验后台 HttpOnly Cookie 会话；安装向导会自动生成。如果手工维护 `.env`，用下面的方式生成强随机值：

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

未配置 `AGMS_AUTH_SECRET` 时，后端会使用进程级临时随机密钥，避免继续使用固定默认密钥；这种模式只适合本地调试，重启后旧登录会话会失效。生产环境使用 HTTPS 时建议设置 `AGMS_COOKIE_SECURE=true`。部署时请替换所有占位配置。

针对 48 核 96 线程 / 128GB 内存 / NVMe 独立服务器，项目默认 `AGMS_UPLOAD_WORKER_COUNT=12`。如果上传主要是普通 SDR 图片，可以继续上调；如果 JXR/HDR/AVIF 比例很高，建议先保持 12，观察 CPU、内存和 ffmpeg 转码耗时后再调到 16 或 24。

### 6.8 HDR 转码注意事项

- 生产环境需要一份支持 `AVIF/AV1` 编码的 `ffmpeg`，但不要求其命令行直接暴露 `master_display / max_cll`；项目会在 AVIF 编码完成后自行补写 `mdcv / clli`。
- 建议在部署验收时至少用一张真实 HDR 样本回归上传链路，并检查输出原图中是否同时存在 `nclx / mdcv / clli`。
- 如果发行版自带 `ffmpeg` 缺少 `libaom-av1` 或其他可用 AV1 still-picture 编码能力，仍建议改用自编译版本或更新的静态发布版本。

### 6.9 安全注意事项

- 后台登录增加了基于来源 IP 的基础限流，默认 5 分钟窗口内最多 8 次失败尝试。
- 当前限流状态保存在后端进程内存中，适合本地和单进程部署；如果生产环境使用多进程、多实例或反向代理集群，建议改为 Redis 等共享计数器。
- 如部署在 Nginx/Caddy/ESA/CDN 等反向代理之后，需要正确传递真实客户端 IP。阿里云 ESA 场景优先使用 `ali-real-client-ip`，并限制源站直连或配置回源鉴权头，避免外部请求伪造真实 IP 头，否则基于 IP 的限流会失真。
- 如果使用 `/install` 安装向导，`AGMS_AUTH_SECRET` 会自动生成；如果手工维护 `.env`，务必修改管理员账号、密码和 `AGMS_AUTH_SECRET`。密钥长度至少 32 个字符，不能使用示例占位符；更换密钥会让旧后台会话立即失效。
- 生产环境建议只放行前台域名到 `cors_origins`，不要保留开发环境的 `localhost:5173`。

## 7. 后续可扩展方向

- 后台权限分级。
- PostgreSQL、全文搜索、元数据别名解析和自动补全。
- 收藏系统、用户图库、私有图片权限。
- 来源站点解析、AI 元数据建议。
- 图片 EXIF/ICC 处理、WebP/AVIF 生成策略、后台任务队列。
