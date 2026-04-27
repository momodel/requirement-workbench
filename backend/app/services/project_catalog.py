from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from datetime import datetime, timedelta
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
    SourceProcessingJobRecord,
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
        wiki_sync_status: str | None,
        wiki_error: str | None,
        wiki_maintained_at: str | None,
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
            wiki_sync_status=wiki_sync_status,
            wiki_error=wiki_error,
            wiki_maintained_at=wiki_maintained_at,
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
    def _source_processing_job_from_row(
        row: dict | None,
    ) -> SourceProcessingJobRecord | None:
        if not row:
            return None
        return SourceProcessingJobRecord.model_validate(dict(row))

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

    def delete_project(self, project_id: str) -> ProjectSummary:
        project = self.get_project(project_id)
        if not project:
            raise LookupError("Project not found")
        if project.seed_key:
            raise ValueError("默认 seed project 不能删除。")

        with connection_scope(self.settings) as connection:
            connection.execute(
                "DELETE FROM projects WHERE id = ?",
                (project_id,),
            )

        return project

    def cleanup_project_files(self, project_id: str) -> str | None:
        projects_root = self.settings.projects_dir.resolve()
        project_dir = (self.settings.projects_dir / project_id).resolve()
        try:
            project_dir.relative_to(projects_root)
        except ValueError:
            return "项目目录不在受控 projects 目录内，已跳过文件清理。"

        if not project_dir.exists():
            return None

        try:
            shutil.rmtree(project_dir)
        except OSError as exc:
            return f"项目已从本地数据库删除，但项目目录清理失败：{exc}"

        return None

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
        index_input_mode: str | None = None,
        normalize_status: str | None = None,
        normalize_summary: str | None = None,
        index_status: str | None = None,
        index_error: str | None = None,
        wiki_sync_status: str | None = None,
        wiki_error: str | None = None,
        wiki_maintained_at: str | None = None,
        notebook_import_mode: str | None = None,
        parse_status: str | None = None,
        parse_summary: str | None = None,
        sync_status: str | None = None,
        sync_error: str | None = None,
    ) -> SourceRecord:
        index_input_mode = index_input_mode if index_input_mode is not None else notebook_import_mode
        normalize_status = normalize_status if normalize_status is not None else parse_status or "pending"
        normalize_summary = normalize_summary if normalize_summary is not None else parse_summary
        index_status = index_status if index_status is not None else sync_status or "pending"
        index_error = index_error if index_error is not None else sync_error
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
            wiki_sync_status=wiki_sync_status,
            wiki_error=wiki_error,
            wiki_maintained_at=wiki_maintained_at,
            created_at=now_iso(self.settings),
        )
        with connection_scope(self.settings) as connection:
            connection.execute(
                """
                INSERT INTO sources (
                  id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
                  index_input_mode, normalize_status, normalize_summary, index_status,
                  index_error, wiki_sync_status, wiki_error, wiki_maintained_at,
                  created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    wiki_sync_status,
                    wiki_error,
                    wiki_maintained_at,
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
                SELECT id, project_id, name, source_kind, upload_kind, storage_path,
                       normalized_path, index_input_mode, normalize_status,
                       normalize_summary, index_status, index_error,
                       wiki_sync_status, wiki_error, wiki_maintained_at,
                       created_at
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
                SELECT id, project_id, name, source_kind, upload_kind, storage_path,
                       normalized_path, index_input_mode, normalize_status,
                       normalize_summary, index_status, index_error,
                       wiki_sync_status, wiki_error, wiki_maintained_at,
                       created_at
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
                SET index_status = ?, index_error = ?
                WHERE id = ?
                """,
                (
                    index_status,
                    index_error,
                    source_id,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, row["project_id"]),
            )
        updated = self.get_source(source_id)
        if not updated:
            raise LookupError("Source not found after sync update")
        return updated

    def update_source_normalization(
        self,
        *,
        source_id: str,
        normalized_path: str | None,
        index_input_mode: str | None,
        normalize_status: str,
        normalize_summary: str | None,
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
                SET normalized_path = ?, index_input_mode = ?, normalize_status = ?,
                    normalize_summary = ?, index_status = ?, index_error = ?
                WHERE id = ?
                """,
                (
                    normalized_path,
                    index_input_mode,
                    normalize_status,
                    normalize_summary,
                    index_status,
                    index_error,
                    source_id,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, row["project_id"]),
            )
        updated = self.get_source(source_id)
        if updated is None:
            raise LookupError("Source not found after normalization update")
        return updated

    def update_source_wiki_status(
        self,
        *,
        source_id: str,
        wiki_sync_status: str,
        wiki_error: str | None,
        wiki_maintained_at: str | None = None,
    ) -> SourceRecord:
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
                SET wiki_sync_status = ?, wiki_error = ?, wiki_maintained_at = ?
                WHERE id = ?
                """,
                (
                    wiki_sync_status,
                    wiki_error,
                    wiki_maintained_at,
                    source_id,
                ),
            )
        updated = self.get_source(source_id)
        if not updated:
            raise LookupError("Source not found after wiki update")
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
                SET index_status = ?, index_error = ?
                WHERE project_id = ?
                """,
                (
                    index_status,
                    index_error,
                    project_id,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
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

    def create_source_processing_job(
        self,
        *,
        project_id: str,
        source_id: str,
        job_type: str,
        provider: str,
        status: str,
        provider_job_id: str | None,
        attempt_count: int,
        last_error: str | None,
    ) -> SourceProcessingJobRecord:
        timestamp = now_iso(self.settings)
        record = SourceProcessingJobRecord(
            id=f"job-{uuid.uuid4().hex[:10]}",
            project_id=project_id,
            source_id=source_id,
            job_type=job_type,
            status=status,
            provider=provider,
            provider_job_id=provider_job_id,
            attempt_count=attempt_count,
            last_error=last_error,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with connection_scope(self.settings) as connection:
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
                raise ValueError(
                    "source_id does not belong to the provided project_id"
                )

            connection.execute(
                """
                INSERT INTO source_processing_jobs (
                  id, project_id, source_id, job_type, status, provider,
                  provider_job_id, attempt_count, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.project_id,
                    record.source_id,
                    record.job_type,
                    record.status,
                    record.provider,
                    record.provider_job_id,
                    record.attempt_count,
                    record.last_error,
                    record.created_at,
                    record.updated_at,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        return record

    def get_source_processing_job(
        self,
        job_id: str,
    ) -> SourceProcessingJobRecord | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, source_id, job_type, status, provider,
                       provider_job_id, attempt_count, last_error, created_at, updated_at
                FROM source_processing_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return self._source_processing_job_from_row(row)

    def list_source_processing_jobs(
        self,
        *,
        source_id: str,
    ) -> list[SourceProcessingJobRecord]:
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, source_id, job_type, status, provider,
                       provider_job_id, attempt_count, last_error, created_at, updated_at
                FROM source_processing_jobs
                WHERE source_id = ?
                ORDER BY datetime(updated_at) DESC, datetime(created_at) DESC
                """,
                (source_id,),
            ).fetchall()
        return [
            SourceProcessingJobRecord.model_validate(dict(row))
            for row in rows
        ]

    def get_latest_source_processing_job(
        self,
        *,
        source_id: str,
    ) -> SourceProcessingJobRecord | None:
        jobs = self.list_source_processing_jobs(source_id=source_id)
        return jobs[0] if jobs else None

    def update_source_processing_job(
        self,
        *,
        job_id: str,
        status: str,
        provider_job_id: str | None,
        attempt_count: int,
        last_error: str | None,
    ) -> SourceProcessingJobRecord:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT project_id
                FROM source_processing_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
            if not row:
                raise LookupError("Source processing job not found")

            connection.execute(
                """
                UPDATE source_processing_jobs
                SET status = ?, provider_job_id = ?, attempt_count = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    provider_job_id,
                    attempt_count,
                    last_error,
                    timestamp,
                    job_id,
                ),
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, row["project_id"]),
            )

        updated = self.get_source_processing_job(job_id)
        if updated is None:
            raise LookupError("Source processing job not found")
        return updated

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
            raw_refs = json.loads(row["source_refs_json"] or "[]")
            image_results = []
            source_refs = []
            for reference in raw_refs:
                if isinstance(reference, dict) and "__image_results__" in reference:
                    raw_images = reference.get("__image_results__")
                    if isinstance(raw_images, list):
                        image_results.extend(raw_images)
                else:
                    source_refs.append(reference)
            messages.append(
                MessageRecord(
                    id=row["id"],
                    role=row["role"],
                    content=row["content"],
                    source_refs=source_refs,
                    image_results=image_results,
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

    def append_state_items(
        self,
        project_id: str,
        category: StateCategory,
        items: list[StateItem],
    ) -> None:
        if not items:
            return

        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
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

    def mark_stale_generating_artifacts_failed(self, project_id: str) -> None:
        artifact_timeout = max(
            self.settings.claude_artifact_timeout_seconds,
            getattr(self.settings, "image_generation_timeout_seconds", 0),
        )
        cutoff = datetime.now(ZoneInfo(self.settings.default_timezone)) - timedelta(seconds=artifact_timeout + 30)
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, title, artifact_type, content_format, updated_at
                FROM demo_artifacts
                WHERE project_id = ? AND status = 'generating'
                """,
                (project_id,),
            ).fetchall()
            stale_rows = []
            for row in rows:
                try:
                    updated_at = datetime.fromisoformat(row["updated_at"])
                except (TypeError, ValueError):
                    updated_at = datetime.min.replace(tzinfo=ZoneInfo(self.settings.default_timezone))
                if updated_at < cutoff:
                    stale_rows.append(row)

            for row in stale_rows:
                summary = "交付物生成任务已中断或超时，请重新生成。"
                connection.execute(
                    """
                    UPDATE demo_artifacts
                    SET status = 'failed', summary = ?, storage_path = NULL, body = NULL, updated_at = ?
                    WHERE id = ? AND project_id = ? AND status = 'generating'
                    """,
                    (summary, timestamp, row["id"], project_id),
                )
                connection.execute(
                    """
                    UPDATE state_items
                    SET body = ?, updated_at = ?
                    WHERE id = ? AND project_id = ? AND category = 'artifacts'
                    """,
                    (summary, timestamp, row["id"], project_id),
                )

    def _row_to_artifact(self, project_id: str, row) -> ArtifactRecord:
        preview_url = None
        if row["storage_path"] and row["content_format"] in {"html", "image"}:
            preview_url = f"/api/projects/{project_id}/artifacts/{row['id']}/preview"

        return ArtifactRecord(
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
            revision_number=row["revision_number"] if "revision_number" in row.keys() else 1,
            updated_at=row["updated_at"],
        )

    def list_artifacts(
        self,
        project_id: str,
        *,
        include_history: bool = False,
    ) -> list[ArtifactRecord]:
        self.mark_stale_generating_artifacts_failed(project_id)
        with connection_scope(self.settings) as connection:
            if include_history:
                rows = connection.execute(
                    """
                    SELECT id, project_id, artifact_type, title, summary, status, content_format,
                           storage_path, body, revision_number, updated_at
                    FROM demo_artifacts
                    WHERE project_id = ?
                    ORDER BY artifact_type ASC, revision_number ASC
                    """,
                    (project_id,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT a.id, a.project_id, a.artifact_type, a.title, a.summary, a.status,
                           a.content_format, a.storage_path, a.body, a.revision_number, a.updated_at
                    FROM demo_artifacts a
                    INNER JOIN (
                        SELECT artifact_type, MAX(revision_number) AS max_rev
                        FROM demo_artifacts
                        WHERE project_id = ?
                        GROUP BY artifact_type
                    ) latest
                      ON latest.artifact_type = a.artifact_type
                     AND latest.max_rev = a.revision_number
                    WHERE a.project_id = ?
                    ORDER BY datetime(a.updated_at) DESC
                    """,
                    (project_id, project_id),
                ).fetchall()
        return [self._row_to_artifact(project_id, row) for row in rows]

    def list_artifact_history(
        self,
        project_id: str,
        artifact_type: str,
    ) -> list[ArtifactRecord]:
        self.mark_stale_generating_artifacts_failed(project_id)
        with connection_scope(self.settings) as connection:
            rows = connection.execute(
                """
                SELECT id, project_id, artifact_type, title, summary, status, content_format,
                       storage_path, body, revision_number, updated_at
                FROM demo_artifacts
                WHERE project_id = ? AND artifact_type = ?
                ORDER BY revision_number ASC
                """,
                (project_id, artifact_type),
            ).fetchall()
        return [self._row_to_artifact(project_id, row) for row in rows]

    def get_artifact(self, project_id: str, artifact_id: str) -> ArtifactRecord | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, artifact_type, title, summary, status, content_format,
                       storage_path, body, revision_number, updated_at
                FROM demo_artifacts
                WHERE project_id = ? AND id = ?
                """,
                (project_id, artifact_id),
            ).fetchone()
        return self._row_to_artifact(project_id, row) if row else None

    def get_latest_artifact_with_metadata(
        self,
        project_id: str,
        artifact_type: str,
    ) -> tuple[ArtifactRecord, dict] | None:
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT id, project_id, artifact_type, title, summary, status, content_format,
                       storage_path, metadata_json, body, revision_number, updated_at
                FROM demo_artifacts
                WHERE project_id = ? AND artifact_type = ? AND status = 'generated'
                ORDER BY revision_number DESC
                LIMIT 1
                """,
                (project_id, artifact_type),
            ).fetchone()

        if not row:
            return None

        metadata_json = row["metadata_json"] or "{}"
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            metadata = {}

        return self._row_to_artifact(project_id, row), metadata

    def _next_artifact_revision(
        self,
        connection,
        *,
        project_id: str,
        artifact_type: str,
    ) -> int:
        row = connection.execute(
            """
            SELECT COALESCE(MAX(revision_number), 0) AS max_rev
            FROM demo_artifacts
            WHERE project_id = ? AND artifact_type = ?
            """,
            (project_id, artifact_type),
        ).fetchone()
        return int(row["max_rev"] or 0) + 1

    def _replace_artifact_state_item(
        self,
        connection,
        *,
        project_id: str,
        artifact_type: str,
        artifact_id: str,
        title: str,
        summary: str,
        timestamp: str,
    ) -> None:
        # 工作台「交付物」分区里每个 artifact_type 只对应一条 state_item，指向最新 revision。
        connection.execute(
            """
            DELETE FROM state_items
            WHERE project_id = ? AND category = 'artifacts'
              AND id IN (
                SELECT id FROM demo_artifacts
                WHERE project_id = ? AND artifact_type = ?
              )
              AND id <> ?
            """,
            (project_id, project_id, artifact_type, artifact_id),
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
                artifact_id,
                project_id,
                title,
                summary,
                timestamp,
            ),
        )

    def create_artifact_revision(
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
            revision_number = self._next_artifact_revision(
                connection,
                project_id=project_id,
                artifact_type=artifact_type,
            )
            connection.execute(
                """
                INSERT INTO demo_artifacts (
                  id, project_id, artifact_type, title, summary, status, content_format,
                  storage_path, metadata_json, body, revision_number, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    revision_number,
                    timestamp,
                    timestamp,
                ),
            )
            self._replace_artifact_state_item(
                connection,
                project_id=project_id,
                artifact_type=artifact_type,
                artifact_id=record_id,
                title=title,
                summary=summary,
                timestamp=timestamp,
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )
        preview_url = None
        if storage_path and content_format in {"html", "image"}:
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
            revision_number=revision_number,
            updated_at=timestamp,
        )

    def update_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
        title: str,
        summary: str,
        status: str,
        content_format: str,
        storage_path: str | None,
        body: str | None,
        metadata: dict | None = None,
    ) -> ArtifactRecord:
        timestamp = now_iso(self.settings)
        with connection_scope(self.settings) as connection:
            row = connection.execute(
                """
                SELECT artifact_type, revision_number
                FROM demo_artifacts
                WHERE id = ? AND project_id = ?
                """,
                (artifact_id, project_id),
            ).fetchone()
            if not row:
                raise LookupError("Artifact not found")
            artifact_type = row["artifact_type"]

            connection.execute(
                """
                UPDATE demo_artifacts
                SET title = ?, summary = ?, status = ?, content_format = ?,
                    storage_path = ?, metadata_json = ?, body = ?, updated_at = ?
                WHERE id = ? AND project_id = ?
                """,
                (
                    title,
                    summary,
                    status,
                    content_format,
                    storage_path,
                    json.dumps(metadata or {}, ensure_ascii=False),
                    body,
                    timestamp,
                    artifact_id,
                    project_id,
                ),
            )
            # update_artifact 只在「同一行翻状态」场景下使用（generating→generated/failed）。
            # state_items 中该 artifact_type 的指向不变，但 title/summary 需同步刷新。
            self._replace_artifact_state_item(
                connection,
                project_id=project_id,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                title=title,
                summary=summary,
                timestamp=timestamp,
            )
            connection.execute(
                "UPDATE projects SET updated_at = ? WHERE id = ?",
                (timestamp, project_id),
            )

        updated = self.get_artifact(project_id, artifact_id)
        if not updated:
            raise LookupError("Artifact not found after update")
        return updated

    def promote_artifact_to_latest(
        self,
        *,
        project_id: str,
        artifact_id: str,
    ) -> ArtifactRecord:
        source = self.get_artifact(project_id, artifact_id)
        if not source:
            raise LookupError("Artifact not found")

        new_storage_path: str | None = None
        if source.storage_path:
            origin = Path(source.storage_path)
            if origin.exists():
                target_dir = self.settings.projects_dir / project_id / "artifacts" / source.artifact_type
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f"index-promoted-{uuid.uuid4().hex[:8]}{origin.suffix or ''}"
                shutil.copy2(origin, target)
                new_storage_path = str(target)
            else:
                new_storage_path = source.storage_path

        with connection_scope(self.settings) as connection:
            row = connection.execute(
                "SELECT metadata_json FROM demo_artifacts WHERE id = ? AND project_id = ?",
                (artifact_id, project_id),
            ).fetchone()
        try:
            metadata = json.loads(row["metadata_json"] or "{}") if row else {}
        except json.JSONDecodeError:
            metadata = {}
        metadata = dict(metadata)
        metadata["promoted_from"] = artifact_id
        metadata["promoted_from_revision"] = source.revision_number

        return self.create_artifact_revision(
            project_id=project_id,
            artifact_type=source.artifact_type,
            title=source.title,
            summary=source.summary,
            status="generated",
            content_format=source.content_format,
            storage_path=new_storage_path,
            body=source.body,
            metadata=metadata,
        )

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
        # 兼容旧调用：带 artifact_id 且记录已存在 → update；否则 → create_revision。
        if artifact_id:
            with connection_scope(self.settings) as connection:
                existing = connection.execute(
                    "SELECT 1 FROM demo_artifacts WHERE id = ? AND project_id = ?",
                    (artifact_id, project_id),
                ).fetchone()
            if existing:
                return self.update_artifact(
                    project_id=project_id,
                    artifact_id=artifact_id,
                    title=title,
                    summary=summary,
                    status=status,
                    content_format=content_format,
                    storage_path=storage_path,
                    body=body,
                    metadata=metadata,
                )
        return self.create_artifact_revision(
            project_id=project_id,
            artifact_type=artifact_type,
            title=title,
            summary=summary,
            status=status,
            content_format=content_format,
            storage_path=storage_path,
            body=body,
            metadata=metadata,
            artifact_id=artifact_id,
        )
