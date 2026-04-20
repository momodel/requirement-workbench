import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.models import ProviderReadiness


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        notebooklm_home_dir=data_dir / "notebooklm",
        claude_cli_path=str(tmp_path / "fake-claude"),
    )


def write_storage_state(settings: AppSettings) -> None:
    settings.notebooklm_home_dir.mkdir(parents=True, exist_ok=True)
    (settings.notebooklm_home_dir / "storage_state.json").write_text("{}", encoding="utf-8")


def make_fake_notebook_client() -> SimpleNamespace:
    return SimpleNamespace(
        notebooks=SimpleNamespace(
            list=lambda: asyncio.sleep(
                0,
                result=[SimpleNamespace(id="existing-notebook", title="项目专属 Notebook")],
            ),
            get=lambda notebook_id: asyncio.sleep(
                0,
                result=SimpleNamespace(id=notebook_id, title="项目专属 Notebook"),
            ),
            create=lambda title: asyncio.sleep(
                0,
                result=SimpleNamespace(id="created-notebook", title=title),
            ),
        ),
        sources=SimpleNamespace(
            add_text=lambda notebook_id, title, content, wait: asyncio.sleep(
                0,
                result=SimpleNamespace(id="nb-source-1", title=title),
            ),
            add_url=lambda notebook_id, url, wait: asyncio.sleep(
                0,
                result=SimpleNamespace(id="nb-source-url", title=url),
            ),
            add_file=lambda notebook_id, file_path, wait: asyncio.sleep(
                0,
                result=SimpleNamespace(id="nb-source-file", title=file_path),
            ),
            list=lambda notebook_id: asyncio.sleep(0, result=[]),
            delete=lambda notebook_id, source_id: asyncio.sleep(0, result=True),
        ),
        chat=SimpleNamespace(
            ask=lambda notebook_id, question, source_ids=None, conversation_id=None: asyncio.sleep(
                0,
                result=SimpleNamespace(answer="NotebookLM 回答", references=[]),
            )
        ),
    )


def install_fake_notebook_client(app, monkeypatch) -> None:
    write_storage_state(app.state.services.settings)
    fake_client = make_fake_notebook_client()
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "_with_client",
        lambda callback: app.state.services.notebooklm._run_async(lambda: callback(fake_client)),
    )


def test_project_and_source_flow(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)

    with TestClient(app) as client:
        projects_response = client.get("/api/projects")
        assert projects_response.status_code == 200
        projects = projects_response.json()
        assert any(project["id"] == "seed-reconciliation" for project in projects)

        create_response = client.post(
            "/api/projects",
            json={
                "name": "测试项目",
                "scenario_type": "general",
                "summary": "验证项目创建和资料入库",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "访谈纪要",
                "text_content": "财务要逐笔核对订单和财务科目金额，退款需要单独规则。",
            },
        )
        assert upload_response.status_code == 201
        source = upload_response.json()
        assert source["name"] == "访谈纪要"
        assert source["parse_status"] in {"parsed", "queued"}

        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        sources = sources_response.json()
        assert len(sources) == 1
        assert sources[0]["id"] == source["id"]

        state_response = client.get(f"/api/projects/{project_id}/state")
        assert state_response.status_code == 200
        state = state_response.json()
        assert state["current_understanding"] == []
        assert state["artifacts"] == []


def test_project_supports_batch_file_upload(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "批量文件上传测试",
                "scenario_type": "general",
                "summary": "验证一次请求可以上传多个文件",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "批量上传"},
            files=[
                ("files", ("rules-a.md", "# A\n退款规则".encode("utf-8"), "text/markdown")),
                ("files", ("rules-b.md", "# B\n冲销规则".encode("utf-8"), "text/markdown")),
            ],
        )

        assert upload_response.status_code == 201
        sources = upload_response.json()
        assert isinstance(sources, list)
        assert len(sources) == 2
        assert {source["name"] for source in sources} == {"rules-a.md", "rules-b.md"}

        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        stored_sources = sources_response.json()
        assert len(stored_sources) == 2


def test_source_upload_normalizes_provider_error_to_sync_failed(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "get_global_readiness",
        lambda: ProviderReadiness(
            provider="NOTEBOOKLM_PY",
            status="error",
            summary="NotebookLM provider 检查失败。",
            detail="ConnectError",
            action_label="检查 NotebookLM 配置",
        ),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "失败状态统一测试",
                "scenario_type": "general",
                "summary": "验证 source 同步失败状态统一成 sync_failed",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "访谈纪要",
                "text_content": "这里是一段文本资料。",
            },
        )

        assert upload_response.status_code == 201
        source = upload_response.json()
        assert source["sync_status"] == "sync_failed"
        assert "ConnectError" in source["sync_error"]


def test_retry_source_sync_updates_failed_source(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "重试同步测试",
                "scenario_type": "general",
                "summary": "验证失败资料可以单独重试同步",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "访谈纪要",
                "text_content": "这里是一段文本资料。",
            },
        )
        assert upload_response.status_code == 201
        source_id = upload_response.json()["id"]

        app.state.services.catalog.update_source_sync_status(
            source_id=source_id,
            sync_status="sync_failed",
            sync_error="NotebookLM 调用失败：ConnectError",
        )

        def fake_sync_source(target_source_id: str):
            assert target_source_id == source_id
            return app.state.services.catalog.update_source_sync_status(
                source_id=target_source_id,
                sync_status="synced",
                sync_error=None,
            )

        monkeypatch.setattr(app.state.services.notebooklm, "sync_source", fake_sync_source)

        retry_response = client.post(
            f"/api/projects/{project_id}/sources/{source_id}/retry-sync",
        )

        assert retry_response.status_code == 200
        updated_source = retry_response.json()
        assert updated_source["id"] == source_id
        assert updated_source["sync_status"] == "synced"
        assert updated_source["sync_error"] is None


def test_chat_stream_reports_provider_not_configured(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "未配置 Provider 测试",
                "scenario_type": "general",
                "summary": "验证未配置时的错误输出",
            },
        )
        project_id = create_response.json()["id"]

        response = client.post(
            f"/api/projects/{project_id}/chat/stream",
            json={
                "message": "请基于资料分析当前真实需求。",
                "selected_source_ids": [],
                "request_artifact_types": [],
            },
        )

        assert response.status_code == 200
        body = response.text
        assert "event: error" in body
        assert "CLAUDE_AGENT_SDK" in body
        assert f"\"project_id\": \"{project_id}\"" in body


def test_provider_readiness_reports_binding_required_when_notebook_is_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "Notebook 绑定测试",
                "scenario_type": "general",
                "summary": "验证 provider readiness 和项目 notebook 绑定状态",
            },
        )
        project_id = create_response.json()["id"]

        readiness_response = client.get(f"/api/projects/{project_id}/readiness")

        assert readiness_response.status_code == 200
        readiness = readiness_response.json()
        assert readiness["claude"]["provider"] == "CLAUDE_AGENT_SDK"
        assert readiness["notebooklm"]["provider"] == "NOTEBOOKLM_PY"
        assert readiness["notebooklm"]["status"] == "binding_required"
        assert readiness["notebook_binding"] is None


def test_bind_notebook_endpoint_persists_project_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "项目级 Notebook 绑定",
                "scenario_type": "general",
                "summary": "验证新项目可以绑定自己的 notebook",
            },
        )
        project_id = create_response.json()["id"]

        bind_response = client.post(
            f"/api/projects/{project_id}/notebook-binding",
            json={"source_url": "https://notebooklm.google.com/notebook/abc123"},
        )

        assert bind_response.status_code == 201
        binding = bind_response.json()
        assert binding["project_id"] == project_id
        assert binding["notebook_id"] == "abc123"
        assert binding["sync_status"] == "bound"

        readiness_response = client.get(f"/api/projects/{project_id}/readiness")
        readiness = readiness_response.json()
        assert readiness["notebooklm"]["status"] == "ready"
        assert readiness["notebook_binding"]["notebook_id"] == "abc123"

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "财务访谈纪要",
                "text_content": "已绑定项目 notebook 后，新资料应进入待同步状态。",
            },
        )
        assert upload_response.status_code == 201
        assert upload_response.json()["sync_status"] == "synced"


def test_delete_source_removes_local_and_notebook_records(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    write_storage_state(app.state.services.settings)

    source_registry: list[SimpleNamespace] = []

    fake_client = SimpleNamespace(
        notebooks=SimpleNamespace(
            list=lambda: asyncio.sleep(
                0,
                result=[SimpleNamespace(id="existing-notebook", title="项目专属 Notebook")],
            ),
            get=lambda notebook_id: asyncio.sleep(
                0,
                result=SimpleNamespace(id=notebook_id, title="项目专属 Notebook"),
            ),
            create=lambda title: asyncio.sleep(
                0,
                result=SimpleNamespace(id="created-notebook", title=title),
            ),
        ),
        sources=SimpleNamespace(
            add_text=lambda notebook_id, title, content, wait: asyncio.sleep(
                0,
                result=source_registry.append(SimpleNamespace(id=f"nb-{len(source_registry)+1}", title=title)) or source_registry[-1],
            ),
            add_url=lambda notebook_id, url, wait: asyncio.sleep(
                0,
                result=SimpleNamespace(id="nb-source-url", title=url),
            ),
            add_file=lambda notebook_id, file_path, wait: asyncio.sleep(
                0,
                result=SimpleNamespace(id="nb-source-file", title=file_path),
            ),
            list=lambda notebook_id: asyncio.sleep(0, result=list(source_registry)),
            delete=lambda notebook_id, source_id: asyncio.sleep(
                0,
                result=source_registry.__setitem__(
                    slice(None),
                    [source for source in source_registry if source.id != source_id],
                )
                or True,
            ),
        ),
        chat=SimpleNamespace(
            ask=lambda notebook_id, question, source_ids=None, conversation_id=None: asyncio.sleep(
                0,
                result=SimpleNamespace(answer="NotebookLM 回答", references=[]),
            )
        ),
    )
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "_with_client",
        lambda callback: app.state.services.notebooklm._run_async(lambda: callback(fake_client)),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "删除资料测试",
                "scenario_type": "general",
                "summary": "验证资料可以从本地和 notebook 一起删掉",
            },
        )
        project_id = create_response.json()["id"]

        bind_response = client.post(
            f"/api/projects/{project_id}/notebook-binding",
            json={"source_url": "https://notebooklm.google.com/notebook/abc123"},
        )
        assert bind_response.status_code == 201

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "待删除资料",
                "text_content": "这是一条后续会被删除的资料。",
            },
        )
        assert upload_response.status_code == 201
        source_id = upload_response.json()["id"]

        delete_response = client.delete(f"/api/projects/{project_id}/sources/{source_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True

        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        assert sources_response.json() == []
        assert source_registry == []
