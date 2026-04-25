from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    GlobalReadiness,
    ProjectReadiness,
)


router = APIRouter(tags=["readiness"])


@router.get("/api/providers/readiness", response_model=GlobalReadiness)
def get_global_readiness(request: Request) -> GlobalReadiness:
    services = request.app.state.services
    claude = services.agent_runtime.get_readiness()
    evidence = services.evidence_runtime.get_global_readiness()
    wiki = services.wiki_runtime.get_global_readiness()
    return GlobalReadiness(claude=claude, evidence=evidence, wiki=wiki)


@router.get("/api/projects/{project_id}/readiness", response_model=ProjectReadiness)
def get_project_readiness(project_id: str, request: Request) -> ProjectReadiness:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    claude = services.agent_runtime.get_readiness()
    evidence = services.evidence_runtime.get_project_readiness(project_id, claude)
    wiki = services.wiki_runtime.get_project_readiness(project_id, claude)
    knowledge_base = services.catalog.get_knowledge_base(
        project_id=project_id,
        provider=evidence.provider,
    )
    return ProjectReadiness(
        project_id=project_id,
        claude=claude,
        evidence=evidence,
        wiki=wiki,
        knowledge_base=knowledge_base,
    )
