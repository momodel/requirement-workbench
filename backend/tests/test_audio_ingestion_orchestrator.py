from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import CreateProjectRequest, ProviderIssue
from app.services.audio_ingestion_orchestrator import AudioIngestionOrchestrator
from app.services.audio_transcription_service import (
    ALIYUN_FILETRANS,
    AudioTranscriptionResult,
)
from app.services.object_storage_service import UploadedObject
from app.services.project_catalog import ProjectCatalog


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
    )


def create_audio_source(
    *,
    settings: AppSettings,
    catalog: ProjectCatalog,
) -> tuple[str, object]:
    project = catalog.create_project(
        CreateProjectRequest(
            name="音频项目",
            scenario_type="general",
            summary="验证异步音频编排",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    raw_path = source_dir / "call.mp3"
    raw_path.write_bytes(b"ID3")
    source = catalog.create_source(
        project_id=project.id,
        name="call.mp3",
        source_kind="audio",
        upload_kind="file",
        storage_path=str(raw_path),
        normalized_path=None,
        index_input_mode=None,
        normalize_status="processing",
        normalize_summary="call.mp3 已入库，正在转写；完成后会自动进入项目知识库。",
        index_status="normalization_pending",
        index_error="音频正在转写，完成后会自动进入项目知识库。",
    )
    return project.id, source


class FakeStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, Path]] = []

    def upload_audio_source(
        self,
        *,
        project_id: str,
        source_id: str,
        local_path: Path,
    ) -> UploadedObject:
        self.calls.append((project_id, source_id, local_path))
        return UploadedObject(
            object_key=f"audio/{project_id}/{source_id}/{local_path.name}",
            url=f"https://audio.example.com/audio/{project_id}/{source_id}/{local_path.name}",
        )


class FakeTranscription:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def transcribe_from_url(
        self,
        *,
        file_url: str,
        source_name: str,
    ) -> AudioTranscriptionResult:
        self.calls.append((file_url, source_name))
        return AudioTranscriptionResult(
            provider_job_id="task-1",
            markdown="# 音频转写\n\n00:00-00:05 逐笔对账需要人工确认",
        )


class FakeEvidenceRuntime:
    def __init__(self) -> None:
        self.index_calls: list[tuple[str, str]] = []

    def index_source(self, project_id: str, source_id: str) -> list[object]:
        self.index_calls.append((project_id, source_id))
        return []


def test_update_source_normalization_updates_fields_and_project_timestamp(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id, source = create_audio_source(settings=settings, catalog=catalog)
    before = catalog.get_project(project_id)

    updated = catalog.update_source_normalization(
        source_id=source.id,
        normalized_path="D:/normalized/call.normalized.md",
        index_input_mode="normalized_text",
        normalize_status="parsed",
        normalize_summary="ASR 已生成转写文本。",
        index_status="pending",
        index_error=None,
    )
    after = catalog.get_project(project_id)

    assert updated.normalized_path == "D:/normalized/call.normalized.md"
    assert updated.index_input_mode == "normalized_text"
    assert updated.normalize_status == "parsed"
    assert updated.normalize_summary == "ASR 已生成转写文本。"
    assert updated.index_status == "pending"
    assert updated.index_error is None
    assert before is not None
    assert after is not None
    assert after.updated_at != before.updated_at


def test_process_source_writes_normalized_markdown_and_indexes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id, source = create_audio_source(settings=settings, catalog=catalog)
    storage = FakeStorage()
    transcription = FakeTranscription()
    evidence_runtime = FakeEvidenceRuntime()
    orchestrator = AudioIngestionOrchestrator(
        settings=settings,
        catalog=catalog,
        object_storage=storage,
        audio_transcription=transcription,
        evidence_runtime=evidence_runtime,
    )

    orchestrator.process_source(project_id, source.id)

    refreshed = catalog.get_source(source.id)
    jobs = catalog.list_source_processing_jobs(source_id=source.id)

    assert refreshed is not None
    assert refreshed.normalize_status == "parsed"
    assert refreshed.normalize_summary == "ASR 已生成转写文本。"
    assert refreshed.index_input_mode == "normalized_text"
    assert refreshed.index_status == "indexed"
    assert refreshed.index_error is None
    assert refreshed.normalized_path is not None
    normalized_path = Path(refreshed.normalized_path)
    assert normalized_path.exists()
    assert "00:00-00:05 逐笔对账需要人工确认" in normalized_path.read_text(
        encoding="utf-8"
    )
    assert storage.calls == [(project_id, source.id, Path(source.storage_path))]
    assert transcription.calls == [
        (
            f"https://audio.example.com/audio/{project_id}/{source.id}/call.mp3",
            "call.mp3",
        )
    ]
    assert evidence_runtime.index_calls == [(project_id, source.id)]
    assert len(jobs) == 1
    assert jobs[0].provider == ALIYUN_FILETRANS
    assert jobs[0].status == "completed"
    assert jobs[0].provider_job_id == "task-1"
    assert jobs[0].last_error is None


def test_process_source_marks_pre_transcription_failure_without_indexing(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id, source = create_audio_source(settings=settings, catalog=catalog)

    class FailingStorage:
        def upload_audio_source(
            self,
            *,
            project_id: str,
            source_id: str,
            local_path: Path,
        ) -> UploadedObject:
            raise ProviderIssue(provider="QINIU_OSS", message="七牛上传失败。")

    evidence_runtime = FakeEvidenceRuntime()
    orchestrator = AudioIngestionOrchestrator(
        settings=settings,
        catalog=catalog,
        object_storage=FailingStorage(),
        audio_transcription=FakeTranscription(),
        evidence_runtime=evidence_runtime,
    )

    orchestrator.process_source(project_id, source.id)

    refreshed = catalog.get_source(source.id)
    jobs = catalog.list_source_processing_jobs(source_id=source.id)

    assert refreshed is not None
    assert refreshed.normalize_status == "failed"
    assert refreshed.normalize_summary == "七牛上传失败。"
    assert refreshed.normalized_path is None
    assert refreshed.index_input_mode is None
    assert refreshed.index_status == "normalization_failed"
    assert "尚未进入项目知识库" in (refreshed.index_error or "")
    assert evidence_runtime.index_calls == []
    assert len(jobs) == 1
    assert jobs[0].status == "failed"
    assert jobs[0].provider_job_id is None
    assert jobs[0].last_error == "七牛上传失败。"


def test_process_source_marks_index_failure_and_keeps_transcript(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id, source = create_audio_source(settings=settings, catalog=catalog)

    class FailingEvidenceRuntime(FakeEvidenceRuntime):
        def index_source(self, project_id: str, source_id: str) -> list[object]:
            self.index_calls.append((project_id, source_id))
            raise ProviderIssue(
                provider="QDRANT_LLAMAINDEX",
                message="Qdrant 写入失败。",
            )

    orchestrator = AudioIngestionOrchestrator(
        settings=settings,
        catalog=catalog,
        object_storage=FakeStorage(),
        audio_transcription=FakeTranscription(),
        evidence_runtime=FailingEvidenceRuntime(),
    )

    orchestrator.process_source(project_id, source.id)

    refreshed = catalog.get_source(source.id)
    jobs = catalog.list_source_processing_jobs(source_id=source.id)

    assert refreshed is not None
    assert refreshed.normalize_status == "parsed"
    assert refreshed.index_status == "index_failed"
    assert refreshed.index_error == "Qdrant 写入失败。"
    assert refreshed.normalized_path is not None
    assert Path(refreshed.normalized_path).exists()
    assert len(jobs) == 1
    assert jobs[0].status == "completed"
