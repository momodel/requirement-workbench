import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..services.chat_service import run_chat_round


router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def stream_chat(project_id: str, payload: dict | None = None) -> StreamingResponse:
    request = payload or {}
    message = request.get("message", "空输入")
    selected_source_ids = request.get("selected_source_ids")
    request_artifact_types = request.get("request_artifact_types")
    client_context = request.get("client_context")

    def event_stream():
        for event in run_chat_round(
            project_id=project_id,
            message=message,
            selected_source_ids=selected_source_ids,
            request_artifact_types=request_artifact_types,
            client_context=client_context,
        ):
            yield sse_event(event["event"], event["data"])

    return StreamingResponse(event_stream(), media_type="text/event-stream")
