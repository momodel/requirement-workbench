from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..models import ChatStreamRequest
from ..services.project_catalog import now_iso


router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def stream_chat(project_id: str, payload: ChatStreamRequest, request: Request) -> StreamingResponse:
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    async def event_stream():
        async for event_type, data in request.app.state.services.chat_service.stream_turn(
            project_id,
            payload,
        ):
            envelope = {
                "project_id": project_id,
                "created_at": now_iso(request.app.state.services.settings),
                **data,
            }
            yield sse_event(event_type, envelope)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
