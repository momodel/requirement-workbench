import unittest


class ModelImportTests(unittest.TestCase):
    def test_models_can_be_instantiated_without_optional_runtime_dependencies(self) -> None:
        from backend.app.models import ProjectSummary

        project = ProjectSummary(
            id="project-1",
            name="Example",
            scenario_type="demo",
            summary="Example summary",
            status="draft",
            created_at="2026-04-15T00:00:00+08:00",
            updated_at="2026-04-15T00:00:00+08:00"
        )

        self.assertEqual(project.id, "project-1")
        self.assertEqual(project.name, "Example")


if __name__ == "__main__":
    unittest.main()
