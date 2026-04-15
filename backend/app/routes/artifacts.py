from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from ..models import ArtifactRecord
from ..services.artifact_generation import generate_artifact
from ..services.project_catalog import get_artifact, list_artifacts


router = APIRouter(prefix="/api/projects/{project_id}/artifacts", tags=["artifacts"])


@router.get("", response_model=list[ArtifactRecord])
def list_artifacts_route(project_id: str) -> list[ArtifactRecord]:
    return list_artifacts(project_id)


@router.post("/generate", response_model=ArtifactRecord)
def generate_artifact_route(project_id: str, payload: dict) -> ArtifactRecord:
    artifact_type = payload.get("artifact_type", "document")
    return generate_artifact(project_id=project_id, artifact_type=artifact_type)


@router.get("/{artifact_id}/content")
def get_artifact_content_route(project_id: str, artifact_id: str) -> PlainTextResponse:
    artifact = get_artifact(project_id, artifact_id)
    if artifact is None or not artifact.storage_path:
        raise HTTPException(status_code=404, detail="Artifact not found")

    path = Path(artifact.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found")

    media_type = "text/html" if artifact.content_format == "html" else "application/json"
    return PlainTextResponse(path.read_text(encoding="utf-8"), media_type=media_type)
