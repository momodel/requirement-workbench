from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    GlobalReadiness,
    ProjectReadiness,
    ProviderReadiness,
)


router = APIRouter(tags=["readiness"])


def _with_audio_detail(readiness: ProviderReadiness, *, sources) -> ProviderReadiness:
    processing_count = sum(
        1
        for source in sources
        if source.source_kind == "audio" and source.normalize_status == "processing"
    )
    failed_count = sum(
        1
        for source in sources
        if source.source_kind == "audio" and source.normalize_status in {"failed", "error"}
    )

    detail_parts: list[str] = []
    if readiness.detail:
        detail_parts.append(readiness.detail)
    detail_parts.append(f"processing_audio_sources={processing_count}")
    detail_parts.append(f"failed_audio_sources={failed_count}")
    return readiness.model_copy(update={"detail": "; ".join(detail_parts)})


@router.get("/api/providers/readiness", response_model=GlobalReadiness)
def get_global_readiness(request: Request) -> GlobalReadiness:
    services = request.app.state.services
    return GlobalReadiness(
        claude=services.agent_runtime.get_readiness(),
        evidence=services.evidence_runtime.get_global_readiness(),
        object_storage=services.object_storage.get_readiness(),
        audio_transcription=services.audio_transcription.get_readiness(),
    )


@router.get("/api/projects/{project_id}/readiness", response_model=ProjectReadiness)
def get_project_readiness(project_id: str, request: Request) -> ProjectReadiness:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    claude = services.agent_runtime.get_readiness()
    evidence = services.evidence_runtime.get_project_readiness(project_id, claude)
    knowledge_base = services.catalog.get_knowledge_base(
        project_id=project_id,
        provider=evidence.provider,
    )
    sources = services.catalog.list_sources(project_id)
    return ProjectReadiness(
        project_id=project_id,
        claude=claude,
        evidence=evidence,
        knowledge_base=knowledge_base,
        object_storage=_with_audio_detail(
            services.object_storage.get_readiness(),
            sources=sources,
        ),
        audio_transcription=_with_audio_detail(
            services.audio_transcription.get_readiness(),
            sources=sources,
        ),
    )
