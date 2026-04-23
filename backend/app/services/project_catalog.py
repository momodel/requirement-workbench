from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import AppSettings, DEFAULT_SETTINGS
from ..db import connection_scope
from ..models import (
    ArtifactRecord,
    CreateProjectRequest,
    KnowledgeBaseRecord,
    MessageRecord,
    ProjectSummary,
    SourceRecord,
    SourceChunkRecord,
    StateCategory,
    StateItem,
    STATE_CATEGORIES,
)


def now_iso(settings: AppSettings = DEFAULT_SETTINGS) -> str:
    return datetime.now(ZoneInfo(settings.default_timezone)).isoformat()


def source_chunk_content_hash(content: str, locator_json: str | None) -> str:
    return hashlib.sha256(
        f"{content}\n{locator_json or ''}".encode("utf-8")
    ).hexdigest()


class ProjectCatalog:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    @staticmethod
    def _build_source_record(
        *,
        source_id: str,
        project_id: str,
        name: str,
        source_kind: str,
        upload_kind: str,
        storage_path: str | None,
        normalized_path: str | None,
        index_input_mode: str | None,
        normalize_status: str,
        normalize_summary: str | None,
        index_status: str,
        index_error: str | None,
        created_at: str,
    ) -> SourceRecord:
        return SourceRecord(
            id=source_id,
            project_id=project_id,
            name=name,
            source_kind=source_kind,
            upload_kind=upload_kind,
            storage_path=storage_path,
            normalized_path=normalized_path,
            index_input_mode=index_input_mode,
            normalize_status=normalize_status,
            normalize_summary=normalize_summary,
            index_status=index_status,
            index_error=index_error,
            created_at=created_at,
        )

    @staticmethod
    def _knowledge_base_from_row(row: dict | None) -> KnowledgeBaseRecord | None:
        if not row:
            return None
        return KnowledgeBaseRecord.model_validate(dict(row))

    @staticmethod
    def _source_chunk_from_row(row: dict) -> SourceChunkRecord:
        return SourceChunkRecord.model_validate(dict(row))

    @staticmethod
    def _validate_source_chunk_ownership(
        *,
        connection,
        project_id: str,
        source_id: str,
        chunks: list[dict],
    ) -> None:
        source_row = connection.execute(
            """
            SELECT project_id
            FROM sources
            WHERE id = ?
            """,
            (source_id,),
        ).fetchone()
        if not source_row:
            raise LookupError("Source not found")
        if source_row["project_id"] != project_id:
            raise ValueError("source_id does not belong to the provided project_id")

        knowledge_base_ids = {
            knowledge_base_id
            for chunk in chunks
            if (knowledge_base_id := chunk.get("knowledge_base_id")) is not None
        }
        knowledge_base_projects = {}
        if knowledge_base_ids:
            rows = connection.execute(
                f"""
                SELECT id, project_id
                FROM knowledge_bases
                WHERE id IN ({",".join("?" for _ in knowledge_base_ids)})
                """,
                tuple(knowledge_base_ids),
            ).fetchall()
            knowledge_base_projects = {
                row["id"]: row["project_id"] for row in rows
            }

        for chunk in chunks:
            chunk_project_id = chunk.get("project_id")
            if chunk_project_id is not None and chunk_project_id != project_id:
                raise ValueError("chunk project_id does not match the provided project_id")

            chunk_source_id = chunk.get("source_id")
            if chunk_source_id is not None and chunk_source_id != source_id:
                raise ValueError("chunk source_id does not match the provided source_id")

            knowledge_base_id = chunk.get("knowledge_base_id")
            if knowledge_base_id is None:
                continue
            knowledge_base_project_id = knowledge_base_projects.get(knowledge_base_id)
            if knowledge_base_project_id is None:
                raise LookupError("Knowledge base not found")
            if knowledge_base_project_id != project_id:
                raise ValueError(
                    "knowledge_base_id does not belong to the provided project_id"
                )

    def list_projects(self) -> list[ProjectSummary]:
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, name, scenario_type, summary, status, created_at, updated_at, seed_key
                FROM projects
                ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC
                """
            ).fetchall()
        return [ProjectSummary.model_validate(dict(row)) for row in rows]

    def get_project(self, project_id: str) -> ProjectSummary | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, name, scenario_type, summary, status, created_at, updated_at, seed_key
                FROM projects
                WHERE id = ?
                """,
                (project_id,),
            ).fetchone()
        return ProjectSummary.model_validate(dict(row)) if row else None

    def create_project(self, payload: CreateProjectRequest) -> ProjectSummary:
        project_id = f"project-{uuid.uuid4().hex[:10]}"
        timestamp = now_iso(self.settings)
        project = ProjectSummary(
            id=project_id,
            name=payload.name,
            scenario_type=payload.scenario_type,
            summary=payload.summary,
            status="active",
            created_at=timestamp,
            updated_at=timestamp,
            seed_key=None,
        )

        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO projects (id, name, scenario_type, summary, status, created_at, updated_at, seed_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project.id,
                    project.name,
                    project.scenario_type,
                    project.summary,
                    project.status,
                    project.created_at,
                    project.updated_at,
                    project.seed_key,
                ),
            )
        return project

    def upsert_project(self, project: ProjectSummary) -> None:
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO projects (id, name, scenario_type, summary, status, created_at, updated_at, seed_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name = excluded.name,
                  scenario_type = excluded.scenario_type,
                  summary = excluded.summary,
                  status = excluded.status,
                  created_at = excluded.created_at,
                  updated_at = excluded.updated_at,
                  seed_key = excluded.seed_key
                """,
                (
                    project.id,
                    project.name,
                    project.scenario_type,
                    project.summary,
                    project.status,
                    project.created_at,
                    project.updated_at,
                    project.seed_key,
                ),
            )

    def create_source(
        self,
        *,
        project_id: str,
        name: str,
        source_kind: str,
        upload_kind: str,
        storage_path: str | None,
        normalized_path: str | None,
        index_input_mode: str | None,
        normalize_status: str,
        normalize_summary: str | None,
        index_status: str,
        index_error: str | None,
    ) -> SourceRecord:
        source = self._build_source_record(
            source_id=f"src-{uuid.uuid4().hex[:10]}",
            project_id=project_id,
            name=name,
            source_kind=source_kind,
            upload_kind=upload_kind,
            storage_path=storage_path,
            normalized_path=normalized_path,
            index_input_mode=index_input_mode,
            normalize_status=normalize_status,
            normalize_summary=normalize_summary,
            index_status=index_status,
            index_error=index_error,
            created_at=now_iso(self.settings),
        )
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO sources (
                  id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
                  notebook_import_mode, parse_status, parse_summary, sync_status, sync_error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source.id,
                    source.project_id,
                    source.name,
                    source.source_kind,
                    source.upload_kind,
                    source.storage_path,
                    source.normalized_path,
                    index_input_mode,
                    normalize_status,
                    normalize_summary,
                    index_status,
                    index_error,
                    source.created_at,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (source.created_at, project_id),
            )
        return source

    def list_sources(self, project_id: str) -> list[SourceRecord]:
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
                       notebook_import_mode, parse_status, parse_summary, sync_status, sync_error, created_at
                FROM sources
                WHERE project_id = ?
                ORDER BY datetime(created_at) ASC
                """,
                (project_id,),
            ).fetchall()
        return [SourceRecord.model_validate(dict(row)) for row in rows]

    def get_source(self, source_id: str) -> SourceRecord | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
                       notebook_import_mode, parse_status, parse_summary, sync_status, sync_error, created_at
                FROM sources
                WHERE id = ?
                """,
                (source_id,),
            ).fetchone()
        return SourceRecord.model_validate(dict(row)) if row else None

    def delete_source(self, source_id: str) -> SourceRecord:
        source = self.get_source(source_id)
        if not source:
            raise LookupError("Source not found")

        timestamp = now_iso(self.settings)
        for path_value in (source.storage_path, source.normalized_path):
            if not path_value:
                continue
            path = Path(path_value)
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                # 删除资料时以数据库一致性优先，单个文件清理失败不阻断主流程。
                pass

        with connection_scope(self.settings) as connection:
            connection.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, source.project_id),
            )

        return source

    def update_source_index_status(
        self,
        *,
        source_id: str,
        index_status: str,
        index_error: str | None,
    ) -> SourceRecord:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                "SELECT project_id FROM sources WHERE id = ?",
                (source_id,),
            ).fetchone()
            if not row:
                raise LookupError("Source not found")

            connection.execute(
                """
                UPDATE sources
                SET sync_status = ?, sync_error = ?
                WHERE id = ?
                """,
                (index_status, index_error, source_id),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, row["project_id"]),
            )
        updated = self.get_source(source_id)
        if not updated:
            raise LookupError("Source not found after sync update")
        return updated

    def bulk_update_source_index_status(
        self,
        *,
        project_id: str,
        index_status: str,
        index_error: str | None,
    ) -> None:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                UPDATE sources
                SET sync_status = ?, sync_error = ?
                WHERE project_id = ?
                """,
                (index_status, index_error, project_id),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )

    def update_source_sync_status(
        self,
        *,
        source_id: str,
        sync_status: str,
        sync_error: str | None,
    ) -> SourceRecord:
        return self.update_source_index_status(
            source_id=source_id,
            index_status=sync_status,
            index_error=sync_error,
        )

    def bulk_update_source_sync_status(
        self,
        *,
        project_id: str,
        sync_status: str,
        sync_error: str | None,
    ) -> None:
        self.bulk_update_source_index_status(
            project_id=project_id,
            index_status=sync_status,
            index_error=sync_error,
        )

    def upsert_knowledge_base(
        self,
        *,
        project_id: str,
        provider: str,
        external_knowledge_base_id: str,
        display_name: str | None,
        description: str | None,
        status: str,
        status_error: str | None,
    ) -> KnowledgeBaseRecord:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            existing = connection.execute(
                """
                SELECT id, created_at
                FROM knowledge_bases
                WHERE project_id = ? AND provider = ?
                """,
                (project_id, provider),
            ).fetchone()

            record_id = existing["id"] if existing else f"kb-{uuid.uuid4().hex[:10]}"
            created_at = existing["created_at"] if existing else timestamp

            connection.execute(
                """
                INSERT INTO knowledge_bases (
                  id, project_id, provider, external_knowledge_base_id, display_name,
                  description, status, status_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  project_id = excluded.project_id,
                  provider = excluded.provider,
                  external_knowledge_base_id = excluded.external_knowledge_base_id,
                  display_name = excluded.display_name,
                  description = excluded.description,
                  status = excluded.status,
                  status_error = excluded.status_error,
                  updated_at = excluded.updated_at
                """,
                (
                    record_id,
                    project_id,
                    provider,
                    external_knowledge_base_id,
                    display_name,
                    description,
                    status,
                    status_error,
                    created_at,
                    timestamp,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )

        return KnowledgeBaseRecord(
            id=record_id,
            project_id=project_id,
            provider=provider,
            external_knowledge_base_id=external_knowledge_base_id,
            display_name=display_name,
            description=description,
            status=status,
            status_error=status_error,
            created_at=created_at,
            updated_at=timestamp,
        )

    def get_knowledge_base(
        self,
        *,
        project_id: str,
        provider: str,
    ) -> KnowledgeBaseRecord | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, provider, external_knowledge_base_id, display_name,
                       description, status, status_error, created_at, updated_at
                FROM knowledge_bases
                WHERE project_id = ? AND provider = ?
                """,
                (project_id, provider),
            ).fetchone()
        return self._knowledge_base_from_row(row)

    def replace_source_chunks(
        self,
        *,
        project_id: str,
        source_id: str,
        chunks: list[dict],
    ) -> list[SourceChunkRecord]:
        timestamp = now_iso(self.settings)
        records: list[SourceChunkRecord] = []

        for chunk in chunks:
            content = chunk["content"]
            locator_json = chunk.get("locator_json")
            records.append(
                SourceChunkRecord(
                    id=chunk.get("id") or f"chunk-{uuid.uuid4().hex[:10]}",
                    project_id=project_id,
                    source_id=source_id,
                    knowledge_base_id=chunk.get("knowledge_base_id"),
                    chunk_order=int(chunk["chunk_order"]),
                    modality=chunk.get("modality") or "text",
                    content=content,
                    locator_json=locator_json,
                    content_hash=chunk.get("content_hash")
                    or source_chunk_content_hash(content, locator_json),
                    embedding_status=chunk.get("embedding_status") or "pending",
                    index_error=chunk.get("index_error"),
                    indexed_at=chunk.get("indexed_at"),
                    created_at=chunk.get("created_at") or timestamp,
                    updated_at=chunk.get("updated_at") or timestamp,
                )
            )

        with connection_scope(self.settings) as connection:
            self._validate_source_chunk_ownership(
                connection=connection,
                project_id=project_id,
                source_id=source_id,
                chunks=chunks,
            )
            connection.execute(
                """
                DELETE FROM source_chunks
                WHERE project_id = ? AND source_id = ?
                """,
                (project_id, source_id),
            )
            for record in records:
                connection.execute(
                    """
                    INSERT INTO source_chunks (
                      id, project_id, source_id, knowledge_base_id, chunk_order, modality,
                      content, locator_json, content_hash, embedding_status, index_error,
                      indexed_at, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.project_id,
                        record.source_id,
                        record.knowledge_base_id,
                        record.chunk_order,
                        record.modality,
                        record.content,
                        record.locator_json,
                        record.content_hash,
                        record.embedding_status,
                        record.index_error,
                        record.indexed_at,
                        record.created_at,
                        record.updated_at,
                    ),
                )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )

        return records

    def list_source_chunks(
        self,
        *,
        project_id: str,
        source_id: str | None = None,
        knowledge_base_id: str | None = None,
    ) -> list[SourceChunkRecord]:
        where_clauses = ["project_id = ?"]
        parameters: list[str] = [project_id]

        if source_id is not None:
            where_clauses.append("source_id = ?")
            parameters.append(source_id)
        if knowledge_base_id is not None:
            where_clauses.append("knowledge_base_id = ?")
            parameters.append(knowledge_base_id)

        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                f"""
                SELECT id, project_id, source_id, knowledge_base_id, chunk_order, modality,
                       content, locator_json, content_hash, embedding_status, index_error,
                       indexed_at, created_at, updated_at
                FROM source_chunks
                WHERE {' AND '.join(where_clauses)}
                ORDER BY chunk_order ASC, datetime(created_at) ASC, id ASC
                """,
                tuple(parameters),
            ).fetchall()

        return [self._source_chunk_from_row(dict(row)) for row in rows]

    def create_message(
        self,
        *,
        project_id: str,
        role: str,
        content: str,
        source_refs: list[dict] | None = None,
        stream_group_id: str | None = None,
    ) -> str:
        message_id = f"msg-{uuid.uuid4().hex[:10]}"
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO messages (id, project_id, role, content, source_refs_json, created_at, stream_group_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    project_id,
                    role,
                    content,
                    json.dumps(source_refs or [], ensure_ascii=False),
                    timestamp,
                    stream_group_id,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        return message_id

    def list_recent_messages(self, project_id: str, limit: int = 50) -> list[MessageRecord]:
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, role, content, source_refs_json, created_at, stream_group_id
                FROM messages
                WHERE project_id = ?
                ORDER BY datetime(created_at) DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
        messages: list[MessageRecord] = []
        for row in reversed(rows):
            messages.append(
                MessageRecord(
                    id=row["id"],
                    role=row["role"],
                    content=row["content"],
                    source_refs=json.loads(row["source_refs_json"] or "[]"),
                    created_at=row["created_at"],
                    stream_group_id=row["stream_group_id"],
                )
            )
        return messages

    def replace_state_items(
        self,
        project_id: str,
        category: StateCategory,
        items: list[StateItem],
    ) -> None:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            connection.execute(
                "DELETE FROM state_items WHERE project_id = ? AND category = ?",
                (project_id, category),
            )
            for item in items:
                connection.execute(
                    """
                    INSERT INTO state_items (id, project_id, category, title, body, status, source_ids_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        project_id,
                        category,
                        item.title,
                        item.body,
                        item.status,
                        json.dumps(item.source_ids, ensure_ascii=False),
                        item.updated_at or timestamp,
                    ),
                )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )

    def list_state_items(self, project_id: str) -> dict[StateCategory, list[StateItem]]:
        grouped = {category: [] for category in STATE_CATEGORIES}
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, category, title, body, status, source_ids_json, updated_at
                FROM state_items
                WHERE project_id = ?
                ORDER BY datetime(updated_at) DESC
                """,
                (project_id,),
            ).fetchall()
        for row in rows:
            grouped[row["category"]].append(
                StateItem(
                    id=row["id"],
                    title=row["title"],
                    body=row["body"],
                    status=row["status"],
                    category=row["category"],
                    updated_at=row["updated_at"],
                    source_ids=json.loads(row["source_ids_json"] or "[]"),
                )
            )
        return grouped  # type: ignore[return-value]

    def create_version_snapshot(
        self,
        *,
        project_id: str,
        trigger_kind: str,
        summary: str,
        state_json: str,
    ) -> StateItem:
        version_id = f"version-{uuid.uuid4().hex[:10]}"
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO version_snapshots (id, project_id, trigger_kind, summary, state_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (version_id, project_id, trigger_kind, summary, state_json, timestamp),
            )
            connection.execute(
                """
                INSERT INTO state_items (id, project_id, category, title, body, status, source_ids_json, updated_at)
                VALUES (?, ?, 'versions', ?, ?, 'active', '[]', ?)
                """,
                (
                    version_id,
                    project_id,
                    trigger_kind,
                    summary,
                    timestamp,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        return StateItem(
            id=version_id,
            title=trigger_kind,
            body=summary,
            status="active",
            category="versions",
            updated_at=timestamp,
            source_ids=[],
        )

    def list_artifacts(self, project_id: str) -> list[ArtifactRecord]:
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, artifact_type, title, summary, status, content_format,
                       storage_path, body, updated_at
                FROM demo_artifacts
                WHERE project_id = ?
                ORDER BY datetime(updated_at) DESC
                """,
                (project_id,),
            ).fetchall()
        records: list[ArtifactRecord] = []
        for row in rows:
            preview_url = None
            if row["storage_path"] and row["content_format"] == "html":
                preview_url = f"/api/projects/{project_id}/artifacts/{row['id']}/preview"

            records.append(
                ArtifactRecord(
                    id=row["id"],
                    project_id=row["project_id"],
                    artifact_type=row["artifact_type"],
                    title=row["title"],
                    summary=row["summary"],
                    status=row["status"],
                    content_format=row["content_format"],
                    storage_path=row["storage_path"],
                    preview_url=preview_url,
                    body=row["body"],
                    updated_at=row["updated_at"],
                )
            )
        return records

    def get_artifact(self, project_id: str, artifact_id: str) -> ArtifactRecord | None:
        for artifact in self.list_artifacts(project_id):
            if artifact.id == artifact_id:
                return artifact
        return None

    def get_latest_artifact_with_metadata(
        self,
        project_id: str,
        artifact_type: str,
    ) -> tuple[ArtifactRecord, dict] | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, artifact_type, title, summary, status, content_format,
                       storage_path, metadata_json, body, updated_at
                FROM demo_artifacts
                WHERE project_id = ? AND artifact_type = ? AND status = 'generated'
                ORDER BY datetime(updated_at) DESC
                LIMIT 1
                """,
                (project_id, artifact_type),
            ).fetchone()

        if not row:
            return None

        preview_url = None
        if row["storage_path"] and row["content_format"] == "html":
            preview_url = f"/api/projects/{project_id}/artifacts/{row['id']}/preview"

        metadata_json = row["metadata_json"] or "{}"
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            metadata = {}

        artifact = ArtifactRecord(
            id=row["id"],
            project_id=row["project_id"],
            artifact_type=row["artifact_type"],
            title=row["title"],
            summary=row["summary"],
            status=row["status"],
            content_format=row["content_format"],
            storage_path=row["storage_path"],
            preview_url=preview_url,
            body=row["body"],
            updated_at=row["updated_at"],
        )
        return artifact, metadata

    def save_artifact(
        self,
        *,
        project_id: str,
        artifact_type: str,
        title: str,
        summary: str,
        status: str,
        content_format: str,
        storage_path: str | None,
        body: str | None,
        metadata: dict | None = None,
        artifact_id: str | None = None,
    ) -> ArtifactRecord:
        record_id = artifact_id or f"artifact-{uuid.uuid4().hex[:10]}"
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO demo_artifacts (
                  id, project_id, artifact_type, title, summary, status, content_format,
                  storage_path, metadata_json, body, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  title = excluded.title,
                  summary = excluded.summary,
                  status = excluded.status,
                  content_format = excluded.content_format,
                  storage_path = excluded.storage_path,
                  metadata_json = excluded.metadata_json,
                  body = excluded.body,
                  updated_at = excluded.updated_at
                """,
                (
                    record_id,
                    project_id,
                    artifact_type,
                    title,
                    summary,
                    status,
                    content_format,
                    storage_path,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    body,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO state_items (id, project_id, category, title, body, status, source_ids_json, updated_at)
                VALUES (?, ?, 'artifacts', ?, ?, 'active', '[]', ?)
                ON CONFLICT(id) DO UPDATE SET
                  title = excluded.title,
                  body = excluded.body,
                  updated_at = excluded.updated_at
                """,
                (
                    record_id,
                    project_id,
                    title,
                    summary,
                    timestamp,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        preview_url = None
        if storage_path and content_format == "html":
            preview_url = f"/api/projects/{project_id}/artifacts/{record_id}/preview"
        return ArtifactRecord(
            id=record_id,
            project_id=project_id,
            artifact_type=artifact_type,
            title=title,
            summary=summary,
            status=status,
            content_format=content_format,
            storage_path=storage_path,
            preview_url=preview_url,
            body=body,
            updated_at=timestamp,
        )
