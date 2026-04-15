import json
from datetime import datetime
from uuid import uuid4

from ..db import get_connection
from .agent_runtime import runtime as agent_runtime
from .artifact_generation import generate_artifact
from .notebooklm_service import query as query_evidence
from .project_catalog import get_project
from .project_state import create_version_snapshot, get_state_counts, upsert_state_items


PATCH_EVENT_MAP = {
    "current_understanding": "current_understanding_patch",
    "pending_items": "pending_patch",
    "confirmed_items": "confirmed_patch",
    "conflict_items": "conflict_patch",
    "mvp_items": "mvp_patch",
}


def sse_event(event: str, data: dict) -> dict:
    return {"event": event, "data": data}


def _store_message(
    project_id: str,
    role: str,
    content: str,
    stream_group_id: str,
    source_refs: list[dict[str, str]] | None = None,
) -> None:
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO messages (
              id, project_id, role, content, source_refs_json, created_at, stream_group_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"msg-{uuid4().hex[:8]}",
                project_id,
                role,
                content,
                json.dumps(source_refs or [], ensure_ascii=False),
                datetime.now().isoformat(),
                stream_group_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _patch_payload(project_id: str, items: list[dict[str, str] | object]) -> dict:
    created_at = datetime.now().isoformat()
    return {
        "project_id": project_id,
        "op": "upsert",
        "items": [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in items
        ],
        "event_id": f"evt-{uuid4().hex[:8]}",
        "created_at": created_at,
    }


def run_chat_round(
    *,
    project_id: str,
    message: str,
    selected_source_ids: list[str] | None = None,
    request_artifact_types: list[str] | None = None,
    client_context: dict | None = None,
):
    del client_context

    project = get_project(project_id)
    if project is None:
        raise ValueError(f"Unknown project: {project_id}")

    stream_group_id = f"stream-{uuid4().hex[:8]}"
    _store_message(project_id, "user", message, stream_group_id)

    evidence = query_evidence(
        project_id=project_id,
        question=message or "空输入",
        selected_source_ids=selected_source_ids,
    )
    response = agent_runtime.respond(
        project_summary=project.summary,
        message=message or "空输入",
        evidence_summary=evidence.summary,
        citations=evidence.citations,
        current_state_counts=get_state_counts(project_id),
        request_artifact_types=request_artifact_types,
    )

    _store_message(
        project_id,
        "assistant",
        response.message,
        stream_group_id,
        source_refs=response.citations,
    )

    for chunk in [part.strip() for part in response.message.split("。") if part.strip()]:
        yield sse_event("message_chunk", {"project_id": project_id, "text": f"{chunk}。"})

    if response.citations:
        yield sse_event(
            "citations",
            {
                "project_id": project_id,
                "items": response.citations,
                "event_id": f"evt-{uuid4().hex[:8]}",
                "created_at": datetime.now().isoformat(),
            },
        )

    for category, items in response.state_patches.items():
        persisted = upsert_state_items(
            project_id=project_id,
            category=category,
            items=items,
        )
        yield sse_event(PATCH_EVENT_MAP[category], _patch_payload(project_id, persisted))

    generated_artifacts = [
        generate_artifact(project_id, artifact_type)
        for artifact_type in response.artifact_requests
    ]
    if generated_artifacts:
        yield sse_event("artifact_patch", _patch_payload(project_id, generated_artifacts))

    version_item = create_version_snapshot(
        project_id=project_id,
        trigger_kind="chat-round",
        summary=response.version_summary or "完成一次聊天轮次。",
    )
    yield sse_event("version_patch", _patch_payload(project_id, [version_item]))
    yield sse_event("done", {"project_id": project_id})
