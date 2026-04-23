import os
from pathlib import Path

from app.config import AppSettings, _load_local_env_file


def test_from_env_no_longer_exposes_notebooklm_home(monkeypatch: object) -> None:
    monkeypatch.delenv("NOTEBOOKLM_QUERY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_DATA_DIR", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_SQLITE_DIR", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_SQLITE_PATH", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_PROJECTS_DIR", raising=False)

    settings = AppSettings.from_env()

    assert "notebooklm_home_dir" not in AppSettings.__dataclass_fields__
    assert not hasattr(settings, "notebooklm_home_dir")
    assert "notebooklm_query_timeout_seconds" not in AppSettings.__dataclass_fields__
    assert not hasattr(settings, "notebooklm_query_timeout_seconds")


def test_from_env_defaults_evidence_runtime_paths(monkeypatch: object) -> None:
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_DATA_DIR", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_QDRANT_PATH", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_QDRANT_URL", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_QDRANT_COLLECTION_PREFIX", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_EVIDENCE_BACKEND", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_EMBEDDER_BACKEND", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_EVIDENCE_QUERY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("REQUIREMENT_WORKBENCH_EVIDENCE_TOP_K", raising=False)
    monkeypatch.delenv("EVIDENCE_QUERY_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("EVIDENCE_TOP_K", raising=False)

    settings = AppSettings.from_env()

    assert settings.qdrant_path == settings.data_dir / "qdrant"
    assert settings.qdrant_url is None
    assert settings.qdrant_collection_prefix == "project"
    assert settings.evidence_backend == "qdrant_llamaindex"
    assert settings.embedder_backend == "fastembed"
    assert settings.evidence_query_timeout_seconds == 15.0
    assert settings.evidence_top_k == 6


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
