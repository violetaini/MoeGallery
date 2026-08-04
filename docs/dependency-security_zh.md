# 依赖安全维护

MoeGallery 的安装、更新和 CI 都使用精确版本与文件哈希，避免同一发布包在不同时间安装出不同的依赖集合。

## 文件职责

- `backend/requirements.in`：后端直接依赖，由维护者修改。
- `backend/requirements.lock.txt`：运行环境的完整跨平台依赖锁，包含间接依赖和 SHA-256 哈希。
- `backend/requirements-test.in`：测试环境新增的直接依赖。
- `backend/requirements-test.lock.txt`：测试环境完整依赖锁。
- `backend/requirements.txt` 与 `backend/requirements-test.txt`：兼容旧部署脚本的入口，同样强制使用哈希锁。
- `frontend/package.json`：前端直接依赖使用精确版本，不使用版本范围。
- `frontend/package-lock.json`：前端完整依赖树。

不要手工修改锁文件中的版本或哈希。

## 更新后端依赖

锁文件固定由 `uv 0.12.0` 生成，并以 Python 3.12 为解析基线：

```bash
python3 -m venv .venv-lock
.venv-lock/bin/python -m pip install "uv==0.12.0"
cd backend
../.venv-lock/bin/uv pip compile --universal --python-version 3.12 --generate-hashes --output-file requirements.lock.txt requirements.in
../.venv-lock/bin/uv pip compile --universal --python-version 3.12 --generate-hashes --output-file requirements-test.lock.txt requirements-test.in
```

Windows 下把 `.venv-lock/bin` 换成 `.venv-lock/Scripts`。

## 更新前端依赖

使用明确版本更新 `package.json` 和锁文件，不执行带 `--force` 的自动升级：

```bash
cd frontend
npm install --save-exact 包名@明确版本
npm install --save-dev --save-exact 开发包名@明确版本
```

## 合并前检查

```bash
python -m pip install "pip==26.2" "pip-audit==2.10.1"
python -m pip install --require-hashes -r backend/requirements-test.lock.txt
python -m pip_audit --strict --require-hashes --disable-pip -r backend/requirements.lock.txt
cd frontend
npm ci
npm audit --audit-level=high
npm run build
```

GitHub Actions 会在依赖文件变更、每周定时任务和正式发布时重复执行审计。Dependabot 每周检查 Python、npm 和 GitHub Actions 更新。

## 紧急安全升级

1. 从漏洞公告确认受影响版本、修复版本和实际影响范围，不以跳过审计代替修复。
2. 只升级解决漏洞所需的最小版本范围；主版本升级单独评估兼容性。
3. 重新生成锁文件并运行后端完整测试、前端构建、依赖审计和发布包校验。
4. 发布补丁版本，通过更新中心部署；确认健康检查、数据库迁移状态和主要上传、浏览流程正常。
5. 若暂时无法升级，必须记录漏洞编号、临时缓解措施、负责人和到期日期。不得永久加入无说明的忽略项。
