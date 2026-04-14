from fastapi import APIRouter

from ..models import SourceRecord
from ..services.seed_projects import SEED_PROJECT, SEED_SOURCES


router = APIRouter(prefix="/api/projects/{project_id}/sources", tags=["sources"])


@router.get("", response_model=list[SourceRecord])
def list_sources(project_id: str) -> list[SourceRecord]:
    if project_id != SEED_PROJECT.id:
        return []

    return SEED_SOURCES
