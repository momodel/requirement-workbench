import importlib
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class SeedStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        os.environ["REQUIREMENT_WORKBENCH_DATA_DIR"] = self.temp_dir.name

        from backend.app import config, db
        from backend.app.services import project_state

        self.config = importlib.reload(config)
        self.db = importlib.reload(db)
        self.project_state = importlib.reload(project_state)

    def tearDown(self) -> None:
        os.environ.pop("REQUIREMENT_WORKBENCH_DATA_DIR", None)
        self.temp_dir.cleanup()

    def test_init_db_creates_seed_project_and_sources(self) -> None:
        self.db.init_db()

        self.assertTrue(Path(self.config.SQLITE_PATH).exists())

        connection = self.db.get_connection()
        try:
            project_count = connection.execute(
                "SELECT COUNT(*) FROM projects"
            ).fetchone()[0]
            source_count = connection.execute(
                "SELECT COUNT(*) FROM sources"
            ).fetchone()[0]
            state_count = connection.execute(
                "SELECT COUNT(*) FROM state_items"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(project_count, 1)
        self.assertEqual(source_count, 2)
        self.assertGreaterEqual(state_count, 3)

    def test_get_project_state_reads_seed_data_from_storage(self) -> None:
        self.db.init_db()

        state = self.project_state.get_project_state("seed-reconciliation")

        self.assertEqual(len(state.current_understanding), 1)
        self.assertEqual(state.current_understanding[0].title, "仓库主路径已切换到全栈一期")
        self.assertEqual(len(state.pending_items), 1)
        self.assertEqual(len(state.versions), 1)


if __name__ == "__main__":
    unittest.main()
