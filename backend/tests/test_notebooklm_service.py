import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from app.config import AppSettings
from app.db import init_db
from app.models import (
    BindNotebookRequest,
    ChatCitation,
    CreateNotebookRequest,
    CreateProjectRequest,
)
from app.services.notebooklm_service import NotebookLMService


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


def make_service(tmp_path: Path) -> NotebookLMService:
    settings = make_settings(tmp_path)
    init_db(settings)
    return NotebookLMService(settings)


def write_storage_state(settings: AppSettings) -> None:
    settings.notebooklm_home_dir.mkdir(parents=True, exist_ok=True)
    (settings.notebooklm_home_dir / "storage_state.json").write_text("{}", encoding="utf-8")


def test_global_readiness_requires_project_scoped_login(tmp_path: Path) -> None:
    service = make_service(tmp_path)

    readiness = service.get_global_readiness()

    assert readiness.provider == "NOTEBOOKLM_PY"
    assert readiness.status == "auth_required"
    assert "NOTEBOOKLM_HOME" in (readiness.detail or "")
    assert ".venv/bin/notebooklm login" in (readiness.detail or "")


def test_list_library_reads_notebooks_from_notebooklm_py(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path)
    write_storage_state(service.settings)

    fake_notebooks = [
        SimpleNamespace(
            id="nb-1",
            title="集团业财逐笔对账 Notebook",
            created_at=datetime(2026, 4, 16, 10, 0, 0),
        )
    ]
    fake_client = SimpleNamespace(
        notebooks=SimpleNamespace(list=lambda: asyncio.sleep(0, result=fake_notebooks))
    )

    monkeypatch.setattr(
        service,
        "_with_client",
        lambda callback: service._run_async(lambda: callback(fake_client)),
    )

    notebooks = service.list_library()

    assert notebooks[0].id == "nb-1"
    assert notebooks[0].name == "集团业财逐笔对账 Notebook"
    assert notebooks[0].url == "https://notebooklm.google.com/notebook/nb-1"


def test_bind_project_notebook_parses_url_and_persists_binding(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path)
    write_storage_state(service.settings)
    project = service.catalog.create_project(
        CreateProjectRequest(
            name="测试项目",
            scenario_type="general",
            summary="测试 Notebook 绑定",
        )
    )

    fake_client = SimpleNamespace(
        notebooks=SimpleNamespace(
            get=lambda notebook_id: asyncio.sleep(
                0,
                result=SimpleNamespace(id=notebook_id, title="项目专属 Notebook"),
            )
        )
    )
    synced = []
    monkeypatch.setattr(
        service,
        "_with_client",
        lambda callback: service._run_async(lambda: callback(fake_client)),
    )
    monkeypatch.setattr(service, "sync_project_sources", lambda project_id: synced.append(project_id) or [])

    binding = service.bind_project_notebook(
        project.id,
        BindNotebookRequest(source_url="https://notebooklm.google.com/notebook/nb-bind-123?pli=1"),
    )

    assert binding.project_id == project.id
    assert binding.notebook_id == "nb-bind-123"
    assert binding.provider == "NOTEBOOKLM_PY"
    assert synced == [project.id]


def test_create_and_bind_project_notebook_creates_new_notebook(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path)
    write_storage_state(service.settings)
    project = service.catalog.create_project(
        CreateProjectRequest(
            name="新建项目",
            scenario_type="general",
            summary="测试创建 notebook",
        )
    )

    fake_client = SimpleNamespace(
        notebooks=SimpleNamespace(
            create=lambda title: asyncio.sleep(
                0,
                result=SimpleNamespace(id="nb-created-1", title=title),
            )
        )
    )
    monkeypatch.setattr(
        service,
        "_with_client",
        lambda callback: service._run_async(lambda: callback(fake_client)),
    )
    monkeypatch.setattr(service, "sync_project_sources", lambda project_id: [])

    response = service.create_and_bind_project_notebook(
        project.id,
        CreateNotebookRequest(notebook_name="项目专属 Notebook"),
    )

    assert response.notebook.id == "nb-created-1"
    assert response.binding.notebook_id == "nb-created-1"
    assert response.binding.provider == "NOTEBOOKLM_PY"


def test_sync_source_uses_add_text_for_normalized_content(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path)
    write_storage_state(service.settings)
    project = service.catalog.create_project(
        CreateProjectRequest(
            name="同步项目",
            scenario_type="general",
            summary="测试 source 同步",
        )
    )
    source_dir = service.settings.projects_dir / project.id / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = source_dir / "访谈纪要.md"
    normalized_path.write_text("退款单需要独立规则。", encoding="utf-8")
    source = service.catalog.create_source(
        project_id=project.id,
        name="访谈纪要",
        source_kind="text",
        upload_kind="text",
        storage_path=str(normalized_path),
        normalized_path=str(normalized_path),
        notebook_import_mode="direct_text",
        parse_status="parsed",
        parse_summary="退款单需要独立规则。",
        sync_status="pending_sync",
        sync_error=None,
    )
    service.catalog.upsert_notebook_binding(
        project_id=project.id,
        notebook_id="nb-sync-1",
        provider="NOTEBOOKLM_PY",
        sync_status="bound",
        source_url="https://notebooklm.google.com/notebook/nb-sync-1",
    )

    calls = []
    fake_client = SimpleNamespace(
        sources=SimpleNamespace(
            add_text=lambda notebook_id, title, content, wait: calls.append(
                (notebook_id, title, content, wait)
            ) or asyncio.sleep(0, result=SimpleNamespace(id="nb-source-1", title=title))
        )
    )
    monkeypatch.setattr(
        service,
        "_with_client",
        lambda callback: service._run_async(lambda: callback(fake_client)),
    )

    updated = service.sync_source(source.id)

    assert calls == [("nb-sync-1", "访谈纪要", "退款单需要独立规则。", True)]
    assert updated.sync_status == "synced"
    assert updated.sync_error is None


def test_query_returns_notebook_summary_and_citations(tmp_path: Path, monkeypatch) -> None:
    service = make_service(tmp_path)
    write_storage_state(service.settings)
    project = service.catalog.create_project(
        CreateProjectRequest(
            name="查询项目",
            scenario_type="general",
            summary="测试 query",
        )
    )
    source = service.catalog.create_source(
        project_id=project.id,
        name="订单字段说明.md",
        source_kind="text",
        upload_kind="seed",
        storage_path=None,
        normalized_path=None,
        notebook_import_mode="direct_text",
        parse_status="parsed",
        parse_summary="订单字段说明",
        sync_status="synced",
        sync_error=None,
    )
    service.catalog.upsert_notebook_binding(
        project_id=project.id,
        notebook_id="nb-query-1",
        provider="NOTEBOOKLM_PY",
        sync_status="bound",
        source_url="https://notebooklm.google.com/notebook/nb-query-1",
    )

    fake_references = [
        SimpleNamespace(source_id="nb-source-1", cited_text="金额字段和科目映射口径不一致"),
        SimpleNamespace(source_id="nb-source-1", cited_text="金额字段和科目映射口径不一致"),
    ]
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            ask=lambda notebook_id, question, source_ids=None, conversation_id=None: asyncio.sleep(
                0,
                result=SimpleNamespace(answer="核心问题是字段与科目映射不一致。", references=fake_references),
            )
        ),
        sources=SimpleNamespace(
            list=lambda notebook_id: asyncio.sleep(
                0,
                result=[SimpleNamespace(id="nb-source-1", title="订单字段说明.md", url=None)],
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_with_client",
        lambda callback: service._run_async(lambda: callback(fake_client)),
    )

    evidence = service.query(project.id, "当前核心冲突是什么？")

    assert evidence.summary == "核心问题是字段与科目映射不一致。"
    assert evidence.sync_status == "queried"
    assert evidence.citations == [
        ChatCitation(
            title="订单字段说明.md",
            snippet="金额字段和科目映射口径不一致",
            source_id=source.id,
        )
    ]
