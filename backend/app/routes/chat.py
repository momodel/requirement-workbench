from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from ..models import ChatStreamRequest
from ..services.project_catalog import now_iso


router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class AnswerQuestionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_labels: list[str] = Field(default_factory=list)
    free_text: str | None = None


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


@router.post("/questions/{question_id}/answer")
async def answer_question(
    project_id: str,
    question_id: str,
    payload: AnswerQuestionRequest,
    request: Request,
) -> dict:
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    registry = request.app.state.services.agent_runtime.question_registry
    accepted = registry.resolve(
        project_id,
        question_id,
        {
            "selected_labels": list(payload.selected_labels),
            "free_text": payload.free_text,
        },
    )
    if not accepted:
        raise HTTPException(
            status_code=404,
            detail="该提问不存在或已超时；请刷新对话以查看最新状态。",
        )
    return {"status": "accepted"}
