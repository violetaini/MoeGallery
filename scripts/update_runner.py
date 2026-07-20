#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


RUNNING_LOG_LIMIT = 400


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_env_value(app_dir: Path, key: str) -> str | None:
    env_path = app_dir / ".env"
    if not env_path.exists():
        return None
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        env_key, value = line.split("=", 1)
        if env_key.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def resolve_task_file(app_dir: Path, task_id: str, explicit_task_file: str | None) -> Path:
    if explicit_task_file:
        return Path(explicit_task_file).resolve()
    storage_path = os.environ.get("AGMS_STORAGE_PATH") or read_env_value(app_dir, "AGMS_STORAGE_PATH")
    storage_root = Path(storage_path).expanduser() if storage_path else app_dir / "storage"
    if not storage_root.is_absolute():
        storage_root = app_dir / storage_root
    return storage_root / "updates" / task_id / "task.json"


def load_task(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_task(path: Path, task: dict) -> None:
    task["updated_at"] = utc_now()
    path.parent.mkdir(parents=True, exist_ok=True)
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


def append_log(path: Path, task: dict, message: str) -> None:
    task.setdefault("log", []).append(f"{utc_now()} {message}")
    task["log"] = task["log"][-RUNNING_LOG_LIMIT:]
    save_task(path, task)


def set_status(path: Path, task: dict, status: str, progress: int, message: str) -> None:
    task["status"] = status
    task["progress"] = max(0, min(100, progress))
    task["message"] = message
    if status == "starting" and not task.get("started_at"):
        task["started_at"] = utc_now()
    if status in {"success", "failed"}:
        task["finished_at"] = utc_now()
    append_log(path, task, message)


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "" and Path(url).exists():
        target.write_bytes(Path(url).read_bytes())
        return
    request = urllib.request.Request(url, headers={"User-Agent": "MoeGallery-updater"})
    with urllib.request.urlopen(request, timeout=120) as response, target.open("wb") as output:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_sha256(checksum_file: Path, archive_name: str) -> str:
    for raw_line in checksum_file.read_text(encoding="utf-8").splitlines():
        parts = raw_line.strip().split()
        if len(parts) >= 2 and parts[1].lstrip("*") == archive_name:
            return parts[0].lower()
    raise RuntimeError(f"SHA256SUMS.txt does not contain {archive_name}")


def verify_checksum(archive_path: Path, checksum_path: Path, archive_name: str) -> None:
    expected = expected_sha256(checksum_path, archive_name)
    actual = sha256_file(archive_path)
    if actual.lower() != expected:
        raise RuntimeError(f"SHA256 mismatch for {archive_name}: expected {expected}, got {actual}")


def run_upgrade(
    app_dir: Path,
    task_path: Path,
    task: dict,
    archive_path: Path,
    *,
    managed_by_launcher: bool,
) -> None:
    if os.name == "nt":
        raise RuntimeError("Windows local preview only supports dry-run verification; run production upgrades on Linux")
    upgrade_script = app_dir / "scripts" / "upgrade_release.sh"
    if not upgrade_script.exists():
        raise RuntimeError(f"upgrade_release.sh not found: {upgrade_script}")
    command = [
        "bash",
        str(upgrade_script),
        "--app-dir",
        str(app_dir),
    ]
    if managed_by_launcher:
        command.extend(
            [
                "--no-service-control",
                "--result-file",
                str(task_path.parent / "upgrade-result.json"),
            ]
        )
    else:
        command.extend(
            [
                "--service",
                str(task.get("service_name") or "moegallery"),
                "--health-url",
                str(task.get("health_url") or "http://127.0.0.1:8111/api/health"),
            ]
        )
    command.append(str(archive_path))
    append_log(task_path, task, "执行升级脚本")
    process = subprocess.Popen(
        command,
        cwd=app_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert process.stdout is not None
    for line in process.stdout:
        append_log(task_path, task, line.rstrip())
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"upgrade_release.sh exited with code {return_code}")


def prepared_files(task_path: Path, task: dict) -> tuple[Path, Path]:
    work_dir = task_path.parent / "downloads"
    archive_name = task.get("archive_name") or Path(urllib.parse.urlparse(task["archive_url"]).path).name
    return work_dir / archive_name, work_dir / "SHA256SUMS.txt"


def prepare(task_path: Path, app_dir: Path) -> int:
    task = load_task(task_path)
    try:
        set_status(task_path, task, "starting", 5, "更新任务启动")
        archive_path, checksum_path = prepared_files(task_path, task)
        archive_name = archive_path.name

        set_status(task_path, task, "downloading", 20, "下载更新包")
        download(task["archive_url"], archive_path)
        set_status(task_path, task, "downloading", 35, "下载校验文件")
        download(task["checksum_url"], checksum_path)

        set_status(task_path, task, "verifying", 55, "校验 SHA256")
        verify_checksum(archive_path, checksum_path, archive_name)

        if task.get("dry_run"):
            set_status(task_path, task, "success", 100, "下载和校验完成，未执行安装")
            return 0

        set_status(task_path, task, "prepared", 60, "更新包已校验，等待内置启动器安装")
        return 0
    except Exception as exc:  # noqa: BLE001 - updater must persist failures for the panel.
        set_status(task_path, task, "failed", int(task.get("progress") or 0), f"更新失败：{exc}")
        return 1


def apply(task_path: Path, app_dir: Path, *, managed_by_launcher: bool) -> int:
    task = load_task(task_path)
    try:
        archive_path, checksum_path = prepared_files(task_path, task)
        if not archive_path.exists() or not checksum_path.exists():
            raise RuntimeError("已校验的更新包不存在，请重新创建更新任务")
        verify_checksum(checksum_path=checksum_path, archive_path=archive_path, archive_name=archive_path.name)
        set_status(task_path, task, "upgrading", 75, "开始安装更新")
        run_upgrade(
            app_dir,
            task_path,
            task,
            archive_path,
            managed_by_launcher=managed_by_launcher,
        )
        if managed_by_launcher:
            set_status(task_path, task, "restarting", 92, "程序文件已更新，正在重新启动服务")
        else:
            set_status(task_path, task, "success", 100, "更新完成")
        return 0
    except Exception as exc:  # noqa: BLE001 - update errors must be visible after restart.
        set_status(task_path, task, "failed", int(task.get("progress") or 0), f"更新失败：{exc}")
        return 1


def run(task_path: Path, app_dir: Path, phase: str) -> int:
    if phase == "prepare":
        return prepare(task_path, app_dir)
    if phase == "apply":
        return apply(task_path, app_dir, managed_by_launcher=True)
    result = prepare(task_path, app_dir)
    task = load_task(task_path)
    if result != 0 or task.get("dry_run") or task.get("status") == "failed":
        return result
    return apply(task_path, app_dir, managed_by_launcher=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a MoeGallery update task.")
    parser.add_argument("--app-dir", default="/opt/moegallery")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-file", default="")
    parser.add_argument("--phase", choices=["prepare", "apply", "all"], default="all")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    task_path = resolve_task_file(app_dir, args.task_id, args.task_file or None)
    return run(task_path, app_dir, args.phase)


if __name__ == "__main__":
    raise SystemExit(main())
