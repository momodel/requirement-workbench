from fastapi import APIRouter, HTTPException

from ..models import ProjectSummary
from ..services.seed_projects import SEED_PROJECT


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
def list_projects() -> list[ProjectSummary]:
    return [SEED_PROJECT]


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: str) -> ProjectSummary:
    if project_id != SEED_PROJECT.id:
        raise HTTPException(status_code=404, detail="Project not found")

    return SEED_PROJECT
