from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse


router = APIRouter(prefix="/api/projects/{project_id}/chat-images", tags=["chat-images"])


@router.get("/{image_id}")
def preview_chat_image(project_id: str, image_id: str, request: Request):
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    image_dir = request.app.state.services.settings.projects_dir / project_id / "chat-images" / image_id
    if not image_dir.exists() or not image_dir.is_dir():
        raise HTTPException(status_code=404, detail="Chat image not found")

    candidates = sorted(path for path in image_dir.iterdir() if path.is_file() and path.name.startswith("image."))
    if not candidates:
        raise HTTPException(status_code=404, detail="Chat image file not found")
    return FileResponse(Path(candidates[0]))
