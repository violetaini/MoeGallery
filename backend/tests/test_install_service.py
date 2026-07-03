import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.services import install_service


class InstallServiceTests(unittest.TestCase):
    def setUp(self):
        self.original_database_url = settings.database_url
        self.temp_dir = tempfile.TemporaryDirectory(prefix="agms-install-test-")

    def tearDown(self):
        settings.database_url = self.original_database_url
        self.temp_dir.cleanup()

    def _set_sqlite_database(self, name: str) -> str:
        database_url = f"sqlite:///{Path(self.temp_dir.name) / name}"
        settings.database_url = database_url
        return database_url

    def test_empty_alembic_version_table_is_not_initialized(self):
        database_url = self._set_sqlite_database("empty-version.db")
        engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL)"))
        finally:
            engine.dispose()

        self.assertFalse(install_service.current_database_is_initialized())

    def test_populated_alembic_version_table_is_initialized(self):
        database_url = self._set_sqlite_database("populated-version.db")
        engine = create_engine(database_url, connect_args={"check_same_thread": False}, future=True)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(128) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0001_initial_schema')"))
        finally:
            engine.dispose()

        self.assertTrue(install_service.current_database_is_initialized())


if __name__ == "__main__":
    unittest.main()
