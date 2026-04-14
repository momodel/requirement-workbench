from fastapi import APIRouter

from ..models import ArtifactRecord


router = APIRouter(prefix="/api/projects/{project_id}/artifacts", tags=["artifacts"])


@router.get("", response_model=list[ArtifactRecord])
def list_artifacts(project_id: str) -> list[ArtifactRecord]:
    return []
