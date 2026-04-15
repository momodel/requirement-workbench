import importlib
import json
import os
import unittest
from tempfile import TemporaryDirectory


class ChatServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        os.environ["REQUIREMENT_WORKBENCH_DATA_DIR"] = self.temp_dir.name

        from backend.app import config, db
        from backend.app.services import chat_service, project_catalog

        self.config = importlib.reload(config)
        self.db = importlib.reload(db)
        self.chat_service = importlib.reload(chat_service)
        self.project_catalog = importlib.reload(project_catalog)

        self.db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("REQUIREMENT_WORKBENCH_DATA_DIR", None)
        self.temp_dir.cleanup()

    def test_run_chat_round_persists_messages_state_and_artifact(self) -> None:
        from backend.app.services import source_ingestion

        source_ingestion = importlib.reload(source_ingestion)
        connection = self.db.get_connection()
        try:
            initial_message_count = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE project_id = ?",
                ("seed-reconciliation",),
            ).fetchone()[0]
        finally:
            connection.close()

        source = source_ingestion.ingest_text_source(
            project_id="seed-reconciliation",
            name="访谈纪要.txt",
            text="希望先识别逐笔差异，再给出人工复核建议，不自动改账。",
        )

        events = list(
            self.chat_service.run_chat_round(
                project_id="seed-reconciliation",
                message="我们先关注逐笔差异识别，不自动改账。",
                selected_source_ids=[source.id],
                request_artifact_types=["document", "page_solution"],
            )
        )

        event_names = [event["event"] for event in events]
        self.assertIn("message_chunk", event_names)
        self.assertIn("citations", event_names)
        self.assertIn("current_understanding_patch", event_names)
        self.assertIn("pending_patch", event_names)
        self.assertIn("artifact_patch", event_names)
        self.assertIn("version_patch", event_names)
        self.assertEqual(event_names[-1], "done")

        connection = self.db.get_connection()
        try:
            message_count = connection.execute(
                "SELECT COUNT(*) FROM messages WHERE project_id = ?",
                ("seed-reconciliation",),
            ).fetchone()[0]
            state_count = connection.execute(
                "SELECT COUNT(*) FROM state_items WHERE project_id = ? AND category = ?",
                ("seed-reconciliation", "current_understanding"),
            ).fetchone()[0]
            artifact_count = connection.execute(
                "SELECT COUNT(*) FROM demo_artifacts WHERE project_id = ?",
                ("seed-reconciliation",),
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(message_count, initial_message_count + 2)
        self.assertGreaterEqual(state_count, 2)
        self.assertGreaterEqual(artifact_count, 2)

        versions = self.project_catalog.list_versions("seed-reconciliation")
        self.assertGreaterEqual(len(versions), 2)
        self.assertTrue(any("chat-round" in version.id for version in versions))


if __name__ == "__main__":
    unittest.main()
