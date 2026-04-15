import json
from datetime import datetime
from uuid import uuid4

from ..db import get_connection
from ..models import ProjectState, StateItem
from .project_catalog import list_versions


CATEGORY_KEYS = (
    "current_understanding",
    "pending_items",
    "confirmed_items",
    "conflict_items",
    "mvp_items",
)


def _serialize_state_item(item: StateItem) -> dict[str, str]:
    return {"id": item.id, "title": item.title, "body": item.body}


def _serialize_project_state(state: ProjectState) -> dict[str, list[dict[str, str]]]:
    return {
        "current_understanding": [_serialize_state_item(item) for item in state.current_understanding],
        "pending_items": [_serialize_state_item(item) for item in state.pending_items],
        "confirmed_items": [_serialize_state_item(item) for item in state.confirmed_items],
        "conflict_items": [_serialize_state_item(item) for item in state.conflict_items],
        "mvp_items": [_serialize_state_item(item) for item in state.mvp_items],
        "versions": [_serialize_state_item(item) for item in state.versions],
        "artifacts": [_serialize_state_item(item) for item in state.artifacts],
    }


def list_state_items(project_id: str, category: str) -> list[StateItem]:
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, title, body
            FROM state_items
            WHERE project_id = ? AND category = ?
            ORDER BY updated_at, id
            """,
            (project_id, category),
        ).fetchall()
    finally:
        connection.close()

    return [StateItem(id=row["id"], title=row["title"], body=row["body"]) for row in rows]


def upsert_state_items(
    *,
    project_id: str,
    category: str,
    items: list[dict[str, str]],
) -> list[StateItem]:
    updated_at = datetime.now().isoformat()
    persisted: list[StateItem] = []
    connection = get_connection()
    try:
        for item in items:
            state_item = StateItem(
                id=item.get("id") or f"{category}-{uuid4().hex[:8]}",
                title=item["title"],
                body=item["body"],
            )
            connection.execute(
                """
                INSERT OR REPLACE INTO state_items (
                  id, project_id, category, title, body, status, source_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state_item.id,
                    project_id,
                    category,
                    state_item.title,
                    state_item.body,
                    "active",
                    json.dumps(item.get("source_ids", []), ensure_ascii=False),
                    updated_at,
                ),
            )
            persisted.append(state_item)
        connection.commit()
    finally:
        connection.close()

    return persisted


def get_state_counts(project_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    connection = get_connection()
    try:
        for category in CATEGORY_KEYS:
            counts[category] = connection.execute(
                "SELECT COUNT(*) FROM state_items WHERE project_id = ? AND category = ?",
                (project_id, category),
            ).fetchone()[0]
    finally:
        connection.close()
    return counts


def create_version_snapshot(project_id: str, trigger_kind: str, summary: str) -> StateItem:
    state = get_project_state(project_id)
    version_id = f"{trigger_kind}-{uuid4().hex[:8]}"
    created_at = datetime.now().isoformat()
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO version_snapshots (
              id, project_id, trigger_kind, summary, state_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                version_id,
                project_id,
                trigger_kind,
                summary,
                json.dumps(_serialize_project_state(state), ensure_ascii=False),
                created_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return StateItem(id=version_id, title=trigger_kind, body=summary)


def get_project_state(project_id: str) -> ProjectState:
    connection = get_connection()
    try:
        state_rows = connection.execute(
            """
            SELECT id, category, title, body
            FROM state_items
            WHERE project_id = ?
            ORDER BY updated_at, id
            """,
            (project_id,),
        ).fetchall()

        artifact_rows = connection.execute(
            """
            SELECT id, title, summary
            FROM demo_artifacts
            WHERE project_id = ?
            ORDER BY created_at
            """,
            (project_id,),
        ).fetchall()
    finally:
        connection.close()

    grouped_rows: dict[str, list[StateItem]] = {category: [] for category in CATEGORY_KEYS}
    for row in state_rows:
        grouped_rows.setdefault(row["category"], []).append(
            StateItem(id=row["id"], title=row["title"], body=row["body"])
        )

    return ProjectState(
        current_understanding=grouped_rows.get("current_understanding", []),
        pending_items=grouped_rows.get("pending_items", []),
        confirmed_items=grouped_rows.get("confirmed_items", []),
        conflict_items=grouped_rows.get("conflict_items", []),
        mvp_items=grouped_rows.get("mvp_items", []),
        versions=list_versions(project_id),
        artifacts=[
            StateItem(id=row["id"], title=row["title"], body=row["summary"])
            for row in artifact_rows
        ],
    )
