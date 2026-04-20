import sqlite3
from pathlib import Path

from app.config import AppSettings
from app.db import init_db


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        notebooklm_home_dir=data_dir / "notebooklm",
        claude_cli_path=str(tmp_path / "missing-claude"),
    )


def test_init_db_adds_missing_columns_for_existing_database(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(settings.sqlite_path)
    connection.executescript(
        """
        CREATE TABLE sources (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          name TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          upload_kind TEXT NOT NULL,
          storage_path TEXT,
          normalized_path TEXT,
          notebook_import_mode TEXT,
          parse_status TEXT NOT NULL,
          sync_status TEXT NOT NULL DEFAULT 'pending',
          parse_summary TEXT,
          created_at TEXT NOT NULL
        );

        CREATE TABLE notebook_bindings (
          project_id TEXT PRIMARY KEY,
          notebook_id TEXT NOT NULL,
          provider TEXT NOT NULL,
          sync_status TEXT NOT NULL,
          last_synced_at TEXT
        );

        CREATE TABLE demo_artifacts (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL,
          artifact_type TEXT NOT NULL,
          title TEXT NOT NULL,
          summary TEXT NOT NULL,
          status TEXT NOT NULL,
          content_format TEXT NOT NULL,
          storage_path TEXT,
          metadata_json TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()

    init_db(settings)

    migrated = sqlite3.connect(settings.sqlite_path)
    try:
        sources_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(sources)").fetchall()
        }
        bindings_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(notebook_bindings)").fetchall()
        }
        artifact_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(demo_artifacts)").fetchall()
        }
    finally:
        migrated.close()

    assert "sync_error" in sources_columns
    assert "source_url" in bindings_columns
    assert "body" in artifact_columns
