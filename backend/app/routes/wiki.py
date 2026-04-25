from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import (
    ProviderIssue,
    WikiMaintenanceResult,
    WikiPage,
    WikiPageMeta,
    WikiRecord,
)


router = APIRouter(prefix="/api/projects/{project_id}/wiki", tags=["wiki"])


@router.get("", response_model=WikiRecord)
def get_wiki_record(project_id: str, request: Request) -> WikiRecord:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return services.wiki_runtime.ensure_project_wiki(project_id)
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/pages", response_model=list[WikiPageMeta])
def list_wiki_pages(project_id: str, request: Request) -> list[WikiPageMeta]:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    services.wiki_runtime.ensure_project_wiki(project_id)
    return services.wiki_runtime.list_pages(project_id)


@router.get("/pages/{slug}", response_model=WikiPage)
def get_wiki_page(project_id: str, slug: str, request: Request) -> WikiPage:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return services.wiki_runtime.read_page(project_id, slug)
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/maintain", response_model=WikiMaintenanceResult)
async def trigger_wiki_maintenance(
    project_id: str,
    request: Request,
    probe: bool = Query(default=False),
    source_id: str | None = Query(default=None),
    version_summary: str | None = Query(default=None),
) -> WikiMaintenanceResult:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    services.wiki_runtime.ensure_project_wiki(project_id)

    try:
        if probe:
            return await services.wiki_runtime.run_health_probe(project_id)
        if source_id:
            return await services.wiki_runtime.maintain_after_ingest(project_id, source_id)
        return await services.wiki_runtime.maintain_after_checkpoint(
            project_id, version_summary
        )
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
