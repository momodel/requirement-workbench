from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import AppSettings, DEFAULT_SETTINGS


MIGRATION_COLUMNS: dict[str, dict[str, str]] = {
    "sources": {
        "sync_error": "ALTER TABLE sources ADD COLUMN sync_error TEXT",
    },
    "notebook_bindings": {
        "source_url": "ALTER TABLE notebook_bindings ADD COLUMN source_url TEXT",
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


def _existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


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


def _migrate_source_chunks_table(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "source_chunks"):
        return

    existing_columns = _existing_columns(connection, "source_chunks")
    if SOURCE_CHUNKS_EXPECTED_COLUMNS.issubset(existing_columns):
        return

    rows = [
        dict(row)
        for row in connection.execute(
            "SELECT * FROM source_chunks ORDER BY source_id, id"
        ).fetchall()
    ]

    connection.execute(
        """
        CREATE TABLE source_chunks__migrated (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          knowledge_base_id TEXT REFERENCES knowledge_bases(id) ON DELETE SET NULL,
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
                row.get("knowledge_base_id"),
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
        _migrate_source_chunks_table(connection)
        schema_path = Path(__file__).with_name("schema.sql")
        connection.executescript(schema_path.read_text(encoding="utf-8"))
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
