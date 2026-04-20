from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse

from ..models import ArtifactGenerateRequest, ArtifactRecord, ProviderIssue


router = APIRouter(prefix="/api/projects/{project_id}/artifacts", tags=["artifacts"])


def with_public_preview_url(artifact: ArtifactRecord, request: Request) -> ArtifactRecord:
    if not artifact.preview_url or artifact.preview_url.startswith("http"):
        return artifact

    return artifact.model_copy(
        update={"preview_url": f"{str(request.base_url).rstrip('/')}{artifact.preview_url}"}
    )


@router.get("", response_model=list[ArtifactRecord])
def list_artifacts(project_id: str, request: Request) -> list[ArtifactRecord]:
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return [
        with_public_preview_url(artifact, request)
        for artifact in request.app.state.services.catalog.list_artifacts(project_id)
    ]


@router.post("/generate", response_model=ArtifactRecord)
async def generate_artifact(
    project_id: str,
    payload: ArtifactGenerateRequest,
    request: Request,
) -> ArtifactRecord:
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        services.agent_runtime.ensure_available()
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    state = services.project_state.get_project_state(project_id)
    try:
        artifact = await services.artifact_generation.generate_from_model(
            project=project,
            state=state,
            artifact_type=payload.artifact_type,
            agent_runtime=services.agent_runtime,
        )
        services.project_state.create_artifact_version(
            project_id=project_id,
            artifact_title=artifact.title,
            artifact_type=artifact.artifact_type,
        )
        return with_public_preview_url(artifact, request)
    except ProviderIssue as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get("/{artifact_id}/preview")
def preview_artifact(project_id: str, artifact_id: str, request: Request):
    artifact = request.app.state.services.catalog.get_artifact(project_id, artifact_id)
    if not artifact or artifact.content_format != "html" or not artifact.storage_path:
        raise HTTPException(status_code=404, detail="Artifact preview not found")

    path = Path(artifact.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(path)
