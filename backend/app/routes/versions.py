from fastapi import APIRouter, HTTPException, Request

from ..models import StateItem


router = APIRouter(prefix="/api/projects/{project_id}/versions", tags=["versions"])


@router.get("", response_model=list[StateItem])
def list_versions(project_id: str, request: Request) -> list[StateItem]:
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    state = request.app.state.services.project_state.get_project_state(project_id)
    return state.versions
