from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from ..models import ProviderIssue


router = APIRouter(prefix="/api/projects/{project_id}/knowledge-base", tags=["knowledge-base"])


@router.get("")
def get_project_knowledge_base(project_id: str, request: Request):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    readiness = services.evidence_runtime.get_project_readiness(project_id)
    knowledge_base = services.catalog.get_knowledge_base(
        project_id=project_id,
        provider=readiness.provider,
    )
    sources = services.catalog.list_sources(project_id)
    chunks = services.catalog.list_source_chunks(project_id=project_id)
    indexed_chunk_count = sum(1 for chunk in chunks if chunk.embedding_status == "indexed")

    return {
        "project_id": project_id,
        "knowledge_base": knowledge_base.model_dump() if knowledge_base else None,
        "readiness": readiness.model_dump(),
        "source_count": len(sources),
        "chunk_count": len(chunks),
        "indexed_chunk_count": indexed_chunk_count,
    }


@router.post("/init", status_code=status.HTTP_201_CREATED)
def init_project_knowledge_base(project_id: str, request: Request):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        record = services.evidence_runtime.ensure_project_knowledge_base(project_id)
        for source in services.catalog.list_sources(project_id):
            if source.normalize_status != "parsed":
                continue
            if source.index_status == "indexed":
                continue
            services.evidence_runtime.reindex_source(project_id, source.id)
        return record
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
