import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from app.config import ROOT_DIR, settings
from app.services.release_service import current_app_version, latest_release_info, parse_semver

UPDATE_STATUS_RUNNING = {
    "queued",
    "starting",
    "downloading",
    "verifying",
    "prepared",
    "backup",
    "upgrading",
    "restarting",
}


def updates_root() -> Path:
    path = settings.storage_path / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_dir(task_id: str) -> Path:
    if not _valid_task_id(task_id):
        raise ValueError("Invalid update task id")
    return updates_root() / task_id


def task_file(task_id: str) -> Path:
    return task_dir(task_id) / "task.json"


def _valid_task_id(task_id: str) -> bool:
    return len(task_id) == 32 and all(char in "0123456789abcdef" for char in task_id)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _find_asset(release: dict, suffix: str) -> dict | None:
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        if name.endswith(suffix) and url:
            return asset
    return None


def _update_available(current_version: str, latest_version: str) -> bool:
    current = parse_semver(current_version)
    latest = parse_semver(latest_version)
    return bool(current and latest and latest > current)


def _launcher_managed() -> bool:
    if os.environ.get("AGMS_LAUNCHER_MANAGED") != "1":
        return False
    configured_app_dir = os.environ.get("AGMS_LAUNCHER_APP_DIR", "").strip()
    if not configured_app_dir:
        return True
    try:
        return Path(configured_app_dir).resolve() == ROOT_DIR.resolve()
    except OSError:
        return False


def _formal_update_platform_supported() -> bool:
    return os.name != "nt"


def update_execution_status() -> dict:
    runner = ROOT_DIR / "scripts" / "update_runner.py"
    upgrade_script = ROOT_DIR / "scripts" / "upgrade_release.sh"
    backup_script = ROOT_DIR / "scripts" / "backup_before_upgrade.sh"
    restore_script = ROOT_DIR / "scripts" / "restore_upgrade_backup.sh"
    launcher_managed = _launcher_managed()
    mode = "launcher" if launcher_managed else "local"
    issues: list[str] = []
    warnings: list[str] = []

    runner_exists = runner.exists()
    upgrade_script_exists = upgrade_script.exists()
    backup_script_exists = backup_script.exists()
    restore_script_exists = restore_script.exists()
    if not runner_exists:
        issues.append("缺少 scripts/update_runner.py")
    if not upgrade_script_exists:
        issues.append("缺少 scripts/upgrade_release.sh")
    if not backup_script_exists:
        issues.append("缺少 scripts/backup_before_upgrade.sh")
    if not restore_script_exists:
        issues.append("缺少 scripts/restore_upgrade_backup.sh")
    if not launcher_managed:
        warnings.append("当前未通过 MoeGallery 启动器运行，只支持下载校验")
    if not _formal_update_platform_supported():
        warnings.append("当前是 Windows 环境，只支持下载校验，不支持正式替换运行中的服务")

    dry_run_available = runner_exists
    production_ready = bool(
        _formal_update_platform_supported()
        and launcher_managed
        and runner_exists
        and upgrade_script_exists
        and backup_script_exists
        and restore_script_exists
    )
    local_upgrade_available = production_ready
    available = production_ready
    if production_ready:
        message = "内置更新已就绪"
        severity = "ok"
    elif dry_run_available:
        message = "当前启动方式只支持下载校验"
        severity = "warning"
    else:
        message = "更新执行器不可用"
        severity = "danger"

    return {
        "mode": mode,
        "available": available,
        "dry_run_available": dry_run_available,
        "production_ready": production_ready,
        "local_upgrade_available": local_upgrade_available,
        "runner_exists": runner_exists,
        "upgrade_script_exists": upgrade_script_exists,
        "backup_script_exists": backup_script_exists,
        "restore_script_exists": restore_script_exists,
        "launcher_managed": launcher_managed,
        "os": os.name,
        "severity": severity,
        "message": message,
        "issues": issues,
        "warnings": warnings,
    }


def check_for_updates(db: Session) -> dict:
    current_version = current_app_version()
    latest_release = latest_release_info(db)
    status = update_execution_status()
    return {
        "current_version": current_version,
        "latest_release": latest_release,
        "update_available": _update_available(
            current_version,
            latest_release.get("version") if latest_release.get("available") else "",
        ),
        "update_execution_available": status["available"],
        "update_execution_mode": status["mode"],
        "update_execution_status": status,
    }


def read_task(task_id: str) -> dict:
    path = task_file(task_id)
    if not path.exists():
        raise FileNotFoundError(task_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_tasks(limit: int = 20) -> list[dict]:
    items: list[dict] = []
    root = updates_root()
    for path in root.glob("*/task.json"):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[:limit]


def running_task() -> dict | None:
    for task in list_tasks(limit=50):
        if task.get("status") in UPDATE_STATUS_RUNNING:
            return task
    return None


def _write_task(task: dict) -> None:
    directory = task_dir(task["id"])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "task.json"
    task["updated_at"] = _utc_now()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(json.dumps(task, ensure_ascii=False, indent=2) + "\n")
            output.flush()
            os.fsync(output.fileno())
        for attempt in range(10):
            try:
                os.replace(temp_name, path)
                break
            except PermissionError:
                if attempt == 9:
                    raise
                time.sleep(0.01 * (attempt + 1))
    finally:
        try:
            Path(temp_name).unlink()
        except FileNotFoundError:
            pass


def _new_task(
    *,
    current_version: str,
    release: dict,
    archive_asset: dict,
    checksum_asset: dict,
    dry_run: bool,
) -> dict:
    task_id = uuid4().hex
    now = _utc_now()
    archive_name = str(archive_asset.get("name") or Path(str(archive_asset.get("browser_download_url"))).name)
    return {
        "id": task_id,
        "status": "queued",
        "current_version": current_version,
        "target_version": release.get("version") or "",
        "release_url": release.get("url") or "",
        "archive_url": archive_asset.get("browser_download_url") or "",
        "checksum_url": checksum_asset.get("browser_download_url") or "",
        "archive_name": archive_name,
        "app_dir": str(ROOT_DIR),
        "dry_run": dry_run,
        "progress": 0,
        "message": "等待更新任务启动",
        "log": ["更新任务已创建"],
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
    }


def create_update_task(db: Session, version: str | None = None, dry_run: bool = False, force: bool = False) -> dict:
    if running_task():
        raise ValueError("已有更新任务正在执行")
    status = update_execution_status()
    if dry_run and not status["dry_run_available"]:
        raise ValueError("更新下载校验不可用：缺少 scripts/update_runner.py")
    if not dry_run and not status["available"]:
        problems = status["issues"] or status["warnings"] or [status["message"]]
        raise ValueError("正式更新未就绪：" + "；".join(problems))
    current_version = current_app_version()
    release = latest_release_info(db)
    if not release.get("available"):
        raise ValueError("无法获取最新 Release")
    if version and version != release.get("version"):
        raise ValueError("当前仅支持更新到最新 Release")
    target_version = str(release.get("version") or "")
    if not target_version:
        raise ValueError("最新 Release 缺少版本号")
    if not force and not _update_available(current_version, target_version):
        raise ValueError("当前已经是最新版本")
    archive_asset = _find_asset(release, ".tar.gz")
    checksum_asset = _find_asset(release, "SHA256SUMS.txt")
    if not archive_asset:
        raise ValueError("最新 Release 缺少 .tar.gz 更新包")
    if not checksum_asset:
        raise ValueError("最新 Release 缺少 SHA256SUMS.txt")
    task = _new_task(
        current_version=current_version,
        release=release,
        archive_asset=archive_asset,
        checksum_asset=checksum_asset,
        dry_run=dry_run,
    )
    _write_task(task)
    try:
        trigger_update_task(task["id"])
    except Exception as exc:
        task["status"] = "failed"
        task["message"] = f"启动更新任务失败：{exc}"
        task["finished_at"] = _utc_now()
        task.setdefault("log", []).append(task["message"])
        _write_task(task)
        raise
    return read_task(task["id"])


def trigger_update_task(task_id: str) -> None:
    path = task_file(task_id)
    if _launcher_managed():
        # The stable launcher polls queued task files and keeps the web process
        # alive during download and checksum verification.
        return
    task = read_task(task_id)
    if not task.get("dry_run"):
        raise RuntimeError("正式更新需要通过 MoeGallery 启动器运行")
    runner = ROOT_DIR / "scripts" / "update_runner.py"
    if not runner.exists():
        raise FileNotFoundError("scripts/update_runner.py")
    command = [
        sys.executable,
        str(runner),
        "--app-dir",
        str(ROOT_DIR),
        "--task-id",
        task_id,
        "--task-file",
        str(path),
    ]
    kwargs: dict = {
        "cwd": str(ROOT_DIR),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)
