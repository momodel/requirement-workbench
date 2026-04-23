from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import ProjectSummary
from app.services.project_catalog import ProjectCatalog
from app.services.seed_projects import SEED_PROJECT_ID, ensure_seed_project


def make_settings(
    tmp_path: Path,
) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "missing-claude"),
    )


def test_ensure_seed_project_rebuilds_canonical_demo_data(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    catalog.upsert_project(
        ProjectSummary(
            id=SEED_PROJECT_ID,
            name="污染项目",
            scenario_type="dirty",
            summary="旧内容",
            status="dirty",
            created_at="2026-04-15T00:00:00+08:00",
            updated_at="2026-04-15T00:00:00+08:00",
            seed_key="reconciliation",
        )
    )
    catalog.create_source(
        project_id=SEED_PROJECT_ID,
        name="probe.txt",
        source_kind="text",
        upload_kind="seed",
        storage_path=None,
        normalized_path=None,
        notebook_import_mode=None,
        parse_status="parsed",
        parse_summary="hello",
        sync_status="synced",
        sync_error=None,
    )

    ensure_seed_project(settings)

    seed_project = catalog.get_project(SEED_PROJECT_ID)
    assert seed_project is not None
    assert seed_project.name == "集团业财逐笔对账需求分析"
    assert seed_project.status == "seed"

    source_names = [source.name for source in catalog.list_sources(SEED_PROJECT_ID)]
    assert source_names == [
        "订单字段说明.md",
        "结算单样例.xlsx",
        "财务科目口径说明.pdf",
        "历史差异清单.txt",
    ]
    source_files = catalog.list_sources(SEED_PROJECT_ID)
    assert all(source.storage_path for source in source_files)
    assert all(Path(source.storage_path).exists() for source in source_files if source.storage_path)
    assert all(source.parse_status == "parsed" for source in source_files)
    assert all(source.sync_status == "pending" for source in source_files)
    assert all(source.sync_error for source in source_files)
    assert all("项目知识库" in (source.sync_error or "") for source in source_files)

    message_contents = [message.content for message in catalog.list_recent_messages(SEED_PROJECT_ID)]
    assert any(
        content.startswith("客户说希望核对订单或结算系统的数据")
        for content in message_contents
    )
    assert all("hello" not in content for content in message_contents)
    assert all("语雀" not in content for content in message_contents)
    assert any("为什么现在先确认" in content for content in message_contents)

    artifact_titles = [artifact.title for artifact in catalog.list_artifacts(SEED_PROJECT_ID)]
    assert set(artifact_titles) == {"交互稿", "页面方案", "需求分析与 MVP 文档稿"}
