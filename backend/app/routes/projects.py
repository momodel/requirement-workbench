from fastapi import APIRouter, HTTPException, Request, status

from ..models import CreateProjectRequest, ProjectSummary, ProviderIssue


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


@router.delete("/{project_id}", status_code=status.HTTP_200_OK)
def delete_project(project_id: str, request: Request) -> dict[str, str | bool | None]:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.seed_key:
        raise HTTPException(status_code=409, detail="默认 seed project 不能删除。")

    warning: str | None = None
    try:
        services.evidence_runtime.delete_project(project_id)
    except (ProviderIssue, LookupError, ValueError) as exc:
        warning = str(exc.message if isinstance(exc, ProviderIssue) else exc)

    try:
        deleted = services.catalog.delete_project(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    file_warning = services.catalog.cleanup_project_files(project_id)
    if file_warning:
        warning = f"{warning} {file_warning}".strip() if warning else file_warning

    return {
        "id": deleted.id,
        "name": deleted.name,
        "deleted": True,
        "warning": warning,
    }
