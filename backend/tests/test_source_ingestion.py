import importlib
import os
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class SourceIngestionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        os.environ["REQUIREMENT_WORKBENCH_DATA_DIR"] = self.temp_dir.name

        from backend.app import config, db
        from backend.app.services import source_ingestion

        self.config = importlib.reload(config)
        self.db = importlib.reload(db)
        self.source_ingestion = importlib.reload(source_ingestion)

        self.db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("REQUIREMENT_WORKBENCH_DATA_DIR", None)
        self.temp_dir.cleanup()

    def test_ingest_text_source_writes_files_and_db_row(self) -> None:
        record = self.source_ingestion.ingest_text_source(
            project_id="seed-reconciliation",
            name="访谈纪要.txt",
            text="客户希望先把逐笔差异找出来，再人工确认归因。"
        )

        self.assertEqual(record.parse_status, "parsed")
        self.assertEqual(record.sync_status, "pending")
        self.assertTrue(Path(record.storage_path).exists())
        self.assertTrue(Path(record.normalized_path).exists())

        connection = self.db.get_connection()
        try:
            row = connection.execute(
                "SELECT name, parse_status, sync_status FROM sources WHERE id = ?",
                (record.id,),
            ).fetchone()
        finally:
            connection.close()

        self.assertIsNotNone(row)
        self.assertEqual(row["name"], "访谈纪要.txt")
        self.assertEqual(row["parse_status"], "parsed")
        self.assertEqual(row["sync_status"], "pending")

    def test_ingest_url_source_creates_normalized_note(self) -> None:
        record = self.source_ingestion.ingest_url_source(
            project_id="seed-reconciliation",
            name="业务系统说明链接",
            url="https://example.com/reconciliation"
        )

        self.assertEqual(record.source_kind, "url")
        self.assertTrue(Path(record.normalized_path).exists())
        normalized_text = Path(record.normalized_path).read_text(encoding="utf-8")
        self.assertIn("https://example.com/reconciliation", normalized_text)

    def test_ingest_file_source_persists_binary_file_and_summary(self) -> None:
        record = self.source_ingestion.ingest_file_source(
            project_id="seed-reconciliation",
            name="差异样本.xlsx",
            content=b"sheet:orders\norder_id,amount,subject_code\nA1001,1280,6001\n",
            source_kind="xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        self.assertEqual(record.upload_kind, "file")
        self.assertEqual(record.source_kind, "xlsx")
        self.assertTrue(Path(record.storage_path).exists())
        self.assertTrue(Path(record.normalized_path).exists())

        normalized_text = Path(record.normalized_path).read_text(encoding="utf-8")
        self.assertIn("order_id", normalized_text)
        self.assertIn("sheet", record.parse_summary.lower())


if __name__ == "__main__":
    unittest.main()
