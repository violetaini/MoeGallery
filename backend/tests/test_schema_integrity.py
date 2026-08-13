import sys
import tempfile
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class SchemaIntegrityMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-schema-integrity-")
        self.database_path = Path(self.temp_dir.name) / "schema.db"
        self.database_url = f"sqlite:///{self.database_path.as_posix()}"
        self.config = Config(str(BACKEND_DIR / "alembic.ini"))
        self.config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
        self.config.set_main_option("sqlalchemy.url", self.database_url)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_upgrade_repairs_backdrop_reference_and_adds_lookup_indexes(self):
        command.upgrade(self.config, "0015_database_concurrency")
        engine = create_engine(self.database_url, future=True)
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO works "
                        "(name, sort_order, created_at, updated_at, backdrop_image_id) "
                        "VALUES ('dangling backdrop', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 999999)"
                    )
                )
        finally:
            engine.dispose()

        command.upgrade(self.config, "head")
        engine = create_engine(self.database_url, future=True)
        try:
            inspector = inspect(engine)
            work_indexes = inspector.get_indexes("works")
            character_indexes = inspector.get_indexes("characters")
            work_index_columns = {tuple(item["column_names"]) for item in work_indexes}
            character_index_columns = {tuple(item["column_names"]) for item in character_indexes}
            backdrop_foreign_keys = [
                item
                for item in inspector.get_foreign_keys("works")
                if item["constrained_columns"] == ["backdrop_image_id"]
            ]

            self.assertIn(("cover_image_id",), work_index_columns)
            self.assertIn(("backdrop_image_id",), work_index_columns)
            self.assertIn(("avatar_image_id",), character_index_columns)
            self.assertEqual(len(backdrop_foreign_keys), 1)
            self.assertEqual(backdrop_foreign_keys[0]["referred_table"], "images")
            self.assertEqual(backdrop_foreign_keys[0]["options"].get("ondelete"), "SET NULL")
            with engine.connect() as connection:
                value = connection.execute(
                    text("SELECT backdrop_image_id FROM works WHERE name = 'dangling backdrop'")
                ).scalar()
            self.assertIsNone(value)
        finally:
            engine.dispose()

        command.check(self.config)


if __name__ == "__main__":
    unittest.main()
