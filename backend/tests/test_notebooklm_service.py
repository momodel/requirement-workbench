import importlib
import os
import unittest
from tempfile import TemporaryDirectory


class NotebookLMServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        os.environ["REQUIREMENT_WORKBENCH_DATA_DIR"] = self.temp_dir.name

        from backend.app import config, db
        from backend.app.services import notebooklm_service

        self.config = importlib.reload(config)
        self.db = importlib.reload(db)
        self.notebooklm_service = importlib.reload(notebooklm_service)

        self.db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("REQUIREMENT_WORKBENCH_DATA_DIR", None)
        self.temp_dir.cleanup()

    def test_ensure_binding_creates_project_binding(self) -> None:
        binding = self.notebooklm_service.ensure_notebook_binding("seed-reconciliation")

        self.assertEqual(binding["project_id"], "seed-reconciliation")
        self.assertEqual(binding["sync_status"], "pending")

    def test_mark_sync_status_updates_binding(self) -> None:
        self.notebooklm_service.ensure_notebook_binding("seed-reconciliation")
        self.notebooklm_service.mark_sync_status(
            project_id="seed-reconciliation",
            sync_status="synced"
        )

        binding = self.notebooklm_service.get_notebook_binding("seed-reconciliation")
        self.assertIsNotNone(binding)
        self.assertEqual(binding["sync_status"], "synced")

    def test_query_returns_grounded_summary_and_citations(self) -> None:
        from backend.app.services import source_ingestion

        source_ingestion = importlib.reload(source_ingestion)
        source = source_ingestion.ingest_text_source(
            project_id="seed-reconciliation",
            name="访谈纪要.txt",
            text="客户重点关注订单金额与财务科目 6001 的逐笔一致性。",
        )

        self.notebooklm_service.import_source(
            project_id="seed-reconciliation",
            source_id=source.id,
            normalized_path=source.normalized_path or "",
            source_name=source.name,
        )
        result = self.notebooklm_service.query(
            project_id="seed-reconciliation",
            question="当前逐笔对账最核心的核对关系是什么？",
            selected_source_ids=[source.id],
        )

        self.assertIn("逐笔", result.summary)
        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.citations[0]["source_id"], source.id)


if __name__ == "__main__":
    unittest.main()
