import importlib
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class ArtifactGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        os.environ["REQUIREMENT_WORKBENCH_DATA_DIR"] = self.temp_dir.name

        from backend.app import config, db
        from backend.app.services import artifact_generation, project_catalog

        self.config = importlib.reload(config)
        self.db = importlib.reload(db)
        self.artifact_generation = importlib.reload(artifact_generation)
        self.project_catalog = importlib.reload(project_catalog)

        self.db.init_db()

    def tearDown(self) -> None:
        os.environ.pop("REQUIREMENT_WORKBENCH_DATA_DIR", None)
        self.temp_dir.cleanup()

    def test_generate_document_artifact_persists_metadata_and_file(self) -> None:
        artifact = self.artifact_generation.generate_artifact(
            project_id="seed-reconciliation",
            artifact_type="document"
        )

        self.assertEqual(artifact.status, "generated")
        self.assertTrue(Path(artifact.storage_path).exists())

        stored = self.project_catalog.list_artifacts("seed-reconciliation")
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].id, artifact.id)

        payload = json.loads(Path(artifact.storage_path).read_text(encoding="utf-8"))
        self.assertEqual(payload["artifact_type"], "document")
        self.assertIn("sections", payload)

    def test_generate_html_artifact_writes_previewable_page(self) -> None:
        artifact = self.artifact_generation.generate_artifact(
            project_id="seed-reconciliation",
            artifact_type="page_solution"
        )

        html = Path(artifact.storage_path).read_text(encoding="utf-8")
        self.assertEqual(artifact.content_format, "html")
        self.assertIn("<title>", html)
        self.assertIn("页面方案", html)

    def test_validate_html_rejects_external_script(self) -> None:
        with self.assertRaises(ValueError):
            self.artifact_generation.validate_html_artifact(
                """
                <html>
                  <head><title>bad</title></head>
                  <body><main>test</main><script src="https://cdn.example.com/app.js"></script></body>
                </html>
                """
            )


if __name__ == "__main__":
    unittest.main()
