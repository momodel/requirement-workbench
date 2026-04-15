import importlib
import os
import unittest
from tempfile import TemporaryDirectory


class ProjectCreationTests(unittest.TestCase):
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

    def test_create_project_persists_new_project(self) -> None:
        created = self.project_catalog.create_project(
            name="结算对账分析",
            summary="针对结算系统和财务科目做需求转译",
            scenario_type="settlement-reconciliation"
        )

        self.assertEqual(created.name, "结算对账分析")
        fetched = self.project_catalog.get_project(created.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.id, created.id)

    def test_list_projects_includes_created_project(self) -> None:
        self.project_catalog.create_project(
            name="订单对账分析",
            summary="补充项目",
            scenario_type="order-reconciliation"
        )

        projects = self.project_catalog.list_projects()
        self.assertEqual(len(projects), 2)


if __name__ == "__main__":
    unittest.main()
