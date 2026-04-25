import os
from pathlib import Path

from app.config import AppSettings, _load_local_env_file


def test_from_env_defaults_project_paths_to_repo_data_dir(monkeypatch: object) -> None:
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_DATA_DIR", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_SQLITE_DIR", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_SQLITE_PATH", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_PROJECTS_DIR", raising=False)

    settings = AppSettings.from_env()

    assert settings.projects_dir == settings.data_dir / "projects"


def test_load_local_env_file_sets_missing_values_only(tmp_path: Path, monkeypatch) -> None:
    backend_dir = tmp_path / "backend"
    backend_dir.mkdir(parents=True, exist_ok=True)
    env_file = backend_dir / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "ANTHROPIC_API_KEY=from-local-file",
                "ANTHROPIC_BASE_URL='https://coding.dashscope.aliyuncs.com/apps/anthropic'",
                'CLAUDE_MODEL="glm-5"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("CLAUDE_MODEL", "already-set")

    _load_local_env_file(tmp_path)

    assert os.getenv("ANTHROPIC_API_KEY") == "from-local-file"
    assert os.getenv("ANTHROPIC_BASE_URL") == "https://coding.dashscope.aliyuncs.com/apps/anthropic"
    assert os.getenv("CLAUDE_MODEL") == "already-set"
