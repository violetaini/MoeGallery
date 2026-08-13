import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.storage_stats_service import (
    directory_stats,
    invalidate_storage_stats_cache,
    media_storage_stats,
)


class StorageStatsCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-storage-stats-test-")
        self.storage_path = Path(self.temp_dir.name) / "storage"
        invalidate_storage_stats_cache()

    def tearDown(self):
        invalidate_storage_stats_cache()
        self.temp_dir.cleanup()

    def test_cached_stats_can_be_forced_or_invalidated(self):
        original = self.storage_path / "original"
        original.mkdir(parents=True)
        (original / "one.webp").write_bytes(b"one")

        initial = directory_stats(original)
        (original / "two.webp").write_bytes(b"second")
        cached = directory_stats(original)
        refreshed = directory_stats(original, force_refresh=True)

        self.assertEqual(initial["file_count"], 1)
        self.assertEqual(cached["file_count"], 1)
        self.assertEqual(refreshed["file_count"], 2)
        self.assertEqual(refreshed["size_bytes"], 9)

        (original / "three.webp").write_bytes(b"third")
        invalidate_storage_stats_cache(self.storage_path)
        self.assertEqual(directory_stats(original)["file_count"], 3)

    def test_media_stats_include_missing_directories_without_failing(self):
        stats = media_storage_stats(self.storage_path)

        self.assertEqual(set(stats), {"original", "preview", "thumbnail"})
        self.assertTrue(all(not item["exists"] for item in stats.values()))
        self.assertTrue(all(item["file_count"] == 0 for item in stats.values()))


if __name__ == "__main__":
    unittest.main()
