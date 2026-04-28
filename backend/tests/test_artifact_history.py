import sqlite3
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import CreateProjectRequest
from app.services.project_catalog import ProjectCatalog


def _make_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        sqlite_dir=tmp_path / "data" / "sqlite",
        sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
        projects_dir=tmp_path / "data" / "projects",
    )


def _make_project(catalog: ProjectCatalog) -> str:
    project = catalog.create_project(
        payload=CreateProjectRequest(
            name="版本测试项目",
            scenario_type="versioning",
            summary="覆盖交付物多版本。",
        )
    )
    return project.id


def test_create_artifact_revision_assigns_incrementing_numbers(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id = _make_project(catalog)

    first = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿",
        summary="第一版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v1",
    )
    second = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿",
        summary="第二版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v2",
    )
    third = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="page_solution",
        title="页面方案",
        summary="新类型第一版",
        status="generated",
        content_format="html",
        storage_path=None,
        body=None,
    )

    assert first.revision_number == 1
    assert second.revision_number == 2
    # 不同类型自己单独从 1 计数。
    assert third.revision_number == 1


def test_list_artifacts_default_returns_only_latest_per_type(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id = _make_project(catalog)

    catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿 v1",
        summary="第一版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v1",
    )
    latest_doc = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿 v2",
        summary="第二版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v2",
    )
    latest_page = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="page_solution",
        title="页面方案 v1",
        summary="页面方案",
        status="generated",
        content_format="html",
        storage_path=None,
        body=None,
    )

    listed = catalog.list_artifacts(project_id)
    listed_ids = {item.id for item in listed}

    assert listed_ids == {latest_doc.id, latest_page.id}
    history = catalog.list_artifact_history(project_id, "document")
    assert [item.revision_number for item in history] == [1, 2]


def test_list_artifacts_include_history_returns_all_revisions(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id = _make_project(catalog)

    for i in range(3):
        catalog.create_artifact_revision(
            project_id=project_id,
            artifact_type="document",
            title=f"文档稿 v{i + 1}",
            summary=f"第 {i + 1} 版",
            status="generated",
            content_format="markdown",
            storage_path=None,
            body=f"# v{i + 1}",
        )

    listed = catalog.list_artifacts(project_id, include_history=True)
    assert len(listed) == 3
    assert [item.revision_number for item in listed] == [1, 2, 3]


def test_update_artifact_does_not_create_new_revision(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id = _make_project(catalog)

    placeholder = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿",
        summary="生成中",
        status="generating",
        content_format="markdown",
        storage_path=None,
        body=None,
    )
    finalised = catalog.update_artifact(
        project_id=project_id,
        artifact_id=placeholder.id,
        title="文档稿",
        summary="完成",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# 完成稿",
    )

    assert finalised.id == placeholder.id
    assert finalised.revision_number == placeholder.revision_number == 1
    history = catalog.list_artifact_history(project_id, "document")
    assert len(history) == 1
    assert history[0].status == "generated"


def test_promote_artifact_to_latest_creates_new_revision(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id = _make_project(catalog)

    first = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿 v1",
        summary="第一版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v1",
    )
    catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿 v2",
        summary="第二版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v2",
    )

    promoted = catalog.promote_artifact_to_latest(
        project_id=project_id,
        artifact_id=first.id,
    )

    assert promoted.revision_number == 3
    assert promoted.body == "# v1"
    history = catalog.list_artifact_history(project_id, "document")
    assert [item.revision_number for item in history] == [1, 2, 3]
    listed = catalog.list_artifacts(project_id)
    assert len(listed) == 1
    assert listed[0].id == promoted.id


def test_promote_artifact_copies_storage_file_for_html_body(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id = _make_project(catalog)

    artifact_dir = settings.projects_dir / project_id / "artifacts" / "page_solution"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    html_path = artifact_dir / "index.html"
    html_path.write_text(
        "<!doctype html><html><head><title>页面方案</title></head><body><main>v1</main></body></html>",
        encoding="utf-8",
    )

    first = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="page_solution",
        title="页面方案",
        summary="第一版",
        status="generated",
        content_format="html",
        storage_path=str(html_path),
        body=None,
    )
    catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="page_solution",
        title="页面方案",
        summary="第二版",
        status="generated",
        content_format="html",
        storage_path=str(html_path),
        body=None,
    )

    promoted = catalog.promote_artifact_to_latest(
        project_id=project_id,
        artifact_id=first.id,
    )

    assert promoted.storage_path is not None
    assert promoted.storage_path != first.storage_path
    assert Path(promoted.storage_path).exists()


def test_state_items_artifacts_only_keep_latest_per_type(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project_id = _make_project(catalog)

    catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿 v1",
        summary="第一版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v1",
    )
    second = catalog.create_artifact_revision(
        project_id=project_id,
        artifact_type="document",
        title="文档稿 v2",
        summary="第二版",
        status="generated",
        content_format="markdown",
        storage_path=None,
        body="# v2",
    )

    grouped = catalog.list_state_items(project_id)
    artifact_state_ids = [item.id for item in grouped["artifacts"]]
    assert artifact_state_ids == [second.id]


def test_backfill_renumbers_legacy_rows(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    settings.sqlite_dir.mkdir(parents=True, exist_ok=True)

    legacy = sqlite3.connect(settings.sqlite_path)
    try:
        legacy.executescript(
            """
            CREATE TABLE projects (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL,
              scenario_type TEXT NOT NULL,
              summary TEXT NOT NULL,
              status TEXT NOT NULL,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
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
            INSERT INTO projects (id, name, scenario_type, summary, status, created_at, updated_at)
            VALUES ('p1', '老项目', 'legacy', '老项目', 'active', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO demo_artifacts (id, project_id, artifact_type, title, summary, status, content_format, storage_path, metadata_json, created_at, updated_at)
            VALUES ('a-old', 'p1', 'document', '老文档稿 v1', '', 'generated', 'markdown', NULL, '{}', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            INSERT INTO demo_artifacts (id, project_id, artifact_type, title, summary, status, content_format, storage_path, metadata_json, created_at, updated_at)
            VALUES ('a-mid', 'p1', 'document', '老文档稿 v2', '', 'generated', 'markdown', NULL, '{}', '2026-02-01T00:00:00Z', '2026-02-01T00:00:00Z');
            INSERT INTO demo_artifacts (id, project_id, artifact_type, title, summary, status, content_format, storage_path, metadata_json, created_at, updated_at)
            VALUES ('a-new', 'p1', 'document', '老文档稿 v3', '', 'generated', 'markdown', NULL, '{}', '2026-03-01T00:00:00Z', '2026-03-01T00:00:00Z');
            """
        )
        legacy.commit()
    finally:
        legacy.close()

    init_db(settings)

    migrated = sqlite3.connect(settings.sqlite_path)
    migrated.row_factory = sqlite3.Row
    try:
        rows = migrated.execute(
            "SELECT id, revision_number FROM demo_artifacts ORDER BY revision_number"
        ).fetchall()
    finally:
        migrated.close()

    assert [(row["id"], row["revision_number"]) for row in rows] == [
        ("a-old", 1),
        ("a-mid", 2),
        ("a-new", 3),
    ]
