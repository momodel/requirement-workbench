import sqlite3
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import CreateProjectRequest
from app.services.project_catalog import ProjectCatalog


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
        tables = {
            row[0]
            for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        bindings_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(notebook_bindings)").fetchall()
        }
        artifact_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(demo_artifacts)").fetchall()
        }
        source_chunk_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(source_chunks)").fetchall()
        }
    finally:
        migrated.close()

    assert "sync_error" in sources_columns
    assert "source_url" in bindings_columns
    assert "body" in artifact_columns
    assert "knowledge_bases" in tables
    assert "source_chunks" in tables
    assert "chunk_order" in source_chunk_columns
    assert "modality" in source_chunk_columns
    assert "content" in source_chunk_columns
    assert "locator_json" in source_chunk_columns
    assert "content_hash" in source_chunk_columns
    assert "embedding_status" in source_chunk_columns
    assert "indexed_at" in source_chunk_columns


def test_init_db_migrates_legacy_source_chunks_table_shape(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(settings.sqlite_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE projects (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          scenario_type TEXT NOT NULL,
          summary TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          seed_key TEXT
        );

        CREATE TABLE sources (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          source_kind TEXT NOT NULL,
          upload_kind TEXT NOT NULL,
          storage_path TEXT,
          normalized_path TEXT,
          notebook_import_mode TEXT,
          parse_status TEXT NOT NULL,
          parse_summary TEXT,
          sync_status TEXT NOT NULL DEFAULT 'pending',
          sync_error TEXT,
          created_at TEXT NOT NULL
        );

        CREATE TABLE knowledge_bases (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          provider TEXT NOT NULL,
          external_knowledge_base_id TEXT NOT NULL,
          display_name TEXT,
          description TEXT,
          status TEXT NOT NULL,
          status_error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE source_chunks (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          knowledge_base_id TEXT REFERENCES knowledge_bases(id) ON DELETE SET NULL,
          chunk_index INTEGER NOT NULL,
          chunk_text TEXT NOT NULL,
          metadata_json TEXT,
          index_status TEXT NOT NULL DEFAULT 'pending',
          index_error TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO projects (id, name, scenario_type, summary, status, created_at, updated_at, seed_key)
        VALUES ('project-1', '项目一', 'general', 'summary', 'active', '2026-04-22T10:00:00+08:00', '2026-04-22T10:00:00+08:00', NULL)
        """
    )
    connection.execute(
        """
        INSERT INTO sources (
          id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
          notebook_import_mode, parse_status, parse_summary, sync_status, sync_error, created_at
        )
        VALUES (
          'src-1', 'project-1', '访谈纪要', 'text', 'text', NULL, NULL,
          'direct_text', 'parsed', '摘要', 'synced', NULL, '2026-04-22T10:00:00+08:00'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO knowledge_bases (
          id, project_id, provider, external_knowledge_base_id, display_name, description,
          status, status_error, created_at, updated_at
        )
        VALUES (
          'kb-1', 'project-1', 'NOTEBOOKLM_PY', 'kb-ext-1', 'KB', 'desc',
          'ready', NULL, '2026-04-22T10:00:00+08:00', '2026-04-22T10:00:00+08:00'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO source_chunks (
          id, project_id, source_id, knowledge_base_id, chunk_index, chunk_text, metadata_json,
          index_status, index_error, created_at, updated_at
        )
        VALUES (
          'chunk-legacy-1', 'project-1', 'src-1', 'kb-1', 3, '旧分块内容', '{"page": 2}',
          'indexed', NULL, '2026-04-22T10:00:00+08:00', '2026-04-22T10:00:00+08:00'
        )
        """
    )
    connection.commit()
    connection.close()

    init_db(settings)

    catalog = ProjectCatalog(settings)
    chunks = catalog.list_source_chunks(project_id="project-1", source_id="src-1")

    migrated = sqlite3.connect(settings.sqlite_path)
    try:
        source_chunk_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(source_chunks)").fetchall()
        }
    finally:
        migrated.close()

    assert "chunk_index" not in source_chunk_columns
    assert "chunk_text" not in source_chunk_columns
    assert "metadata_json" not in source_chunk_columns
    assert "index_status" not in source_chunk_columns
    assert len(chunks) == 1
    assert chunks[0].id == "chunk-legacy-1"
    assert chunks[0].knowledge_base_id == "kb-1"
    assert chunks[0].chunk_order == 3
    assert chunks[0].modality == "text"
    assert chunks[0].content == "旧分块内容"
    assert chunks[0].locator_json == '{"page": 2}'
    assert chunks[0].embedding_status == "indexed"
    assert chunks[0].content_hash
    assert chunks[0].indexed_at is None


def test_project_catalog_persists_knowledge_bases_and_source_chunks(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="证据项目",
            scenario_type="general",
            summary="测试知识库和分块账本",
        )
    )
    source = catalog.create_source(
        project_id=project.id,
        name="字段说明.md",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        notebook_import_mode="direct_text",
        parse_status="parsed",
        parse_summary="字段说明",
        sync_status="pending_sync",
        sync_error=None,
    )

    created = catalog.upsert_knowledge_base(
        project_id=project.id,
        provider="NOTEBOOKLM_PY",
        external_knowledge_base_id="kb-ext-1",
        display_name="项目 KB",
        description="初始知识库",
        status="ready",
        status_error=None,
    )
    updated = catalog.upsert_knowledge_base(
        project_id=project.id,
        provider="NOTEBOOKLM_PY",
        external_knowledge_base_id="kb-ext-2",
        display_name="项目 KB v2",
        description="更新后的知识库",
        status="syncing",
        status_error="still indexing",
    )

    fetched = catalog.get_knowledge_base(project_id=project.id, provider="NOTEBOOKLM_PY")
    assert fetched is not None
    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert fetched.id == created.id
    assert fetched.external_knowledge_base_id == "kb-ext-2"
    assert fetched.display_name == "项目 KB v2"
    assert fetched.description == "更新后的知识库"
    assert fetched.status == "syncing"
    assert fetched.status_error == "still indexing"

    replaced = catalog.replace_source_chunks(
        project_id=project.id,
        source_id=source.id,
        chunks=[
            {
                "knowledge_base_id": created.id,
                "chunk_order": 0,
                "modality": "text",
                "content": "第一段内容",
                "locator_json": '{"page": 1}',
                "content_hash": "hash-1",
                "embedding_status": "indexed",
                "indexed_at": "2026-04-22T10:01:00+08:00",
            },
            {
                "knowledge_base_id": created.id,
                "chunk_order": 1,
                "modality": "text",
                "content": "第二段内容",
                "locator_json": '{"page": 2}',
                "embedding_status": "pending",
            },
        ],
    )
    listed = catalog.list_source_chunks(project_id=project.id, source_id=source.id)

    assert len(replaced) == 2
    assert [chunk.chunk_order for chunk in listed] == [0, 1]
    assert listed[0].knowledge_base_id == created.id
    assert listed[0].content == "第一段内容"
    assert listed[0].content_hash == "hash-1"
    assert listed[0].embedding_status == "indexed"
    assert listed[0].indexed_at == "2026-04-22T10:01:00+08:00"
    assert listed[1].knowledge_base_id == created.id
    assert listed[1].content == "第二段内容"
    assert listed[1].locator_json == '{"page": 2}'
    assert listed[1].content_hash
    assert listed[1].embedding_status == "pending"

    replaced_again = catalog.replace_source_chunks(
        project_id=project.id,
        source_id=source.id,
        chunks=[
            {
                "knowledge_base_id": created.id,
                "chunk_order": 0,
                "modality": "text",
                "content": "重建后的唯一分块",
                "locator_json": '{"section": "A"}',
                "embedding_status": "failed",
                "index_error": "bad embedding",
            }
        ],
    )

    assert len(replaced_again) == 1
    assert [chunk.content for chunk in catalog.list_source_chunks(project_id=project.id, source_id=source.id)] == [
        "重建后的唯一分块"
    ]
