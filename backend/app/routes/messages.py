from fastapi import APIRouter, HTTPException, Request

from ..models import MessageRecord


router = APIRouter(prefix="/api/projects/{project_id}/messages", tags=["messages"])


@router.get("", response_model=list[MessageRecord])
def list_messages(project_id: str, request: Request) -> list[MessageRecord]:
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return request.app.state.services.catalog.list_recent_messages(project_id)
