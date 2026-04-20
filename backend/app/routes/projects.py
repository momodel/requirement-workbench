from fastapi import APIRouter, HTTPException, Request, status

from ..models import CreateProjectRequest, ProjectSummary


router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
def list_projects(request: Request) -> list[ProjectSummary]:
    return request.app.state.services.catalog.list_projects()


@router.post("", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_project(request: Request, payload: CreateProjectRequest) -> ProjectSummary:
    return request.app.state.services.catalog.create_project(payload)


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: str, request: Request) -> ProjectSummary:
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project
