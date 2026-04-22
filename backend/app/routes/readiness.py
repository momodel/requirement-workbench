from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from ..models import (
    BindNotebookRequest,
    CreateNotebookRequest,
    GlobalReadiness,
    ProjectReadiness,
    ProviderIssue,
)


router = APIRouter(tags=["readiness"])


@router.get("/api/providers/readiness", response_model=GlobalReadiness)
def get_global_readiness(request: Request) -> GlobalReadiness:
    claude = request.app.state.services.agent_runtime.get_readiness()
    evidence = request.app.state.services.evidence_runtime.get_global_readiness()
    return GlobalReadiness(claude=claude, evidence=evidence)


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
    return ProjectReadiness(
        project_id=project_id,
        claude=claude,
        evidence=evidence,
        knowledge_base=knowledge_base,
    )


@router.get("/api/projects/{project_id}/notebook-binding")
def get_notebook_binding(project_id: str, request: Request):
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    binding = request.app.state.services.catalog.get_notebook_binding(project_id)
    if not binding:
        raise HTTPException(status_code=404, detail="Notebook binding not found")
    return binding


@router.get("/api/projects/{project_id}/notebook-library")
def get_project_notebook_library(project_id: str, request: Request):
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return request.app.state.services.notebooklm.list_library()
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/api/projects/{project_id}/notebook-binding",
    status_code=status.HTTP_201_CREATED,
)
def bind_project_notebook(project_id: str, payload: BindNotebookRequest, request: Request):
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return request.app.state.services.notebooklm.bind_project_notebook(project_id, payload)
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post(
    "/api/projects/{project_id}/notebook-create-and-bind",
    status_code=status.HTTP_201_CREATED,
)
def create_and_bind_project_notebook(
    project_id: str,
    payload: CreateNotebookRequest,
    request: Request,
):
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        return request.app.state.services.notebooklm.create_and_bind_project_notebook(project_id, payload)
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
