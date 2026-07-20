import hashlib
import importlib.util
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[2]


def load_script_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_runner = load_script_module("moegallery_update_runner_test", ROOT_DIR / "scripts" / "update_runner.py")
launcher_module = load_script_module("moegallery_launcher_test", ROOT_DIR / "scripts" / "moegallery_launcher.py")


class UpdateRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="moegallery-runner-test-")
        self.root = Path(self.temp_dir.name)
        self.source_dir = self.root / "source"
        self.source_dir.mkdir()
        self.archive = self.source_dir / "MoeGallery-v9.9.9.tar.gz"
        self.archive.write_bytes(b"verified release archive")
        digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.checksums = self.source_dir / "SHA256SUMS.txt"
        self.checksums.write_text(f"{digest}  {self.archive.name}\n", encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def make_task(self, *, dry_run: bool) -> Path:
        task_dir = self.root / "storage" / "updates" / ("a" * 32)
        task_dir.mkdir(parents=True)
        now = datetime.now(UTC).isoformat()
        task = {
            "id": "a" * 32,
            "status": "queued",
            "current_version": "v1.0.0",
            "target_version": "v9.9.9",
            "archive_url": self.archive.as_uri(),
            "checksum_url": self.checksums.as_uri(),
            "archive_name": self.archive.name,
            "dry_run": dry_run,
            "progress": 0,
            "message": "queued",
            "log": [],
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
        }
        task_path = task_dir / "task.json"
        task_path.write_text(json.dumps(task), encoding="utf-8")
        return task_path

    def test_prepare_dry_run_downloads_and_finishes(self):
        task_path = self.make_task(dry_run=True)

        result = update_runner.prepare(task_path, self.root)

        task = update_runner.load_task(task_path)
        self.assertEqual(result, 0)
        self.assertEqual(task["status"], "success")
        self.assertEqual(task["progress"], 100)
        self.assertTrue((task_path.parent / "downloads" / self.archive.name).exists())

    def test_prepare_then_apply_waits_for_launcher_restart(self):
        task_path = self.make_task(dry_run=False)
        self.assertEqual(update_runner.prepare(task_path, self.root), 0)
        self.assertEqual(update_runner.load_task(task_path)["status"], "prepared")

        with patch.object(update_runner, "run_upgrade", return_value=None) as mocked_upgrade:
            result = update_runner.apply(task_path, self.root, managed_by_launcher=True)

        task = update_runner.load_task(task_path)
        self.assertEqual(result, 0)
        self.assertEqual(task["status"], "restarting")
        mocked_upgrade.assert_called_once()

    def test_atomic_task_writes_do_not_share_a_temp_file(self):
        task_path = self.make_task(dry_run=True)

        def write(index: int) -> None:
            update_runner.save_task(task_path, {"id": "a" * 32, "status": "queued", "writer": index})

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(write, range(40)))

        task = update_runner.load_task(task_path)
        self.assertIn(task["writer"], range(40))
        self.assertEqual(list(task_path.parent.glob(".task.json.*.tmp")), [])


class LauncherStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="moegallery-launcher-test-")
        self.root = Path(self.temp_dir.name)
        (self.root / "storage" / "updates").mkdir(parents=True)
        (self.root / ".env").write_text("AGMS_STORAGE_PATH=storage\n", encoding="utf-8")
        self.launcher = launcher_module.MoeGalleryLauncher(self.root, "127.0.0.1", 8111, 0.1, 1)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_launcher_discovers_queued_task(self):
        task_dir = self.root / "storage" / "updates" / ("b" * 32)
        task_dir.mkdir()
        task_path = task_dir / "task.json"
        task_path.write_text(json.dumps({"id": "b" * 32, "status": "queued"}), encoding="utf-8")

        self.assertEqual(self.launcher.next_task(), task_path)

    def test_restart_request_honors_not_before(self):
        runtime_dir = self.root / "storage" / "runtime"
        runtime_dir.mkdir()
        request_path = runtime_dir / "restart.request"
        request_path.write_text(json.dumps({"not_before": 9999999999}), encoding="utf-8")
        self.assertFalse(self.launcher.restart_requested())
        self.assertTrue(request_path.exists())

        request_path.write_text(json.dumps({"not_before": 0}), encoding="utf-8")
        self.assertTrue(self.launcher.restart_requested())
        self.assertFalse(request_path.exists())

    def test_failure_before_backup_does_not_claim_rollback_failed(self):
        task_path = self.root / "storage" / "updates" / ("c" * 32) / "task.json"
        task_path.parent.mkdir()

        restored, message = self.launcher.rollback(task_path, "release validation failed")

        self.assertTrue(restored)
        self.assertIn("原版本未被修改", message)


if __name__ == "__main__":
    unittest.main()
