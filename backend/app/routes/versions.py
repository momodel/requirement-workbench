from fastapi import APIRouter

from ..models import StateItem
from ..services.project_catalog import list_versions


router = APIRouter(prefix="/api/projects/{project_id}/versions", tags=["versions"])


@router.get("", response_model=list[StateItem])
def list_versions_route(project_id: str) -> list[StateItem]:
    return list_versions(project_id)
