import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api import imports
from app.schemas.image import ImageBatchItemUpdate, ImageUpdate
from app.schemas.work import WorkCreate, WorkUpdate
from app.utils.urls import normalize_http_url


class ExternalUrlValidationTests(unittest.TestCase):
    def test_accepts_http_https_and_normalizes_blank_values(self):
        self.assertEqual(normalize_http_url(" https://example.com/art?id=1 "), "https://example.com/art?id=1")
        self.assertEqual(ImageUpdate(source_url="http://example.com").source_url, "http://example.com")
        self.assertIsNone(ImageBatchItemUpdate(source_url="  ").source_url)
        self.assertEqual(WorkCreate(name="Example", official_site="https://example.com").official_site, "https://example.com")

    def test_rejects_unsafe_or_ambiguous_urls_across_edit_schemas(self):
        invalid_urls = (
            "javascript:alert(1)",
            "data:text/html,unsafe",
            "//example.com/path",
            "https://user:password@example.com/path",
            "https://example.com\\@evil.example/path",
        )
        for value in invalid_urls:
            with self.subTest(value=value, schema="image"):
                with self.assertRaises(ValidationError):
                    ImageUpdate(source_url=value)
            with self.subTest(value=value, schema="batch"):
                with self.assertRaises(ValidationError):
                    ImageBatchItemUpdate(source_url=value)
            with self.subTest(value=value, schema="work-create"):
                with self.assertRaises(ValidationError):
                    WorkCreate(name="Example", official_site=value)
            with self.subTest(value=value, schema="work-update"):
                with self.assertRaises(ValidationError):
                    WorkUpdate(official_site=value)

    def test_metadata_import_reports_invalid_official_site(self):
        row = {"work_name": "Unsafe Work", "work_official_site": "javascript:alert(1)"}
        with self.assertRaisesRegex(ValueError, "http or https"):
            imports._normalize_row(row, 2)


if __name__ == "__main__":
    unittest.main()
