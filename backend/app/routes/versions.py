from fastapi import APIRouter

from ..models import StateItem
from ..services.seed_projects import SEED_PROJECT, SEED_STATE


router = APIRouter(prefix="/api/projects/{project_id}/versions", tags=["versions"])


@router.get("", response_model=list[StateItem])
def list_versions(project_id: str) -> list[StateItem]:
    if project_id != SEED_PROJECT.id:
        return []

    return SEED_STATE.versions
