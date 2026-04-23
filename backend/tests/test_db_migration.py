import sqlite3
from pathlib import Path

import pytest

from app.config import AppSettings
from app.db import init_db
from app.models import CreateProjectRequest
from app.services.project_catalog import ProjectCatalog

SOURCE_WRITE_STORAGE_COLUMNS = (
    "notebook_import_mode",
    "index_input_mode",
    "parse_status",
    "normalize_status",
    "parse_summary",
    "normalize_summary",
    "sync_status",
    "index_status",
    "sync_error",
    "index_error",
)

SOURCE_STATUS_STORAGE_COLUMNS = (
    "sync_status",
    "index_status",
    "sync_error",
    "index_error",
)


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "missing-claude"),
    )


def fetch_source_storage(connection: sqlite3.Connection, source_id: str, columns: tuple[str, ...]) -> dict:
    row = connection.execute(
        f"""
        SELECT {", ".join(columns)}
        FROM sources
        WHERE id = ?
        """,
        (source_id,),
    ).fetchone()
    assert row is not None
    return dict(zip(columns, row))


def fetch_table_info(connection: sqlite3.Connection, table_name: str) -> dict[str, tuple]:
    return {
        row[1]: row
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def assert_source_neutral_write_storage(
    stored: dict,
    *,
    index_input_mode: str | None,
    normalize_status: str,
    normalize_summary: str | None,
    index_status: str,
    index_error: str | None,
) -> None:
    assert stored["index_input_mode"] == index_input_mode
    assert stored["normalize_status"] == normalize_status
    assert stored["normalize_summary"] == normalize_summary
    assert stored["index_status"] == index_status
    assert stored["index_error"] == index_error
    assert stored["notebook_import_mode"] is None
    assert stored["parse_status"] is None
    assert stored["parse_summary"] is None
    assert stored["sync_status"] is None
    assert stored["sync_error"] is None


def assert_source_status_neutral_write_storage(
    stored: dict,
    *,
    index_status: str,
    index_error: str | None,
) -> None:
    assert stored["index_status"] == index_status
    assert stored["index_error"] == index_error
    assert stored["sync_status"] is None
    assert stored["sync_error"] is None


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
          sync_error TEXT,
          created_at TEXT NOT NULL
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
    connection.execute(
        """
        INSERT INTO sources (
          id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
          notebook_import_mode, parse_status, sync_status, parse_summary, sync_error, created_at
        )
        VALUES (
          'source-legacy-1', 'project-legacy-1', '旧资料.txt', 'text', 'text', NULL, NULL,
          'direct_text', 'parsed', 'synced', '迁移摘要', 'legacy sync error', '2026-04-22T00:00:00Z'
        )
        """
    )
    connection.commit()
    connection.close()

    init_db(settings)

    migrated = sqlite3.connect(settings.sqlite_path)
    try:
        sources_table_info = fetch_table_info(migrated, "sources")
        sources_columns = set(sources_table_info)
        tables = {
            row[0]
            for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        artifact_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(demo_artifacts)").fetchall()
        }
        source_chunk_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(source_chunks)").fetchall()
        }
        migrated_source_row = migrated.execute(
            """
            SELECT
              notebook_import_mode,
              parse_status,
              parse_summary,
              sync_status,
              sync_error,
              index_input_mode,
              normalize_status,
              normalize_summary,
              index_status,
              index_error
            FROM sources
            WHERE id = 'source-legacy-1'
            """
        ).fetchone()
    finally:
        migrated.close()

    assert "index_input_mode" in sources_columns
    assert "normalize_status" in sources_columns
    assert "normalize_summary" in sources_columns
    assert "index_status" in sources_columns
    assert "index_error" in sources_columns
    assert "notebook_import_mode" in sources_columns
    assert "parse_status" in sources_columns
    assert "parse_summary" in sources_columns
    assert "sync_status" in sources_columns
    assert "sync_error" in sources_columns
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
    assert migrated_source_row is not None
    assert migrated_source_row[0] == "direct_text"
    assert migrated_source_row[1] == "parsed"
    assert migrated_source_row[2] == "迁移摘要"
    assert migrated_source_row[3] == "synced"
    assert migrated_source_row[4] == "legacy sync error"
    assert migrated_source_row[5] == "direct_text"
    assert migrated_source_row[6] == "parsed"
    assert migrated_source_row[7] == "迁移摘要"
    assert migrated_source_row[8] == "synced"
    assert migrated_source_row[9] == "legacy sync error"
    assert sources_table_info["parse_status"][3] == 0
    assert sources_table_info["parse_status"][4] is None
    assert sources_table_info["sync_status"][3] == 0
    assert sources_table_info["sync_status"][4] is None


def test_init_db_creates_sources_table_with_neutral_and_legacy_source_columns(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)

    init_db(settings)

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        sources_table_info = fetch_table_info(connection, "sources")
        sources_columns = set(sources_table_info)
    finally:
        connection.close()

    expected_columns = {
        "index_input_mode",
        "notebook_import_mode",
        "normalize_status",
        "parse_status",
        "normalize_summary",
        "parse_summary",
        "index_status",
        "sync_status",
        "index_error",
        "sync_error",
    }
    assert expected_columns.issubset(sources_columns)
    assert sources_table_info["parse_status"][3] == 0
    assert sources_table_info["parse_status"][4] is None
    assert sources_table_info["sync_status"][3] == 0
    assert sources_table_info["sync_status"][4] is None


def test_init_db_allows_neutral_only_source_insert_on_fresh_schema(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)

    connection = sqlite3.connect(settings.sqlite_path)
    connection.execute(
        """
        INSERT INTO projects (id, name, scenario_type, summary, status, created_at, updated_at, seed_key)
        VALUES ('project-neutral-1', '项目一', 'general', 'summary', 'active', '2026-04-22T10:00:00+08:00', '2026-04-22T10:00:00+08:00', NULL)
        """
    )
    connection.execute(
        """
        INSERT INTO sources (
          id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
          index_input_mode, normalize_status, normalize_summary, index_status, index_error, created_at
        )
        VALUES (
          'source-neutral-only-1', 'project-neutral-1', '中性写入资料', 'text', 'text', NULL, NULL,
          'direct_text', 'parsed', '摘要', 'pending_sync', NULL, '2026-04-22T10:00:00+08:00'
        )
        """
    )
    stored = fetch_source_storage(connection, "source-neutral-only-1", SOURCE_WRITE_STORAGE_COLUMNS)
    connection.commit()
    connection.close()

    assert_source_neutral_write_storage(
        stored,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="摘要",
        index_status="pending_sync",
        index_error=None,
    )


def test_init_db_migrates_legacy_source_chunks_table_shape_without_knowledge_bases_table(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(settings.sqlite_path)
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

        CREATE TABLE source_chunks (
          id TEXT PRIMARY KEY,
          project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
          knowledge_base_id TEXT,
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
        tables = {
            row[0]
            for row in migrated.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        source_chunk_columns = {
            row[1]
            for row in migrated.execute("PRAGMA table_info(source_chunks)").fetchall()
        }
        source_chunk_foreign_keys = migrated.execute(
            "PRAGMA foreign_key_list(source_chunks)"
        ).fetchall()
    finally:
        migrated.close()

    assert "knowledge_bases" in tables
    assert "chunk_index" not in source_chunk_columns
    assert "chunk_text" not in source_chunk_columns
    assert "metadata_json" not in source_chunk_columns
    assert "index_status" not in source_chunk_columns
    assert len(chunks) == 1
    assert chunks[0].id == "chunk-legacy-1"
    assert chunks[0].knowledge_base_id is None
    assert chunks[0].chunk_order == 3
    assert chunks[0].modality == "text"
    assert chunks[0].content == "旧分块内容"
    assert chunks[0].locator_json == '{"page": 2}'
    assert chunks[0].embedding_status == "indexed"
    assert chunks[0].content_hash
    assert chunks[0].indexed_at is None
    assert any(
        row[2] == "knowledge_bases"
        and row[3] == "knowledge_base_id"
        and row[4] == "id"
        and row[6].upper() == "SET NULL"
        for row in source_chunk_foreign_keys
    )

    connection = sqlite3.connect(settings.sqlite_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        INSERT INTO knowledge_bases (
          id, project_id, provider, external_knowledge_base_id, display_name, description,
          status, status_error, created_at, updated_at
        )
        VALUES (
          'kb-2', 'project-1', 'NOTEBOOKLM_PY', 'kb-ext-2', 'KB 2', NULL,
          'ready', NULL, '2026-04-22T10:01:00+08:00', '2026-04-22T10:01:00+08:00'
        )
        """
    )
    connection.execute(
        "UPDATE source_chunks SET knowledge_base_id = 'kb-2' WHERE id = 'chunk-legacy-1'"
    )
    connection.execute("DELETE FROM knowledge_bases WHERE id = 'kb-2'")
    knowledge_base_id = connection.execute(
        "SELECT knowledge_base_id FROM source_chunks WHERE id = 'chunk-legacy-1'"
    ).fetchone()[0]
    connection.commit()
    connection.close()

    assert knowledge_base_id is None


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
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="字段说明",
        index_status="pending_sync",
        index_error=None,
    )
    connection = sqlite3.connect(settings.sqlite_path)
    try:
        stored = fetch_source_storage(
            connection,
            source.id,
            SOURCE_WRITE_STORAGE_COLUMNS,
        )
    finally:
        connection.close()

    assert_source_neutral_write_storage(
        stored,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="字段说明",
        index_status="pending_sync",
        index_error=None,
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


def test_replace_source_chunks_rejects_cross_project_ownership(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    project_a = catalog.create_project(
        CreateProjectRequest(
            name="项目 A",
            scenario_type="general",
            summary="A",
        )
    )
    project_b = catalog.create_project(
        CreateProjectRequest(
            name="项目 B",
            scenario_type="general",
            summary="B",
        )
    )
    source_a = catalog.create_source(
        project_id=project_a.id,
        name="A.md",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="A",
        index_status="pending_sync",
        index_error=None,
    )
    source_b = catalog.create_source(
        project_id=project_b.id,
        name="B.md",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="B",
        index_status="pending_sync",
        index_error=None,
    )
    knowledge_base_b = catalog.upsert_knowledge_base(
        project_id=project_b.id,
        provider="NOTEBOOKLM_PY",
        external_knowledge_base_id="kb-b",
        display_name="项目 B KB",
        description=None,
        status="ready",
        status_error=None,
    )

    with pytest.raises(ValueError, match="source_id does not belong"):
        catalog.replace_source_chunks(
            project_id=project_a.id,
            source_id=source_b.id,
            chunks=[
                {
                    "chunk_order": 0,
                    "modality": "text",
                    "content": "wrong source owner",
                }
            ],
        )

    with pytest.raises(ValueError, match="knowledge_base_id does not belong"):
        catalog.replace_source_chunks(
            project_id=project_a.id,
            source_id=source_a.id,
            chunks=[
                {
                    "chunk_order": 0,
                    "modality": "text",
                    "content": "wrong kb owner",
                    "knowledge_base_id": knowledge_base_b.id,
                }
            ],
        )

    with pytest.raises(ValueError, match="chunk project_id does not match"):
        catalog.replace_source_chunks(
            project_id=project_a.id,
            source_id=source_a.id,
            chunks=[
                {
                    "project_id": project_b.id,
                    "chunk_order": 0,
                    "modality": "text",
                    "content": "wrong explicit project",
                }
            ],
        )

    with pytest.raises(ValueError, match="chunk source_id does not match"):
        catalog.replace_source_chunks(
            project_id=project_a.id,
            source_id=source_a.id,
            chunks=[
                {
                    "source_id": source_b.id,
                    "chunk_order": 0,
                    "modality": "text",
                    "content": "wrong explicit source",
                }
            ],
        )

    assert catalog.list_source_chunks(project_id=project_a.id, source_id=source_a.id) == []


def test_bulk_update_source_index_status_updates_all_project_sources(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    project = catalog.create_project(
        CreateProjectRequest(
            name="批量更新项目",
            scenario_type="general",
            summary="验证 source index 状态批量更新",
        )
    )
    source_a = catalog.create_source(
        project_id=project.id,
        name="A.md",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="A",
        index_status="pending_sync",
        index_error="waiting",
    )
    source_b = catalog.create_source(
        project_id=project.id,
        name="B.md",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="B",
        index_status="index_failed",
        index_error="old failure",
    )

    catalog.bulk_update_source_index_status(
        project_id=project.id,
        index_status="indexed",
        index_error=None,
    )

    refreshed_sources = {source.id: source for source in catalog.list_sources(project.id)}
    connection = sqlite3.connect(settings.sqlite_path)
    try:
        stored_statuses = {
            source_id: fetch_source_storage(
                connection,
                source_id,
                SOURCE_STATUS_STORAGE_COLUMNS,
            )
            for source_id in (source_a.id, source_b.id)
        }
    finally:
        connection.close()

    assert refreshed_sources[source_a.id].index_status == "indexed"
    assert refreshed_sources[source_a.id].index_error is None
    assert refreshed_sources[source_b.id].index_status == "indexed"
    assert refreshed_sources[source_b.id].index_error is None
    assert_source_status_neutral_write_storage(
        stored_statuses[source_a.id],
        index_status="indexed",
        index_error=None,
    )
    assert_source_status_neutral_write_storage(
        stored_statuses[source_b.id],
        index_status="indexed",
        index_error=None,
    )


def test_update_source_index_status_writes_neutral_columns_only(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    project = catalog.create_project(
        CreateProjectRequest(
            name="单条更新项目",
            scenario_type="general",
            summary="验证 source index 状态单条更新",
        )
    )
    source = catalog.create_source(
        project_id=project.id,
        name="A.md",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="A",
        index_status="pending_sync",
        index_error="waiting",
    )

    updated = catalog.update_source_index_status(
        source_id=source.id,
        index_status="indexed",
        index_error=None,
    )

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        stored = fetch_source_storage(
            connection,
            source.id,
            SOURCE_STATUS_STORAGE_COLUMNS,
        )
    finally:
        connection.close()

    assert updated.index_status == "indexed"
    assert updated.index_error is None
    assert_source_status_neutral_write_storage(
        stored,
        index_status="indexed",
        index_error=None,
    )


def test_project_catalog_source_reads_prefer_neutral_columns_over_legacy_columns(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    project = catalog.create_project(
        CreateProjectRequest(
            name="Source alias 项目",
            scenario_type="general",
            summary="验证 source 读取字段别名",
        )
    )

    connection = sqlite3.connect(settings.sqlite_path)
    connection.execute(
        """
        INSERT INTO sources (
          id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
          notebook_import_mode, index_input_mode,
          parse_status, normalize_status,
          parse_summary, normalize_summary,
          sync_status, index_status,
          sync_error, index_error,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "source-neutral-1",
            project.id,
            "source.txt",
            "text",
            "text",
            None,
            None,
            "legacy_text",
            "neutral_text",
            "legacy_parsed",
            "neutral_parsed",
            "legacy 摘要",
            "neutral 摘要",
            "legacy_synced",
            "neutral_synced",
            "legacy error",
            "neutral error",
            "2026-04-22T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    listed = catalog.list_sources(project.id)
    fetched = catalog.get_source("source-neutral-1")

    assert len(listed) == 1
    assert listed[0].id == "source-neutral-1"
    assert listed[0].index_input_mode == "neutral_text"
    assert listed[0].normalize_status == "neutral_parsed"
    assert listed[0].normalize_summary == "neutral 摘要"
    assert listed[0].index_status == "neutral_synced"
    assert listed[0].index_error == "neutral error"
    assert fetched is not None
    assert fetched.id == "source-neutral-1"
    assert fetched.index_input_mode == "neutral_text"
    assert fetched.normalize_status == "neutral_parsed"
    assert fetched.normalize_summary == "neutral 摘要"
    assert fetched.index_status == "neutral_synced"
    assert fetched.index_error == "neutral error"

    listed_payload = listed[0].model_dump_neutral()
    fetched_payload = fetched.model_dump_neutral()

    for payload in (listed_payload, fetched_payload):
        assert payload["index_input_mode"] == "neutral_text"
        assert payload["normalize_status"] == "neutral_parsed"
        assert payload["normalize_summary"] == "neutral 摘要"
        assert payload["index_status"] == "neutral_synced"
        assert payload["index_error"] == "neutral error"
        assert "notebook_import_mode" not in payload
        assert "parse_status" not in payload
        assert "parse_summary" not in payload
        assert "sync_status" not in payload
        assert "sync_error" not in payload


def test_project_catalog_source_reads_fallback_to_legacy_columns_when_neutral_is_null(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    project = catalog.create_project(
        CreateProjectRequest(
            name="Source fallback 项目",
            scenario_type="general",
            summary="验证 source 读取会回退 legacy 字段",
        )
    )

    connection = sqlite3.connect(settings.sqlite_path)
    connection.execute(
        """
        INSERT INTO sources (
          id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
          notebook_import_mode, index_input_mode,
          parse_status, normalize_status,
          parse_summary, normalize_summary,
          sync_status, index_status,
          sync_error, index_error,
          created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "source-fallback-1",
            project.id,
            "source.txt",
            "text",
            "text",
            None,
            None,
            "legacy_text",
            None,
            "legacy_parsed",
            None,
            "legacy 摘要",
            None,
            "legacy_synced",
            None,
            "legacy error",
            None,
            "2026-04-22T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()

    listed = catalog.list_sources(project.id)
    fetched = catalog.get_source("source-fallback-1")

    assert len(listed) == 1
    assert listed[0].index_input_mode == "legacy_text"
    assert listed[0].normalize_status == "legacy_parsed"
    assert listed[0].normalize_summary == "legacy 摘要"
    assert listed[0].index_status == "legacy_synced"
    assert listed[0].index_error == "legacy error"
    assert fetched is not None
    assert fetched.index_input_mode == "legacy_text"
    assert fetched.normalize_status == "legacy_parsed"
    assert fetched.normalize_summary == "legacy 摘要"
    assert fetched.index_status == "legacy_synced"
    assert fetched.index_error == "legacy error"
