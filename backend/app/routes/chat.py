import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..services.agent_runtime import MockClaudeAgentRuntime


router = APIRouter(prefix="/api/projects/{project_id}/chat", tags=["chat"])
runtime = MockClaudeAgentRuntime()


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def stream_chat(project_id: str, message: str = "") -> StreamingResponse:
    response = runtime.respond(message or "空输入")

    def event_stream():
        for chunk in response.message.split("。"):
            if not chunk:
                continue
            yield sse_event("message_chunk", {"project_id": project_id, "text": f"{chunk}。"})

        yield sse_event("done", {"project_id": project_id})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
