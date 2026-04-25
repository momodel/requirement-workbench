from __future__ import annotations

from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue
from .audio_transcription_service import ALIYUN_FILETRANS, AudioTranscriptionService
from .object_storage_service import ObjectStorageService
from .project_catalog import ProjectCatalog
from .runtime_contracts import EvidenceRuntime


class AudioIngestionOrchestrator:
    def __init__(
        self,
        *,
        settings: AppSettings = DEFAULT_SETTINGS,
        catalog: ProjectCatalog,
        object_storage: ObjectStorageService,
        audio_transcription: AudioTranscriptionService,
        evidence_runtime: EvidenceRuntime,
    ) -> None:
        self.settings = settings
        self.catalog = catalog
        self.object_storage = object_storage
        self.audio_transcription = audio_transcription
        self.evidence_runtime = evidence_runtime

    def process_source(self, project_id: str, source_id: str) -> None:
        source = self.catalog.get_source(source_id)
        if source is None:
            raise LookupError("Source not found")
        if source.project_id != project_id:
            raise ValueError("source_id does not belong to the provided project_id")
        if source.source_kind != "audio":
            raise ValueError("AudioIngestionOrchestrator only handles audio sources")
        if not source.storage_path:
            raise ValueError("Audio source has no storage_path")

        job = self.catalog.create_source_processing_job(
            project_id=project_id,
            source_id=source_id,
            job_type="audio_transcription",
            provider=ALIYUN_FILETRANS,
            status="processing",
            provider_job_id=None,
            attempt_count=1,
            last_error=None,
        )

        storage_path = Path(source.storage_path)
        try:
            uploaded = self.object_storage.upload_audio_source(
                project_id=project_id,
                source_id=source_id,
                local_path=storage_path,
            )
            transcription = self.audio_transcription.transcribe_from_url(
                file_url=uploaded.url,
                source_name=source.name,
            )
        except ProviderIssue as exc:
            self.catalog.update_source_processing_job(
                job_id=job.id,
                status="failed",
                provider_job_id=None,
                attempt_count=job.attempt_count,
                last_error=exc.message,
            )
            self.catalog.update_source_normalization(
                source_id=source_id,
                normalized_path=None,
                index_input_mode=None,
                normalize_status="failed",
                normalize_summary=exc.message,
                index_status="normalization_failed",
                index_error=f"资料标准化失败，尚未进入项目知识库。{exc.message}",
            )
            return

        normalized_path = storage_path.with_suffix(".normalized.md")
        normalized_path.write_text(transcription.markdown, encoding="utf-8")
        self.catalog.update_source_processing_job(
            job_id=job.id,
            status="completed",
            provider_job_id=transcription.provider_job_id,
            attempt_count=job.attempt_count,
            last_error=None,
        )
        self.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=str(normalized_path),
            index_input_mode="normalized_text",
            normalize_status="parsed",
            normalize_summary="ASR 已生成转写文本。",
            index_status="pending",
            index_error=None,
        )

        self.catalog.update_source_index_status(
            source_id=source_id,
            index_status="indexing",
            index_error=None,
        )
        try:
            self.evidence_runtime.index_source(project_id, source_id)
        except ProviderIssue as exc:
            self.catalog.update_source_index_status(
                source_id=source_id,
                index_status="index_failed",
                index_error=exc.message,
            )
            return

        self.catalog.update_source_index_status(
            source_id=source_id,
            index_status="indexed",
            index_error=None,
        )
