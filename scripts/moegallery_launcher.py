#!/usr/bin/env python3
"""Run MoeGallery and coordinate in-panel updates without a second service."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path


RUNNING_TASK_STATUSES = {
    "queued",
    "starting",
    "downloading",
    "verifying",
    "prepared",
    "upgrading",
    "restarting",
}
LOG_LIMIT = 400


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            if value[0] == '"':
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = value[1:-1]
            else:
                value = value[1:-1]
        values[key.strip()] = value
    return values


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


def set_task_status(path: Path, status: str, progress: int, message: str) -> None:
    task = load_task(path)
    task["status"] = status
    task["progress"] = max(0, min(100, progress))
    task["message"] = message
    task.setdefault("log", []).append(f"{utc_now()} {message}")
    task["log"] = task["log"][-LOG_LIMIT:]
    if status in {"success", "failed"}:
        task["finished_at"] = utc_now()
    save_task(path, task)


class MoeGalleryLauncher:
    def __init__(self, app_dir: Path, host: str, port: int, poll_interval: float, health_timeout: int):
        self.app_dir = app_dir.resolve()
        self.host = host
        self.port = port
        self.poll_interval = poll_interval
        self.health_timeout = health_timeout
        self.web_process: subprocess.Popen | None = None
        self.stopping = False
        self.instance_lock = None

    @property
    def env_path(self) -> Path:
        return self.app_dir / ".env"

    @property
    def python_bin(self) -> Path:
        return self.app_dir / "venv" / "bin" / "python"

    @property
    def health_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/api/health"

    def child_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment.update(read_env_file(self.env_path))
        environment["AGMS_LAUNCHER_MANAGED"] = "1"
        environment["AGMS_LAUNCHER_APP_DIR"] = str(self.app_dir)
        return environment

    def storage_root(self) -> Path:
        configured = read_env_file(self.env_path).get("AGMS_STORAGE_PATH") or os.environ.get("AGMS_STORAGE_PATH")
        storage = Path(configured).expanduser() if configured else self.app_dir / "storage"
        if not storage.is_absolute():
            storage = self.app_dir / storage
        return storage.resolve()

    def acquire_instance_lock(self) -> bool:
        if os.name != "posix":
            return True
        import fcntl

        inherited_fd = os.environ.get("AGMS_LAUNCHER_LOCK_FD")
        if inherited_fd:
            try:
                fd = int(inherited_fd)
                os.fstat(fd)
                self.instance_lock = os.fdopen(fd, "a+", encoding="utf-8")
                return True
            except (OSError, TypeError, ValueError):
                os.environ.pop("AGMS_LAUNCHER_LOCK_FD", None)

        runtime_dir = self.storage_root() / "runtime"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        lock = (runtime_dir / "launcher.lock").open("a+", encoding="utf-8")
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            return False
        lock.seek(0)
        lock.truncate()
        json.dump({"pid": os.getpid(), "app_dir": str(self.app_dir), "started_at": utc_now()}, lock)
        lock.write("\n")
        lock.flush()
        os.fsync(lock.fileno())
        os.set_inheritable(lock.fileno(), True)
        os.environ["AGMS_LAUNCHER_LOCK_FD"] = str(lock.fileno())
        self.instance_lock = lock
        return True

    def release_instance_lock(self) -> None:
        lock = self.instance_lock
        self.instance_lock = None
        os.environ.pop("AGMS_LAUNCHER_LOCK_FD", None)
        if lock is None:
            return
        if os.name == "posix":
            import fcntl

            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock.close()

    def start_web(self) -> None:
        if self.stopping or (self.web_process and self.web_process.poll() is None):
            return
        command = [
            str(self.python_bin),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        print(f"[launcher] starting MoeGallery on {self.host}:{self.port}", flush=True)
        self.web_process = subprocess.Popen(
            command,
            cwd=self.app_dir / "backend",
            env=self.child_environment(),
        )

    def stop_web(self, timeout: int = 30) -> None:
        process = self.web_process
        if not process or process.poll() is not None:
            self.web_process = None
            return
        print("[launcher] stopping web process", flush=True)
        process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        self.web_process = None

    def wait_for_health(self) -> bool:
        deadline = time.monotonic() + self.health_timeout
        while time.monotonic() < deadline and not self.stopping:
            process = self.web_process
            if process and process.poll() is not None:
                return False
            try:
                with urllib.request.urlopen(self.health_url, timeout=3) as response:
                    if response.status == 200:
                        return True
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(1)
        return False

    def task_paths(self) -> list[Path]:
        updates_dir = self.storage_root() / "updates"
        if not updates_dir.exists():
            return []
        paths = list(updates_dir.glob("*/task.json"))
        paths.sort(key=lambda path: path.stat().st_mtime)
        return paths

    def next_task(self) -> Path | None:
        for path in self.task_paths():
            try:
                if load_task(path).get("status") in RUNNING_TASK_STATUSES:
                    return path
            except (OSError, json.JSONDecodeError):
                continue
        return None

    def run_task_phase(self, task_path: Path, phase: str) -> int:
        task = load_task(task_path)
        runner = self.app_dir / "scripts" / "update_runner.py"
        command = [
            str(self.python_bin),
            str(runner),
            "--app-dir",
            str(self.app_dir),
            "--task-id",
            str(task["id"]),
            "--task-file",
            str(task_path),
            "--phase",
            phase,
        ]
        return subprocess.run(command, cwd=self.app_dir, check=False).returncode

    def preserve_restore_script(self, task_path: Path) -> Path:
        source = self.app_dir / "scripts" / "restore_upgrade_backup.sh"
        target = task_path.parent / "restore_upgrade_backup.sh"
        shutil.copy2(source, target)
        target.chmod(0o700)
        return target

    def rollback(self, task_path: Path, reason: str) -> tuple[bool, str]:
        result_path = task_path.parent / "upgrade-result.json"
        restore_script = task_path.parent / "restore_upgrade_backup.sh"
        if not result_path.exists():
            return True, f"{reason}；安装在替换程序前中止，原版本未被修改"
        if not restore_script.exists():
            return False, f"{reason}；缺少恢复脚本，无法自动使用升级备份"
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
            backup_dir = str(result.get("backup_dir") or "")
        except (OSError, json.JSONDecodeError):
            backup_dir = ""
        if not backup_dir:
            return False, f"{reason}；升级备份路径无效"
        command = [
            "bash",
            str(restore_script),
            "--app-dir",
            str(self.app_dir),
            "--backup-dir",
            backup_dir,
            "--python-bin",
            str(self.python_bin),
        ]
        print(f"[launcher] update failed, restoring {backup_dir}", flush=True)
        return_code = subprocess.run(command, cwd=self.app_dir, check=False).returncode
        if return_code == 0:
            return True, f"{reason}；已自动恢复更新前版本"
        return False, f"{reason}；自动恢复失败，请使用备份 {backup_dir} 手动恢复"

    def finish_restart(self, task_path: Path) -> None:
        self.start_web()
        if self.wait_for_health():
            set_task_status(task_path, "success", 100, "更新完成，服务健康检查通过")
            return
        self.stop_web()
        rolled_back, message = self.rollback(task_path, "新版本健康检查失败")
        self.start_web()
        rollback_healthy = self.wait_for_health()
        if rolled_back and not rollback_healthy:
            message += "；旧版本恢复后健康检查仍未通过"
        set_task_status(task_path, "failed", 95, message)

    def reload_self(self) -> None:
        launcher = self.app_dir / "scripts" / "moegallery_launcher.py"
        arguments = [
            str(self.python_bin),
            str(launcher),
            "--app-dir",
            str(self.app_dir),
            "--host",
            self.host,
            "--port",
            str(self.port),
            "--poll-interval",
            str(self.poll_interval),
            "--health-timeout",
            str(self.health_timeout),
        ]
        print("[launcher] loading the updated launcher", flush=True)
        os.execv(str(self.python_bin), arguments)

    def process_task(self, task_path: Path) -> None:
        task = load_task(task_path)
        status = str(task.get("status") or "")
        if status in {"queued", "starting", "downloading", "verifying"}:
            self.run_task_phase(task_path, "prepare")
            task = load_task(task_path)
            status = str(task.get("status") or "")
        if status in {"success", "failed"}:
            return
        if status == "prepared":
            try:
                self.preserve_restore_script(task_path)
            except OSError as exc:
                set_task_status(task_path, "failed", 60, f"无法准备恢复脚本：{exc}")
                return
            self.stop_web()
            return_code = self.run_task_phase(task_path, "apply")
            task = load_task(task_path)
            if return_code != 0 or task.get("status") == "failed":
                rolled_back, message = self.rollback(task_path, str(task.get("message") or "更新安装失败"))
                self.start_web()
                rollback_healthy = self.wait_for_health()
                if rolled_back and not rollback_healthy:
                    message += "；旧版本恢复后健康检查仍未通过"
                set_task_status(task_path, "failed", int(task.get("progress") or 0), message)
                return
            try:
                self.reload_self()
            except OSError as exc:
                print(f"[launcher] could not reload launcher: {exc}", file=sys.stderr, flush=True)
                self.finish_restart(task_path)
            return
        if status == "restarting":
            self.finish_restart(task_path)
            return
        if status == "upgrading":
            self.stop_web()
            rolled_back, message = self.rollback(task_path, "检测到被中断的更新任务")
            self.start_web()
            if rolled_back:
                self.wait_for_health()
            set_task_status(task_path, "failed", int(task.get("progress") or 0), message)

    def restart_requested(self) -> bool:
        request_path = self.storage_root() / "runtime" / "restart.request"
        if not request_path.exists():
            return False
        try:
            request = json.loads(request_path.read_text(encoding="utf-8"))
            if float(request.get("not_before") or 0) > time.time():
                return False
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        try:
            request_path.unlink()
        except OSError:
            return False
        return True

    def run(self) -> int:
        if not self.acquire_instance_lock():
            print(f"[launcher] another launcher already manages {self.app_dir}", file=sys.stderr, flush=True)
            return 1
        try:
            self.start_web()
            while not self.stopping:
                task_path = self.next_task()
                if task_path:
                    try:
                        self.process_task(task_path)
                    except Exception as exc:  # noqa: BLE001 - launcher must keep the web service recoverable.
                        print(f"[launcher] update task crashed: {exc}", file=sys.stderr, flush=True)
                        try:
                            set_task_status(task_path, "failed", 0, f"内置更新任务异常：{exc}")
                        except Exception:
                            pass
                        self.start_web()
                    continue
                if self.restart_requested():
                    print("[launcher] application restart requested", flush=True)
                    self.stop_web()
                    self.start_web()
                    self.wait_for_health()
                    continue
                if self.web_process and self.web_process.poll() is not None:
                    return_code = self.web_process.returncode
                    print(f"[launcher] web process exited with code {return_code}; restarting", file=sys.stderr, flush=True)
                    self.web_process = None
                    time.sleep(2)
                    self.start_web()
                time.sleep(self.poll_interval)
            return 0
        finally:
            self.stop_web()
            self.release_instance_lock()

    def stop(self, _signum=None, _frame=None) -> None:
        self.stopping = True


def main() -> int:
    parser = argparse.ArgumentParser(description="Run MoeGallery with its built-in update coordinator.")
    parser.add_argument("--app-dir", default="/opt/moegallery")
    parser.add_argument("--host", choices=["127.0.0.1", "0.0.0.0"], default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8111)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--health-timeout", type=int, default=90)
    args = parser.parse_args()

    app_dir = Path(args.app_dir)
    launcher = MoeGalleryLauncher(app_dir, args.host, args.port, args.poll_interval, args.health_timeout)
    signal.signal(signal.SIGTERM, launcher.stop)
    signal.signal(signal.SIGINT, launcher.stop)
    return launcher.run()


if __name__ == "__main__":
    raise SystemExit(main())
