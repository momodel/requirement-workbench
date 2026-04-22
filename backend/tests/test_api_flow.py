import asyncio
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.models import EvidenceResult, ProviderIssue, ProviderReadiness


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


def install_fake_evidence_runtime(app, monkeypatch) -> None:
    services = app.state.services
    qdrant_path = services.settings.data_dir / "qdrant"
    qdrant_path.mkdir(parents=True, exist_ok=True)

    def fake_global_readiness() -> ProviderReadiness:
        return ProviderReadiness(
            provider="QDRANT_LLAMA_INDEX",
            status="ready",
            summary="项目内证据运行时已就绪。",
            detail=f"Qdrant path: {qdrant_path}",
        )

    def fake_ensure_available() -> Path:
        return qdrant_path

    def fake_ensure_project_knowledge_base(project_id: str):
        project = services.catalog.get_project(project_id)
        assert project is not None
        return services.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider="QDRANT_LLAMA_INDEX",
            external_knowledge_base_id=f"kb-{project_id}",
            display_name=f"{project.name} Evidence KB",
            description=project.summary,
            status="ready",
            status_error=None,
        )

    def fake_index_source(project_id: str, source_id: str):
        knowledge_base = fake_ensure_project_knowledge_base(project_id)
        source = services.catalog.get_source(source_id)
        assert source is not None
        services.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=[
                {
                    "knowledge_base_id": knowledge_base.id,
                    "chunk_order": 0,
                    "modality": "text",
                    "content": f"{source.name} normalized chunk",
                    "embedding_status": "indexed",
                    "index_error": None,
                    "indexed_at": "2026-04-22T00:00:00+08:00",
                }
            ],
        )
        services.catalog.update_source_sync_status(
            source_id=source_id,
            sync_status="indexed",
            sync_error=None,
        )
        return services.catalog.list_source_chunks(project_id=project_id, source_id=source_id)

    def fake_reindex_source(project_id: str, source_id: str):
        return fake_index_source(project_id, source_id)

    def fake_delete_source(project_id: str, source_id: str) -> None:
        services.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=[],
        )

    monkeypatch.setattr(services.evidence_runtime, "get_global_readiness", fake_global_readiness)
    monkeypatch.setattr(services.evidence_runtime, "ensure_available", fake_ensure_available)
    monkeypatch.setattr(
        services.evidence_runtime,
        "ensure_project_knowledge_base",
        fake_ensure_project_knowledge_base,
    )
    monkeypatch.setattr(services.evidence_runtime, "index_source", fake_index_source)
    monkeypatch.setattr(services.evidence_runtime, "reindex_source", fake_reindex_source)
    monkeypatch.setattr(services.evidence_runtime, "delete_source", fake_delete_source)


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


def test_project_knowledge_base_init_and_get_flow(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "知识库初始化测试",
                "scenario_type": "general",
                "summary": "验证项目知识库可初始化并查询状态",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        before_init_response = client.get(f"/api/projects/{project_id}/knowledge-base")
        assert before_init_response.status_code == 200
        before_init = before_init_response.json()
        assert before_init["knowledge_base"] is None
        assert before_init["readiness"]["status"] == "knowledge_base_missing"
        assert before_init["source_count"] == 0
        assert before_init["indexed_chunk_count"] == 0

        init_response = client.post(f"/api/projects/{project_id}/knowledge-base/init")
        assert init_response.status_code == 201
        knowledge_base = init_response.json()
        assert knowledge_base["project_id"] == project_id
        assert knowledge_base["provider"] == "QDRANT_LLAMA_INDEX"
        assert knowledge_base["status"] == "ready"

        after_init_response = client.get(f"/api/projects/{project_id}/knowledge-base")
        assert after_init_response.status_code == 200
        after_init = after_init_response.json()
        assert after_init["knowledge_base"]["id"] == knowledge_base["id"]
        assert after_init["readiness"]["status"] == "empty"
        assert after_init["indexed_chunk_count"] == 0


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


def test_reindex_source_updates_failed_source(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)
    install_fake_evidence_runtime(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "_load_client_class",
        lambda: SimpleNamespace(from_storage=None),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "重新索引测试",
                "scenario_type": "general",
                "summary": "验证失败资料可以单独重新索引",
            },
        )
        assert create_response.status_code == 201
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
                "name": "访谈纪要",
                "text_content": "这里是一段文本资料。",
            },
        )
        assert upload_response.status_code == 201
        source_id = upload_response.json()["id"]
        assert upload_response.json()["sync_status"] == "synced"

        app.state.services.catalog.update_source_sync_status(
            source_id=source_id,
            sync_status="index_failed",
            sync_error="Qdrant collection 暂不可写。",
        )

        def fake_reindex_source(target_project_id: str, target_source_id: str):
            assert target_project_id == project_id
            assert target_source_id == source_id
            app.state.services.catalog.replace_source_chunks(
                project_id=target_project_id,
                source_id=target_source_id,
                chunks=[],
            )
            return app.state.services.catalog.update_source_sync_status(
                source_id=target_source_id,
                sync_status="indexed",
                sync_error=None,
            )

        monkeypatch.setattr(
            app.state.services.evidence_runtime,
            "reindex_source",
            fake_reindex_source,
        )

        reindex_response = client.post(
            f"/api/projects/{project_id}/sources/{source_id}/reindex",
        )

        assert reindex_response.status_code == 200
        updated_source = reindex_response.json()
        assert updated_source["id"] == source_id
        assert updated_source["sync_status"] == "indexed"
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


def test_project_readiness_reports_knowledge_base_required_when_evidence_runtime_is_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)
    install_fake_evidence_runtime(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "知识库 readiness 测试",
                "scenario_type": "general",
                "summary": "验证 provider readiness 切到 evidence/knowledge-base 语义",
            },
        )
        project_id = create_response.json()["id"]

        readiness_response = client.get(f"/api/projects/{project_id}/readiness")

        assert readiness_response.status_code == 200
        readiness = readiness_response.json()
        assert readiness["claude"]["provider"] == "CLAUDE_AGENT_SDK"
        assert readiness["evidence"]["provider"] == "QDRANT_LLAMA_INDEX"
        assert readiness["evidence"]["status"] == "knowledge_base_missing"
        assert readiness["knowledge_base"] is None
        assert readiness["notebook_binding"] is None


def test_bind_notebook_endpoint_persists_project_binding(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)
    install_fake_evidence_runtime(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "_load_client_class",
        lambda: SimpleNamespace(from_storage=None),
    )
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
        assert readiness["evidence"]["status"] == "knowledge_base_missing"
        assert readiness["knowledge_base"] is None
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


def test_chat_stream_uses_evidence_runtime_instead_of_notebook_query(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))

    evidence_calls: list[dict[str, object]] = []

    def fake_evidence_query(
        project_id: str,
        question: str,
        *,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        evidence_calls.append(
            {
                "project_id": project_id,
                "question": question,
                "selected_source_ids": selected_source_ids,
            }
        )
        return EvidenceResult(
            summary="已检索到 1 条相关证据。",
            citations=[],
            sync_status="queried",
        )

    monkeypatch.setattr(
        app.state.services.chat_service.evidence_runtime,
        "query",
        fake_evidence_query,
    )
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "query",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("chat path should not call NotebookLM query in Task 5")
        ),
        raising=False,
    )
    monkeypatch.setattr(app.state.services.agent_runtime, "ensure_available", lambda: None)

    async def fake_stream_assistant_text(turn):
        yield "基于项目知识库先给出一轮判断。"

    async def fake_run_turn(turn, assistant_message: str | None = None):
        if False:
            yield ("result", None)

    monkeypatch.setattr(
        app.state.services.agent_runtime,
        "stream_assistant_text",
        fake_stream_assistant_text,
    )
    monkeypatch.setattr(
        app.state.services.agent_runtime,
        "run_turn",
        fake_run_turn,
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "聊天证据切换测试",
                "scenario_type": "general",
                "summary": "验证聊天主链路改为 evidence runtime。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        response = client.post(
            f"/api/projects/{project_id}/chat/stream",
            json={
                "message": "请基于当前资料给出判断。",
                "selected_source_ids": ["src-1", "src-2"],
                "request_artifact_types": [],
            },
        )

    assert response.status_code == 200
    assert evidence_calls == [
        {
            "project_id": project_id,
            "question": "请基于当前资料给出判断。",
            "selected_source_ids": ["src-1", "src-2"],
        }
    ]
    assert "正在检索项目知识库证据与引用" in response.text
    assert "基于项目知识库先给出一轮判断。" in response.text


def test_reindex_preserves_synced_delete_compatibility(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    write_storage_state(app.state.services.settings)
    install_fake_evidence_runtime(app, monkeypatch)

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
                result=source_registry.append(
                    SimpleNamespace(id=f"nb-{len(source_registry)+1}", title=title)
                )
                or source_registry[-1],
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
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "_load_client_class",
        lambda: SimpleNamespace(from_storage=None),
    )

    def fake_reindex_source(project_id: str, source_id: str):
        source = app.state.services.catalog.get_source(source_id)
        assert source is not None
        knowledge_base = app.state.services.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider="QDRANT_LLAMA_INDEX",
            external_knowledge_base_id=f"kb-{project_id}",
            display_name="Evidence KB",
            description="test",
            status="ready",
            status_error=None,
        )
        return app.state.services.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=[
                {
                    "knowledge_base_id": knowledge_base.id,
                    "chunk_order": 0,
                    "modality": "text",
                    "content": f"{source.name} reindexed chunk",
                    "embedding_status": "indexed",
                    "index_error": None,
                    "indexed_at": "2026-04-22T00:00:00+08:00",
                }
            ],
        )

    monkeypatch.setattr(app.state.services.evidence_runtime, "reindex_source", fake_reindex_source)
    monkeypatch.setattr(app.state.services.evidence_runtime, "delete_source", lambda project_id, source_id: None)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "重建索引兼容性测试",
                "scenario_type": "general",
                "summary": "验证 synced source reindex 后仍可删除 NotebookLM 远端资料",
            },
        )
        assert create_response.status_code == 201
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
                "name": "兼容性资料",
                "text_content": "这条资料会经历 synced -> reindex -> delete。",
            },
        )
        assert upload_response.status_code == 201
        source = upload_response.json()
        assert source["sync_status"] == "synced"
        assert len(source_registry) == 1

        reindex_response = client.post(
            f"/api/projects/{project_id}/sources/{source['id']}/reindex",
        )
        assert reindex_response.status_code == 200
        reindexed_source = reindex_response.json()
        assert reindexed_source["id"] == source["id"]
        assert reindexed_source["sync_status"] == "synced"
        assert len(source_registry) == 1

        delete_response = client.delete(f"/api/projects/{project_id}/sources/{source['id']}")
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True

        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        assert sources_response.json() == []
        assert source_registry == []


def test_delete_source_removes_local_and_notebook_records_even_when_evidence_cleanup_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
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
                result=source_registry.append(
                    SimpleNamespace(id=f"nb-{len(source_registry)+1}", title=title)
                )
                or source_registry[-1],
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
    monkeypatch.setattr(
        app.state.services.notebooklm,
        "_load_client_class",
        lambda: SimpleNamespace(from_storage=None),
    )
    monkeypatch.setattr(
        app.state.services.evidence_runtime,
        "delete_source",
        lambda project_id, source_id: (_ for _ in ()).throw(
            ProviderIssue(
                provider="QDRANT_LLAMA_INDEX",
                message="Qdrant 暂不可用。",
                status_code=503,
            )
        ),
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
        assert upload_response.json()["sync_status"] == "synced"
        assert source_registry != []

        delete_response = client.delete(f"/api/projects/{project_id}/sources/{source_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True
        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        assert sources_response.json() == []
        assert source_registry == []


def test_generate_artifact_returns_provider_issue_detail(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_notebook_client(app, monkeypatch)
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
    install_fake_notebook_client(app, monkeypatch)
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
