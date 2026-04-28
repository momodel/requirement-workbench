from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, WebSocket

from ..models import MobileVoiceBootstrap, ProviderIssue


router = APIRouter(prefix="/api/projects/{project_id}/mobile-voice", tags=["mobile-voice"])


async def _send_ws_error(
    websocket: WebSocket,
    *,
    provider: str,
    message: str,
    code: int,
) -> None:
    try:
        await websocket.accept()
    except RuntimeError:
        pass
    await websocket.send_json(
        {
            "type": "error",
            "provider": provider,
            "message": message,
        }
    )
    await websocket.close(code=code)


@router.get("/bootstrap", response_model=MobileVoiceBootstrap)
def get_mobile_voice_bootstrap(project_id: str, request: Request) -> MobileVoiceBootstrap:
    try:
        return request.app.state.services.mobile_voice.get_bootstrap(project_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.websocket("/ws")
async def mobile_voice_ws(project_id: str, websocket: WebSocket) -> None:
    try:
        await websocket.app.state.services.realtime_voice_bridge.serve(websocket, project_id)
    except LookupError as exc:
        await _send_ws_error(
            websocket,
            provider="VOICE_ROUND",
            message=str(exc),
            code=4404,
        )
    except ProviderIssue as exc:
        await _send_ws_error(
            websocket,
            provider=exc.provider,
            message=exc.message,
            code=4403,
        )
