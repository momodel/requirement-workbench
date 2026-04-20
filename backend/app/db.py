from __future__ import annotations

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
    "demo_artifacts": {
        "body": "ALTER TABLE demo_artifacts ADD COLUMN body TEXT",
    },
}


def _existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _apply_column_migrations(connection: sqlite3.Connection) -> None:
    for table_name, columns in MIGRATION_COLUMNS.items():
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
