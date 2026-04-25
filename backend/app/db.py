from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import AppSettings, DEFAULT_SETTINGS


MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "sources": {
        "index_input_mode": "ALTER TABLE sources ADD COLUMN index_input_mode TEXT",
        "normalize_status": "ALTER TABLE sources ADD COLUMN normalize_status TEXT",
        "normalize_summary": "ALTER TABLE sources ADD COLUMN normalize_summary TEXT",
        "index_status": "ALTER TABLE sources ADD COLUMN index_status TEXT",
        "index_error": "ALTER TABLE sources ADD COLUMN index_error TEXT",
    },
    "knowledge_bases": {
        "display_name": "ALTER TABLE knowledge_bases ADD COLUMN display_name TEXT",
        "description": "ALTER TABLE knowledge_bases ADD COLUMN description TEXT",
        "status_error": "ALTER TABLE knowledge_bases ADD COLUMN status_error TEXT",
    },
    "demo_artifacts": {
        "body": "ALTER TABLE demo_artifacts ADD COLUMN body TEXT",
    },
}

SOURCE_LEGACY_TO_NEUTRAL_COLUMNS = {
    "notebook_import_mode": "index_input_mode",
    "parse_status": "normalize_status",
    "parse_summary": "normalize_summary",
    "sync_status": "index_status",
    "sync_error": "index_error",
}

SOURCE_CHUNKS_EXPECTED_COLUMNS = {
    "id",
    "project_id",
    "source_id",
    "knowledge_base_id",
    "chunk_order",
    "modality",
    "content",
    "locator_json",
    "content_hash",
    "embedding_status",
    "index_error",
    "indexed_at",
    "created_at",
    "updated_at",
}

SOURCE_CHUNKS_INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS idx_source_chunks_project_id ON source_chunks(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_source_chunks_source_id ON source_chunks(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_source_chunks_knowledge_base_id ON source_chunks(knowledge_base_id)",
    "CREATE INDEX IF NOT EXISTS idx_source_chunks_embedding_status ON source_chunks(embedding_status)",
    "CREATE INDEX IF NOT EXISTS idx_source_chunks_content_hash ON source_chunks(content_hash)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_source_chunks_source_chunk_order ON source_chunks(source_id, chunk_order)",
)


def _column_info(connection: sqlite3.Connection, table_name: str) -> dict[str, sqlite3.Row]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1]: row for row in rows}


def _existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return set(_column_info(connection, table_name))


def _sources_table_needs_rebuild(connection: sqlite3.Connection) -> bool:
    if not _table_exists(connection, "sources"):
        return False

    existing_columns = _existing_columns(connection, "sources")
    return any(
        legacy_column in existing_columns
        for legacy_column in SOURCE_LEGACY_TO_NEUTRAL_COLUMNS
    )


def _rebuild_sources_table(connection: sqlite3.Connection) -> None:
    rows = [
        dict(row)
        for row in connection.execute("SELECT * FROM sources ORDER BY created_at, id").fetchall()
    ]
    project_constraint = "project_id TEXT NOT NULL"
    if _table_exists(connection, "projects"):
        project_constraint = (
            "project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE"
        )

    foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    if foreign_keys_enabled:
        connection.execute("PRAGMA foreign_keys = OFF")

    try:
        connection.execute(
            f"""
            CREATE TABLE sources__migrated (
              id TEXT PRIMARY KEY,
              {project_constraint},
              name TEXT NOT NULL,
              source_kind TEXT NOT NULL,
              upload_kind TEXT NOT NULL,
              storage_path TEXT,
              normalized_path TEXT,
              index_input_mode TEXT,
              normalize_status TEXT,
              normalize_summary TEXT,
              index_status TEXT,
              index_error TEXT,
              created_at TEXT NOT NULL
            )
            """
        )

        for row in rows:
            index_input_mode = row.get("index_input_mode")
            if index_input_mode is None:
                index_input_mode = row.get("notebook_import_mode")

            normalize_status = row.get("normalize_status")
            if normalize_status is None:
                normalize_status = row.get("parse_status")

            normalize_summary = row.get("normalize_summary")
            if normalize_summary is None:
                normalize_summary = row.get("parse_summary")

            index_status = row.get("index_status")
            if index_status is None:
                index_status = row.get("sync_status")

            index_error = row.get("index_error")
            if index_error is None:
                index_error = row.get("sync_error")

            connection.execute(
                """
                INSERT INTO sources__migrated (
                  id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
                  index_input_mode, normalize_status, normalize_summary, index_status,
                  index_error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["project_id"],
                    row["name"],
                    row["source_kind"],
                    row["upload_kind"],
                    row.get("storage_path"),
                    row.get("normalized_path"),
                    index_input_mode,
                    normalize_status,
                    normalize_summary,
                    index_status,
                    index_error,
                    row["created_at"],
                ),
            )

        connection.execute("DROP TABLE sources")
        connection.execute("ALTER TABLE sources__migrated RENAME TO sources")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_sources_project_id ON sources(project_id)")
    finally:
        if foreign_keys_enabled:
            connection.execute("PRAGMA foreign_keys = ON")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _source_chunk_content_hash(content: str, locator_json: str | None) -> str:
    return hashlib.sha256(
        f"{content}\n{locator_json or ''}".encode("utf-8")
    ).hexdigest()


def _source_chunks_has_knowledge_base_fk(connection: sqlite3.Connection) -> bool:
    foreign_keys = connection.execute("PRAGMA foreign_key_list(source_chunks)").fetchall()
    return any(
        foreign_key[2] == "knowledge_bases"
        and foreign_key[3] == "knowledge_base_id"
        and foreign_key[4] == "id"
        and foreign_key[6].upper() == "SET NULL"
        for foreign_key in foreign_keys
    )


def _rebuild_source_chunks_table(
    connection: sqlite3.Connection,
    *,
    include_knowledge_base_fk: bool,
) -> None:
    rows = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM source_chunks ORDER BY source_id, id"
        ).fetchall()
    ]

    knowledge_base_constraint = "knowledge_base_id TEXT"
    valid_knowledge_base_ids: set[str] = set()
    if include_knowledge_base_fk:
        knowledge_base_constraint = (
            "knowledge_base_id TEXT REFERENCES knowledge_bases(id) ON DELETE SET NULL"
        )
        if _table_exists(connection, "knowledge_bases"):
            valid_knowledge_base_ids = {
                row[0]
                for row in connection.execute(
                    "SELECT id FROM knowledge_bases"
                ).fetchall()
            }

    connection.execute(
        f"""
        CREATE TABLE source_chunks__migrated (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          {knowledge_base_constraint},
          chunk_order INTEGER NOT NULL,
          modality TEXT NOT NULL,
          content TEXT NOT NULL,
          locator_json TEXT,
          content_hash TEXT NOT NULL,
          embedding_status TEXT NOT NULL DEFAULT 'pending',
          index_error TEXT,
          indexed_at TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )

    for row in rows:
        chunk_order = row.get("chunk_order")
        if chunk_order is None:
            chunk_order = row.get("chunk_index")
        if chunk_order is None:
            raise sqlite3.OperationalError(
                "source_chunks migration requires chunk_order or chunk_index"
            )

        content = row.get("content")
        if content is None:
            content = row.get("chunk_text")
        if content is None:
            raise sqlite3.OperationalError(
                "source_chunks migration requires content or chunk_text"
            )

        locator_json = row.get("locator_json")
        if locator_json is None:
            locator_json = row.get("metadata_json")
        knowledge_base_id = row.get("knowledge_base_id")
        if include_knowledge_base_fk and knowledge_base_id not in valid_knowledge_base_ids:
            knowledge_base_id = None

        connection.execute(
            """
            INSERT INTO source_chunks__migrated (
              id, project_id, source_id, knowledge_base_id, chunk_order, modality,
              content, locator_json, content_hash, embedding_status, index_error,
              indexed_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["project_id"],
                row["source_id"],
                knowledge_base_id,
                int(chunk_order),
                row.get("modality") or "text",
                content,
                locator_json,
                row.get("content_hash") or _source_chunk_content_hash(content, locator_json),
                row.get("embedding_status") or row.get("index_status") or "pending",
                row.get("index_error"),
                row.get("indexed_at"),
                row["created_at"],
                row["updated_at"],
            ),
        )

    connection.execute("DROP TABLE source_chunks")
    connection.execute("ALTER TABLE source_chunks__migrated RENAME TO source_chunks")
    for statement in SOURCE_CHUNKS_INDEX_STATEMENTS:
        connection.execute(statement)


def _migrate_source_chunks_table(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "source_chunks"):
        return

    existing_columns = _existing_columns(connection, "source_chunks")
    if SOURCE_CHUNKS_EXPECTED_COLUMNS.issubset(existing_columns):
        return

    _rebuild_source_chunks_table(connection, include_knowledge_base_fk=False)


def _migrate_sources_table(connection: sqlite3.Connection) -> None:
    if not _sources_table_needs_rebuild(connection):
        return

    _rebuild_sources_table(connection)


def _ensure_source_chunks_schema(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "source_chunks"):
        return

    existing_columns = _existing_columns(connection, "source_chunks")
    needs_rebuild = (
        not SOURCE_CHUNKS_EXPECTED_COLUMNS.issubset(existing_columns)
        or not _source_chunks_has_knowledge_base_fk(connection)
    )
    if not needs_rebuild:
        return

    _rebuild_source_chunks_table(connection, include_knowledge_base_fk=True)


def _apply_column_migrations(connection: sqlite3.Connection) -> None:
    for table_name, columns in MIGRATION_COLUMNS.items():
        if not _table_exists(connection, table_name):
            continue
        existing_columns = _existing_columns(connection, table_name)
        for column_name, statement in columns.items():
            if column_name not in existing_columns:
                connection.execute(statement)


def init_db(settings: AppSettings = DEFAULT_SETTINGS) -> None:
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)
    settings.projects_dir.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        _migrate_sources_table(connection)
        _migrate_source_chunks_table(connection)
        schema_path = Path(__file__).with_name("schema.sql")
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        _ensure_source_chunks_schema(connection)
        _apply_column_migrations(connection)
        connection.commit()
    finally:
        connection.close()


def get_connection(settings: AppSettings = DEFAULT_SETTINGS) -> sqlite3.Connection:
    connection = sqlite3.connect(settings.sqlite_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connection_scope(settings: AppSettings = DEFAULT_SETTINGS) -> Iterator[sqlite3.Connection]:
    connection = get_connection(settings)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
