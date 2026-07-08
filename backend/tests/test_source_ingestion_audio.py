from pathlib import Path

import pytest

from app.config import AppSettings
from app.models import ProviderIssue
from app.services.docling_normalizer import DoclingNormalizer
from app.services.source_ingestion import SourceIngestionService


class GuardNormalizer:
    def supports(self, source_path: Path) -> bool:
        raise AssertionError(
            "Audio uploads should not ask Docling whether audio is supported"
        )


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        llm_cli_path=str(tmp_path / "fake-claude"),
    )


def test_ingest_audio_returns_processing_and_bypasses_docling(tmp_path: Path) -> None:
    service = SourceIngestionService(
        make_settings(tmp_path),
        docling_normalizer=GuardNormalizer(),
    )

    storage_path, normalized = service.ingest_file(
        "project-1",
        "call.mp3",
        b"ID3",
    )

    assert storage_path.endswith("call.mp3")
    assert normalized.source_kind == "audio"
    assert normalized.normalize_status == "processing"
    assert normalized.normalized_path is None
    assert normalized.index_input_mode is None
    assert (
        normalized.normalize_summary
        == "call.mp3 已入库，正在转写；完成后会自动进入项目知识库。"
    )


def test_docling_normalizer_rejects_audio_inputs() -> None:
    normalizer = DoclingNormalizer()

    assert normalizer.supports(Path("call.mp3")) is False

    with pytest.raises(ProviderIssue, match="AudioTranscriptionService"):
        normalizer.normalize_to_markdown(Path("call.mp3"))
