from fastapi import APIRouter

from ..models import ProjectState
from ..services.project_state import get_project_state


router = APIRouter(prefix="/api/projects/{project_id}/state", tags=["state"])


@router.get("", response_model=ProjectState)
def get_state(project_id: str) -> ProjectState:
    return get_project_state(project_id)
