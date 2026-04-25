from pathlib import Path

from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.models import ProviderIssue


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
    )


def install_noop_provider_hooks(app, monkeypatch) -> None:
    return None


def test_project_and_source_flow(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_noop_provider_hooks(app, monkeypatch)

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
    install_noop_provider_hooks(app, monkeypatch)

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


def test_source_upload_indexes_into_llm_wiki_without_remote_provider(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_noop_provider_hooks(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "知识库索引测试",
                "scenario_type": "general",
                "summary": "验证 source 入库后直接进入 LLM Wiki 知识库上下文",
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
        assert source["sync_status"] == "indexed"
        assert "LLM Wiki" in source["sync_error"]


def test_retry_source_sync_updates_failed_source(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_noop_provider_hooks(app, monkeypatch)

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
            sync_error="索引失败：旧错误",
        )

        retry_response = client.post(
            f"/api/projects/{project_id}/sources/{source_id}/retry-sync",
        )

        assert retry_response.status_code == 200
        updated_source = retry_response.json()
        assert updated_source["id"] == source_id
        assert updated_source["sync_status"] == "indexed"
        assert "LLM Wiki" in updated_source["sync_error"]


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


def test_provider_readiness_reports_llm_wiki_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_noop_provider_hooks(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "知识库 readiness 测试",
                "scenario_type": "general",
                "summary": "验证 provider readiness 和项目知识库状态",
            },
        )
        project_id = create_response.json()["id"]

        readiness_response = client.get(f"/api/projects/{project_id}/readiness")

        assert readiness_response.status_code == 200
        readiness = readiness_response.json()
        assert readiness["claude"]["provider"] == "CLAUDE_AGENT_SDK"
        assert readiness["knowledge_wiki"]["provider"] == "LLM_WIKI"
        assert readiness["knowledge_wiki"]["status"] == "ready"
        assert "notebooklm" not in readiness


def test_legacy_notebook_binding_endpoint_is_not_part_of_llm_wiki_route(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_noop_provider_hooks(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "旧绑定接口验证",
                "scenario_type": "general",
                "summary": "验证旧项目绑定接口不属于当前 LLM Wiki 主链路",
            },
        )
        project_id = create_response.json()["id"]

        bind_response = client.post(
            f"/api/projects/{project_id}/notebook-binding",
            json={"source_url": "https://legacy.example/notebook/abc123"},
        )

        assert bind_response.status_code == 404

        readiness_response = client.get(f"/api/projects/{project_id}/readiness")
        readiness = readiness_response.json()
        assert readiness["knowledge_wiki"]["status"] == "ready"

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "财务访谈纪要",
                "text_content": "新资料应直接进入 LLM Wiki 知识库上下文。",
            },
        )
        assert upload_response.status_code == 201
        assert upload_response.json()["sync_status"] == "indexed"


def test_delete_source_removes_local_and_updates_wiki(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "删除资料测试",
                "scenario_type": "general",
                "summary": "验证资料可以从本地知识库删掉",
            },
        )
        project_id = create_response.json()["id"]

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


def test_generate_artifact_returns_provider_issue_detail(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    monkeypatch.setattr(app.state.services.agent_runtime, "ensure_available", lambda: None)

    async def fake_generate_artifact(**kwargs):
        raise ProviderIssue(
            provider="CLAUDE_AGENT_SDK",
            message="Claude 交付物生成超时，请稍后重试。",
            status_code=504,
        )

    monkeypatch.setattr(
        app.state.services.artifact_generation,
        "generate_from_model",
        fake_generate_artifact,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/projects/seed-reconciliation/artifacts/generate",
            json={"artifact_type": "interaction_flow"},
        )

    assert response.status_code == 504
    assert response.json()["detail"] == "Claude 交付物生成超时，请稍后重试。"


def test_generate_artifact_returns_validation_detail(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    monkeypatch.setattr(app.state.services.agent_runtime, "ensure_available", lambda: None)

    async def fake_generate_artifact(**kwargs):
        raise ValueError("交互稿 的 HTML 缺少 title。")

    monkeypatch.setattr(
        app.state.services.artifact_generation,
        "generate_from_model",
        fake_generate_artifact,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/projects/seed-reconciliation/artifacts/generate",
            json={"artifact_type": "interaction_flow"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "交互稿 的 HTML 缺少 title。"
