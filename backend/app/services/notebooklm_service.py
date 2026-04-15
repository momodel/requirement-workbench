from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ..db import get_connection


@dataclass
class EvidenceResult:
    summary: str
    citations: list[dict[str, str]]


class EvidenceRuntime(Protocol):
    def query(
        self,
        *,
        project_id: str,
        question: str,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult: ...


def get_notebook_binding(project_id: str) -> dict | None:
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT project_id, notebook_id, provider, sync_status, last_synced_at
            FROM notebook_bindings
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return {
        "project_id": row["project_id"],
        "notebook_id": row["notebook_id"],
        "provider": row["provider"],
        "sync_status": row["sync_status"],
        "last_synced_at": row["last_synced_at"],
    }


def ensure_notebook_binding(project_id: str) -> dict:
    existing = get_notebook_binding(project_id)
    if existing is not None:
        return existing

    binding = {
        "project_id": project_id,
        "notebook_id": f"notebook-{project_id}",
        "provider": "notebooklm",
        "sync_status": "pending",
        "last_synced_at": None,
    }

    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO notebook_bindings (
              project_id, notebook_id, provider, sync_status, last_synced_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                binding["project_id"],
                binding["notebook_id"],
                binding["provider"],
                binding["sync_status"],
                binding["last_synced_at"],
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return binding


def mark_sync_status(project_id: str, sync_status: str) -> dict:
    binding = ensure_notebook_binding(project_id)
    last_synced_at = datetime.now().isoformat() if sync_status == "synced" else binding["last_synced_at"]

    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE notebook_bindings
            SET sync_status = ?, last_synced_at = ?
            WHERE project_id = ?
            """,
            (sync_status, last_synced_at, project_id),
        )
        connection.commit()
    finally:
        connection.close()

    updated = get_notebook_binding(project_id)
    return updated if updated is not None else binding


def _mark_source_sync(source_id: str, sync_status: str) -> None:
    connection = get_connection()
    try:
        connection.execute(
            "UPDATE sources SET sync_status = ? WHERE id = ?",
            (sync_status, source_id),
        )
        connection.commit()
    finally:
        connection.close()


def import_source(
    *,
    project_id: str,
    source_id: str,
    normalized_path: str,
    source_name: str,
) -> dict:
    ensure_notebook_binding(project_id)
    path = Path(normalized_path)
    if not path.exists():
        _mark_source_sync(source_id, "failed")
        mark_sync_status(project_id, "degraded")
        raise FileNotFoundError(f"Normalized source not found: {source_name}")

    _mark_source_sync(source_id, "synced")
    binding = mark_sync_status(project_id, "synced")
    return {
        "project_id": project_id,
        "source_id": source_id,
        "source_name": source_name,
        "binding": binding,
    }


def _list_queryable_sources(
    *,
    project_id: str,
    selected_source_ids: list[str] | None,
) -> list[dict[str, str | None]]:
    connection = get_connection()
    try:
        if selected_source_ids:
            placeholders = ",".join("?" for _ in selected_source_ids)
            rows = connection.execute(
                f"""
                SELECT id, name, normalized_path, parse_summary, sync_status
                FROM sources
                WHERE project_id = ? AND id IN ({placeholders})
                ORDER BY created_at, id
                """,
                (project_id, *selected_source_ids),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, name, normalized_path, parse_summary, sync_status
                FROM sources
                WHERE project_id = ?
                ORDER BY created_at, id
                LIMIT 3
                """,
                (project_id,),
            ).fetchall()
    finally:
        connection.close()

    return [
        {
            "id": row["id"],
            "name": row["name"],
            "normalized_path": row["normalized_path"],
            "parse_summary": row["parse_summary"],
            "sync_status": row["sync_status"],
        }
        for row in rows
    ]


class NotebookLMService:
    def query(
        self,
        *,
        project_id: str,
        question: str,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        ensure_notebook_binding(project_id)
        sources = _list_queryable_sources(
            project_id=project_id,
            selected_source_ids=selected_source_ids,
        )

        citations: list[dict[str, str]] = []
        summaries: list[str] = []
        for source in sources:
            normalized_path = source["normalized_path"]
            if normalized_path and Path(normalized_path).exists():
                if source["sync_status"] != "synced":
                    import_source(
                        project_id=project_id,
                        source_id=str(source["id"]),
                        normalized_path=normalized_path,
                        source_name=str(source["name"]),
                    )
                excerpt = Path(normalized_path).read_text(encoding="utf-8").strip().splitlines()
                quote = " ".join(line.strip() for line in excerpt[1:4] if line.strip())[:160]
            else:
                quote = str(source["parse_summary"] or "")

            summaries.append(str(source["parse_summary"] or ""))
            citations.append(
                {
                    "source_id": str(source["id"]),
                    "source_name": str(source["name"]),
                    "excerpt": str(source["parse_summary"] or ""),
                    "quote": quote,
                }
            )

        joined_summary = "；".join(item for item in summaries if item)
        summary = f"基于当前资料，{question}。证据摘要：{joined_summary or '暂无可用资料，需要补充来源。'}"
        return EvidenceResult(summary=summary, citations=citations)

MockNotebookLMService = NotebookLMService
service = NotebookLMService()


def query(
    *,
    project_id: str,
    question: str,
    selected_source_ids: list[str] | None = None,
) -> EvidenceResult:
    return service.query(
        project_id=project_id,
        question=question,
        selected_source_ids=selected_source_ids,
    )
