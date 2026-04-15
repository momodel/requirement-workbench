import importlib
import os
import unittest
from tempfile import TemporaryDirectory


class ProjectCatalogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        os.environ["REQUIREMENT_WORKBENCH_DATA_DIR"] = self.temp_dir.name

        from backend.app import config, db
        from backend.app.services import project_catalog

        self.config = importlib.reload(config)
        self.db = importlib.reload(db)
        self.project_catalog = importlib.reload(project_catalog)

        self.db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("REQUIREMENT_WORKBENCH_DATA_DIR", None)
        self.temp_dir.cleanup()

    def test_list_projects_reads_seed_project_from_storage(self) -> None:
        projects = self.project_catalog.list_projects()

        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].id, "seed-reconciliation")

    def test_get_project_returns_seed_project_from_storage(self) -> None:
        project = self.project_catalog.get_project("seed-reconciliation")

        self.assertIsNotNone(project)
        self.assertEqual(project.name, "业财逐笔对账")

    def test_list_sources_reads_seed_sources_from_storage(self) -> None:
        sources = self.project_catalog.list_sources("seed-reconciliation")

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0].project_id, "seed-reconciliation")
        self.assertEqual(sources[0].sync_status, "pending")


if __name__ == "__main__":
    unittest.main()
