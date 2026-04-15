from fastapi import APIRouter, HTTPException

from ..models import ProjectSummary
from ..services.project_catalog import create_project, get_project, list_projects


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
def list_projects_route() -> list[ProjectSummary]:
    return list_projects()


@router.post("", response_model=ProjectSummary)
def create_project_route(payload: dict) -> ProjectSummary:
    return create_project(
        name=payload.get("name", "未命名项目"),
        summary=payload.get("summary", ""),
        scenario_type=payload.get("scenario_type", "general-requirement")
    )


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project_route(project_id: str) -> ProjectSummary:
    project = get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

    return project
