from pathlib import Path

from app.config import AppSettings
from app.models import ProviderIssue
from app.services.source_ingestion import SourceIngestionService


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        notebooklm_home_dir=data_dir / "notebooklm",
        claude_cli_path=str(tmp_path / "fake-claude"),
    )


class FakeDoclingNormalizer:
    def __init__(self, result: str | None = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[Path] = []

    def supports(self, source_path: Path) -> bool:
        return True

    def normalize_to_markdown(self, source_path: Path) -> str:
        self.calls.append(source_path)
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def test_ingest_pdf_uses_docling_markdown_output(tmp_path: Path) -> None:
    normalizer = FakeDoclingNormalizer("# 规则说明\nDocling extracted text")
    service = SourceIngestionService(
        make_settings(tmp_path),
        docling_normalizer=normalizer,
    )

    storage_path, normalized = service.ingest_file(
        "project-1",
        "rules.pdf",
        b"%PDF-1.4 mock content",
    )

    assert Path(storage_path).name == "rules.pdf"
    assert normalizer.calls == [Path(storage_path)]
    assert normalized.parse_status == "parsed"
    assert normalized.notebook_import_mode == "normalized_text"
    assert normalized.normalized_path is not None
    assert Path(normalized.normalized_path).read_text(encoding="utf-8") == "# 规则说明\nDocling extracted text"
    assert "Docling extracted text" in normalized.parse_summary


def test_ingest_image_fails_honestly_when_text_normalization_is_unavailable(tmp_path: Path) -> None:
    normalizer = FakeDoclingNormalizer(
        error=ProviderIssue(
            provider="DOCLING",
            message="当前环境还没有可用的图片转文本链路。",
        )
    )
    service = SourceIngestionService(
        make_settings(tmp_path),
        docling_normalizer=normalizer,
    )

    _, normalized = service.ingest_file(
        "project-1",
        "flowchart.png",
        b"\x89PNG\r\n",
    )

    assert normalized.parse_status == "failed"
    assert normalized.normalized_path is None
    assert normalized.notebook_import_mode is None
    assert "图片转文本链路" in normalized.parse_summary


def test_ingest_audio_fails_honestly_when_asr_is_unavailable(tmp_path: Path) -> None:
    normalizer = FakeDoclingNormalizer(
        error=ProviderIssue(
            provider="DOCLING",
            message="当前环境还没有可用的音频转文本链路。",
        )
    )
    service = SourceIngestionService(
        make_settings(tmp_path),
        docling_normalizer=normalizer,
    )

    _, normalized = service.ingest_file(
        "project-1",
        "interview.mp3",
        b"ID3",
    )

    assert normalized.parse_status == "failed"
    assert normalized.normalized_path is None
    assert normalized.notebook_import_mode is None
    assert "音频转文本链路" in normalized.parse_summary
