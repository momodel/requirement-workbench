from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    GlobalReadiness,
)


router = APIRouter(tags=["readiness"])


@router.get("/api/providers/readiness", response_model=GlobalReadiness)
def get_global_readiness(request: Request) -> GlobalReadiness:
    claude = request.app.state.services.agent_runtime.get_readiness()
    knowledge_wiki = request.app.state.services.knowledge_wiki.get_global_readiness()
    return GlobalReadiness(claude=claude, knowledge_wiki=knowledge_wiki)


@router.get("/api/projects/{project_id}/readiness")
def get_project_readiness(project_id: str, request: Request):
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    claude = request.app.state.services.agent_runtime.get_readiness()
    return request.app.state.services.knowledge_wiki.get_project_readiness(project, claude)
