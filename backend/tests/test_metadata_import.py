import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api import imports
from app.database import Base
from app.models import Character, Work


HEADERS = imports.TEMPLATE_HEADERS


def sample_rows(prefix: str) -> list[dict[str, str]]:
    return [
        {
            "work_name": f"{prefix} 作品一",
            "work_original_name": f"{prefix} Work One",
            "work_aliases": "别名一; Alias One",
            "work_description": "只创建作品的测试行",
            "work_tagline": "测试标语一",
            "work_production_year": "2024",
            "work_run_time_minutes": "24",
            "work_community_rating": "8.6",
            "work_content_rating": "safe",
            "work_genres": "校园; 推理",
            "work_studios": "测试制作组",
            "work_official_site": "https://example.com/one",
            "work_status": "完结",
            "work_sort_order": "10",
            "character_name": "",
            "character_original_name": "",
            "character_aliases": "",
            "character_description": "",
        },
        {
            "work_name": f"{prefix} 作品二",
            "work_original_name": f"{prefix} Work Two",
            "work_aliases": "别名二",
            "work_description": "创建作品和角色的测试行",
            "work_tagline": "测试标语二",
            "work_production_year": "2025",
            "work_run_time_minutes": "25",
            "work_community_rating": "9.1",
            "work_content_rating": "sensitive",
            "work_genres": "奇幻; 冒险",
            "work_studios": "测试公司",
            "work_official_site": "https://example.com/two",
            "work_status": "连载",
            "work_sort_order": "20",
            "character_name": f"{prefix} 角色二",
            "character_original_name": f"{prefix} Character Two",
            "character_aliases": "角色别名二",
            "character_description": "角色导入测试",
        },
    ]


def csv_bytes(rows: list[dict[str, str]]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return ("\ufeff" + output.getvalue()).encode("utf-8")


def json_bytes(rows: list[dict[str, str]]) -> bytes:
    return json.dumps({"items": rows}, ensure_ascii=False).encode("utf-8")


def workbook_bytes(rows: list[dict[str, str]], keep_vba: bool = False) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADERS)
    for row in rows:
        sheet.append([row.get(header, "") for header in HEADERS])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class MetadataImportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-import-test-")
        self.engine = create_engine(
            f"sqlite:///{Path(self.temp_dir.name) / 'metadata-import.db'}",
            connect_args={"check_same_thread": False},
            future=True,
        )
        Base.metadata.create_all(bind=self.engine)
        self.SessionTesting = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _assert_import_format(self, filename: str, data: bytes, prefix: str) -> None:
        rows = imports._parse_upload(filename, data)
        with self.SessionTesting() as db:
            preview = imports._process_rows(db, rows, dry_run=True)
            self.assertEqual(preview.total_rows, 2)
            self.assertEqual(preview.valid_rows, 2)
            self.assertEqual(preview.error_rows, 0)
            self.assertEqual(preview.works_created, 2)
            self.assertEqual(preview.characters_created, 1)
            self.assertEqual(db.scalar(select(Work).where(Work.name == f"{prefix} 作品一")), None)

            result = imports._process_rows(db, rows, dry_run=False)
            self.assertEqual(result.error_rows, 0)
            self.assertEqual(result.works_created, 2)
            self.assertEqual(result.characters_created, 1)

            work_one = db.scalar(select(Work).where(Work.name == f"{prefix} 作品一"))
            self.assertIsNotNone(work_one)
            self.assertEqual(work_one.production_year, 2024)
            self.assertEqual(work_one.run_time_minutes, 24)
            self.assertEqual(work_one.community_rating, 8.6)
            self.assertEqual(work_one.sort_order, 10)

            work_two = db.scalar(select(Work).where(Work.name == f"{prefix} 作品二"))
            self.assertIsNotNone(work_two)
            character = db.scalar(select(Character).where(Character.name == f"{prefix} 角色二"))
            self.assertIsNotNone(character)
            self.assertEqual(character.work_id, work_two.id)
            self.assertEqual(character.original_name, f"{prefix} Character Two")

    def test_csv_json_xlsx_and_xlsm_imports(self):
        cases = [
            ("metadata.csv", csv_bytes(sample_rows("CSV")), "CSV"),
            ("metadata.json", json_bytes(sample_rows("JSON")), "JSON"),
            ("metadata.xlsx", workbook_bytes(sample_rows("XLSX")), "XLSX"),
            ("metadata.xlsm", workbook_bytes(sample_rows("XLSM"), keep_vba=True), "XLSM"),
        ]
        for filename, data, prefix in cases:
            with self.subTest(filename=filename):
                self._assert_import_format(filename, data, prefix)

    def test_template_download_payloads_are_parseable(self):
        for format_name in ("csv", "json", "xlsx", "xlsm"):
            with self.subTest(format=format_name):
                payload = imports.build_metadata_template(format_name)
                rows = imports._parse_upload(f"template.{format_name}", payload)
                self.assertEqual(len(rows), 2)
                self.assertEqual(rows[0]["work_name"], "示例作品A")

    def test_template_download_headers_include_filename_suffix(self):
        for format_name in ("csv", "json", "xlsx", "xlsm"):
            with self.subTest(format=format_name):
                response = imports.download_metadata_template(admin={}, format=format_name)
                filename = f"metadata-import-template.{format_name}"
                self.assertEqual(response.headers["x-template-filename"], filename)
                self.assertIn(f'filename="{filename}"', response.headers["content-disposition"])
                self.assertIn(f"filename*=UTF-8''{filename}", response.headers["content-disposition"])

    def test_xlsm_template_uses_macro_enabled_content_type(self):
        payload = imports.build_metadata_template("xlsm")
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            content_types = archive.read("[Content_Types].xml").decode("utf-8")
        self.assertIn("application/vnd.ms-excel.sheet.macroEnabled.main+xml", content_types)


if __name__ == "__main__":
    unittest.main()
