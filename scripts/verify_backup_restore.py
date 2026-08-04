#!/usr/bin/env python3
"""Exercise the backup and restore scripts against an isolated disposable app tree."""

from __future__ import annotations

import argparse
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy.engine import make_url


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT_DIR / "scripts" / "backup_gallery.sh"
RESTORE_SCRIPT = ROOT_DIR / "scripts" / "restore_upgrade_backup.sh"
PROBE_TABLE = "moegallery_backup_rehearsal_probe"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default="",
        help="Optional MySQL/MariaDB URL. Without it, an isolated SQLite database is used.",
    )
    parser.add_argument(
        "--allow-mysql",
        action="store_true",
        help="Allow the destructive restore rehearsal against a dedicated MySQL test database.",
    )
    parser.add_argument("--python-bin", default=sys.executable, help="Python used by backup and restore scripts.")
    parser.add_argument("--shell", default="bash", help="Bash executable used to run shell scripts.")
    return parser.parse_args()


def host_path(raw_path: str) -> Path:
    if os.name == "nt" and raw_path.startswith("/tmp/"):
        return Path(tempfile.gettempdir()) / raw_path.removeprefix("/tmp/")
    if os.name == "nt" and len(raw_path) >= 3 and raw_path[0] == "/" and raw_path[2] == "/":
        drive = raw_path[1]
        if drive.isalpha():
            return Path(f"{drive.upper()}:/{raw_path[3:]}")
    return Path(raw_path)


def run(
    command: list[str], *, capture_output: bool = False, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, text=True, capture_output=capture_output, env=env)
    if result.returncode == 0:
        return result
    details = []
    if capture_output and result.stdout:
        details.append(result.stdout.strip())
    if capture_output and result.stderr:
        details.append(result.stderr.strip())
    detail_text = "\n".join(details)
    suffix = f"\n{detail_text}" if detail_text else ""
    raise RuntimeError(f"Command failed with exit code {result.returncode}: {' '.join(command)}{suffix}")


def write_app_tree(app_dir: Path, database_url: str) -> None:
    for relative_path in (
        "backend",
        "frontend",
        "scripts",
        "docs",
        "storage/original",
        "storage/preview",
        "storage/thumbnail",
    ):
        (app_dir / relative_path).mkdir(parents=True, exist_ok=True)

    (app_dir / ".env").write_text(
        "\n".join(
            (
                f"AGMS_DATABASE_URL={database_url}",
                "AGMS_AUTH_SECRET=backup-rehearsal-secret-with-at-least-thirty-two-characters",
                "",
            )
        ),
        encoding="utf-8",
    )
    (app_dir / "installed.lock").write_text('{"state":"completed"}\n', encoding="utf-8")
    (app_dir / "VERSION").write_text("backup-rehearsal\n", encoding="utf-8")
    (app_dir / "backend" / "rehearsal.txt").write_text("before\n", encoding="utf-8")
    (app_dir / "frontend" / "rehearsal.txt").write_text("before\n", encoding="utf-8")
    (app_dir / "scripts" / "rehearsal.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (app_dir / "docs" / "rehearsal.md").write_text("before\n", encoding="utf-8")
    for directory in ("original", "preview", "thumbnail"):
        (app_dir / "storage" / directory / "rehearsal.webp").write_bytes(f"before-{directory}".encode("ascii"))


def prepare_sqlite(app_dir: Path) -> str:
    database_path = app_dir / "backend" / "rehearsal.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"CREATE TABLE {PROBE_TABLE} (value TEXT NOT NULL)")
        connection.execute(f"INSERT INTO {PROBE_TABLE} (value) VALUES ('before')")
    return f"sqlite:///{database_path.as_posix()}"


def mysql_connection(database_url: str):
    import pymysql

    url = make_url(database_url)
    if url.get_backend_name() not in {"mysql", "mariadb"}:
        raise ValueError("--database-url must use mysql or mariadb")
    database = str(url.database or "")
    if not database or not any(marker in database.lower() for marker in ("test", "ci", "e2e")):
        raise ValueError("MySQL restore rehearsal requires a dedicated database whose name includes test, ci, or e2e")
    return pymysql.connect(
        host=url.host or "127.0.0.1",
        port=int(url.port or 3306),
        user=url.username or "",
        password=url.password or "",
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


def prepare_mysql(database_url: str) -> None:
    with mysql_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP TABLE IF EXISTS `{PROBE_TABLE}`")
            cursor.execute(f"CREATE TABLE `{PROBE_TABLE}` (value_text VARCHAR(32) NOT NULL)")
            cursor.execute(f"INSERT INTO `{PROBE_TABLE}` (value_text) VALUES ('before')")


def mutate_sqlite(database_url: str) -> None:
    database_path = Path(database_url.removeprefix("sqlite:///"))
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"UPDATE {PROBE_TABLE} SET value = 'after'")


def mutate_mysql(database_url: str) -> None:
    with mysql_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"UPDATE `{PROBE_TABLE}` SET value_text = 'after'")


def assert_sqlite_restored(database_url: str) -> None:
    database_path = Path(database_url.removeprefix("sqlite:///"))
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(f"SELECT value FROM {PROBE_TABLE}").fetchone()
    value = row[0] if row else None
    if value != "before":
        raise AssertionError(f"SQLite probe was not restored: {value!r}")


def assert_mysql_restored(database_url: str) -> None:
    with mysql_connection(database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT value_text FROM `{PROBE_TABLE}`")
            row = cursor.fetchone()
    if not row or row[0] != "before":
        raise AssertionError(f"MySQL probe was not restored: {row!r}")


def backup(app_dir: Path, backup_root: Path, python_bin: str, shell: str) -> Path:
    environment = os.environ.copy()
    environment["PYTHON_BIN"] = python_bin
    result = run(
        [
            shell,
            str(BACKUP_SCRIPT),
            "--app-dir",
            str(app_dir),
            "--backup-root",
            str(backup_root),
            "--env-file",
            str(app_dir / ".env"),
            "--keep-days",
            "14",
        ],
        capture_output=True,
        env=environment,
    )
    output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not output_lines:
        raise AssertionError("Backup script did not report a backup directory")
    backup_root_resolved = backup_root.resolve()
    backup_dir = None
    for output_line in reversed(output_lines):
        candidate = host_path(output_line).resolve()
        if candidate.is_dir() and backup_root_resolved in candidate.parents:
            backup_dir = candidate
            break
    if backup_dir is None:
        raise AssertionError(
            "Backup script returned an unsafe or missing backup directory: "
            f"backup_root={backup_root_resolved}, output={output_lines!r}"
        )
    if backup_dir.parent.name != "scheduled":
        raise AssertionError("Scheduled backup was not written below the dedicated scheduled directory")
    required_files = ("app-files.tar.gz", "storage-files.tar.gz", "database-backup.json")
    missing = [name for name in required_files if not (backup_dir / name).is_file()]
    if missing:
        raise AssertionError(f"Backup is missing required files: {', '.join(missing)}")
    return backup_dir


def mutate_app_tree(app_dir: Path) -> None:
    (app_dir / "backend" / "rehearsal.txt").write_text("after\n", encoding="utf-8")
    (app_dir / "backend" / "after-backup.txt").write_text("remove-me\n", encoding="utf-8")
    for directory in ("original", "preview", "thumbnail"):
        (app_dir / "storage" / directory / "rehearsal.webp").write_bytes(f"after-{directory}".encode("ascii"))


def assert_app_tree_restored(app_dir: Path) -> None:
    if (app_dir / "backend" / "rehearsal.txt").read_text(encoding="utf-8") != "before\n":
        raise AssertionError("Application files were not restored")
    if (app_dir / "backend" / "after-backup.txt").exists():
        raise AssertionError("Application files created after the backup were not removed")
    for directory in ("original", "preview", "thumbnail"):
        value = (app_dir / "storage" / directory / "rehearsal.webp").read_bytes()
        if value != f"before-{directory}".encode("ascii"):
            raise AssertionError(f"Storage directory {directory} was not restored")


def main() -> int:
    args = parse_args()
    database_url = args.database_url.strip()
    use_mysql = bool(database_url)
    if use_mysql and not args.allow_mysql:
        raise SystemExit("Pass --allow-mysql only for a dedicated disposable MySQL test database")

    with tempfile.TemporaryDirectory(prefix="moegallery-backup-rehearsal-", ignore_cleanup_errors=True) as temporary_directory:
        temporary_root = Path(temporary_directory)
        app_dir = temporary_root / "app"
        if use_mysql:
            write_app_tree(app_dir, database_url)
            prepare_mysql(database_url)
        else:
            (app_dir / "backend").mkdir(parents=True, exist_ok=True)
            database_url = prepare_sqlite(app_dir)
            write_app_tree(app_dir, database_url)

        expired_backup = temporary_root / "backups" / "scheduled" / "upgrade-20000101-000000"
        expired_backup.mkdir(parents=True, exist_ok=True)
        old_timestamp = time.time() - 20 * 24 * 60 * 60
        os.utime(expired_backup, (old_timestamp, old_timestamp))
        backup_dir = backup(app_dir, temporary_root / "backups", args.python_bin, args.shell)
        if expired_backup.exists():
            raise AssertionError("Expired scheduled backup was not pruned")
        mutate_app_tree(app_dir)
        if use_mysql:
            mutate_mysql(database_url)
        else:
            mutate_sqlite(database_url)

        run(
            [
                args.shell,
                str(RESTORE_SCRIPT),
                "--app-dir",
                str(app_dir),
                "--backup-dir",
                str(backup_dir),
                "--python-bin",
                args.python_bin,
            ]
        )
        assert_app_tree_restored(app_dir)
        if use_mysql:
            assert_mysql_restored(database_url)
            print("MySQL backup and restore rehearsal passed")
        else:
            assert_sqlite_restored(database_url)
            print("SQLite backup and restore rehearsal passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
