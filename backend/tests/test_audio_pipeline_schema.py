import sqlite3
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import (
    CreateProjectRequest,
    GlobalReadiness,
    ProjectReadiness,
    ProviderReadiness,
)
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


def test_readiness_models_accept_audio_provider_slots() -> None:
    ready = ProviderReadiness(
        provider="PROVIDER",
        status="ready",
        summary="provider is ready",
    )

    global_readiness = GlobalReadiness(
        claude=ready,
        evidence=ready,
        object_storage=ready,
        audio_transcription=ready,
    )
    project_readiness = ProjectReadiness(
        project_id="project-1",
        claude=ready,
        evidence=ready,
        knowledge_base=None,
        object_storage=ready,
        audio_transcription=ready,
    )

    assert global_readiness.object_storage == ready
    assert global_readiness.audio_transcription == ready
    assert project_readiness.object_storage == ready
    assert project_readiness.audio_transcription == ready


def test_init_db_creates_source_processing_jobs_table(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(source_processing_jobs)"
            ).fetchall()
        }
    finally:
        connection.close()

    assert {
        "id",
        "project_id",
        "source_id",
        "job_type",
        "status",
        "provider",
        "provider_job_id",
        "attempt_count",
        "last_error",
        "created_at",
        "updated_at",
    }.issubset(columns)


def test_project_catalog_can_create_get_list_and_update_source_processing_job(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="音频项目",
            scenario_type="general",
            summary="验证音频任务账本",
        )
    )
    source = catalog.create_source(
        project_id=project.id,
        name="call.mp3",
        source_kind="audio",
        upload_kind="file",
        storage_path=str(settings.projects_dir / project.id / "sources" / "call.mp3"),
        normalized_path=None,
        index_input_mode=None,
        normalize_status="processing",
        normalize_summary=None,
        index_status="pending",
        index_error=None,
    )

    created = catalog.create_source_processing_job(
        project_id=project.id,
        source_id=source.id,
        job_type="audio_transcription",
        provider="ALIYUN_FILETRANS",
        status="processing",
        provider_job_id=None,
        attempt_count=1,
        last_error=None,
    )
    fetched = catalog.get_source_processing_job(created.id)
    listed = catalog.list_source_processing_jobs(source_id=source.id)
    updated = catalog.update_source_processing_job(
        job_id=created.id,
        status="failed",
        provider_job_id="task-123",
        attempt_count=2,
        last_error="Aliyun timeout",
    )
    refetched = catalog.get_source_processing_job(created.id)

    assert created.status == "processing"
    assert fetched is not None
    assert fetched.id == created.id
    assert len(listed) == 1
    assert listed[0].id == created.id
    assert listed[0].status == "processing"
    assert updated.status == "failed"
    assert updated.provider_job_id == "task-123"
    assert updated.attempt_count == 2
    assert updated.last_error == "Aliyun timeout"
    assert refetched is not None
    assert refetched.status == "failed"
    assert refetched.provider_job_id == "task-123"
