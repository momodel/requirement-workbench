from fastapi import APIRouter, HTTPException, Request

from ..models import ProjectState


router = APIRouter(prefix="/api/projects/{project_id}/state", tags=["state"])


@router.get("", response_model=ProjectState)
def get_state(project_id: str, request: Request) -> ProjectState:
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return request.app.state.services.project_state.get_project_state(project_id)
