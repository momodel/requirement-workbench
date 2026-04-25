from pathlib import Path
import sqlite3
from subprocess import CompletedProcess

from fastapi.testclient import TestClient

from app.config import AppSettings
from app.main import create_app
from app.models import ChatCitation, EvidenceResult, ProviderIssue, ProviderReadiness, StateItem
from app.services import agent_runtime as agent_runtime_module
from app.services.evidence_indexing import load_source_text

LEGACY_SOURCE_FIELDS = {
    "notebook_import_mode",
    "parse_status",
    "parse_summary",
    "sync_status",
    "sync_error",
}

MINIMAL_NEUTRAL_SOURCE_FIELDS = {
    "id",
    "project_id",
    "name",
}

SOURCE_WRITE_STORAGE_COLUMNS = (
    "index_input_mode",
    "normalize_status",
    "normalize_summary",
    "index_status",
    "index_error",
)


def assert_source_payload_is_neutral_only(source: dict) -> None:
    for field_name in MINIMAL_NEUTRAL_SOURCE_FIELDS:
        assert field_name in source
    for field_name in LEGACY_SOURCE_FIELDS:
        assert field_name not in source


def fetch_source_storage(connection: sqlite3.Connection, source_id: str) -> dict:
    row = connection.execute(
        f"""
        SELECT {", ".join(SOURCE_WRITE_STORAGE_COLUMNS)}
        FROM sources
        WHERE id = ?
        """,
        (source_id,),
    ).fetchone()
    assert row is not None
    return dict(zip(SOURCE_WRITE_STORAGE_COLUMNS, row))


def assert_source_neutral_write_storage(
    stored: dict,
    *,
    index_input_mode: str | None,
    normalize_status: str,
    normalize_summary: str | None,
    index_status: str,
    index_error_predicate,
) -> None:
    assert stored["index_input_mode"] == index_input_mode
    assert stored["normalize_status"] == normalize_status
    assert stored["normalize_summary"] == normalize_summary
    assert stored["index_status"] == index_status
    assert index_error_predicate(stored["index_error"])


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
                    "content": load_source_text(source),
                    "embedding_status": "indexed",
                    "index_error": None,
                    "indexed_at": "2026-04-22T00:00:00+08:00",
                }
            ],
        )
        services.catalog.update_source_index_status(
            source_id=source_id,
            index_status="indexed",
            index_error=None,
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

    def fake_query(project_id: str, question: str, *, selected_source_ids=None):
        source_ids = set(selected_source_ids or [])
        chunks = []
        for source in services.catalog.list_sources(project_id):
            if source_ids and source.id not in source_ids:
                continue
            chunks.extend(
                services.catalog.list_source_chunks(
                    project_id=project_id,
                    source_id=source.id,
                )
            )
        citations = []
        snippets = []
        for chunk in chunks:
            source = services.catalog.get_source(chunk.source_id)
            citations.append(
                ChatCitation(
                    source_id=chunk.source_id,
                    title=source.name if source else chunk.source_id,
                    snippet=chunk.content,
                    confidence=1.0,
                )
            )
            snippets.append(chunk.content)
        return EvidenceResult(
            summary="；".join(snippets) if snippets else "当前项目知识库没有命中相关资料。",
            citations=citations,
            sync_status="queried",
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
    monkeypatch.setattr(services.evidence_runtime, "query", fake_query)


def install_not_configured_evidence_runtime(app, monkeypatch) -> None:
    monkeypatch.setattr(
        app.state.services.evidence_runtime,
        "get_global_readiness",
        lambda: ProviderReadiness(
            provider="QDRANT_LLAMA_INDEX",
            status="not_configured",
            summary="项目内证据运行时未就绪。",
            detail="当前后端环境没有安装 LlamaIndex Qdrant/FastEmbed 依赖。请先安装。",
            action_label="安装 Qdrant/LlamaIndex 依赖",
        ),
    )


def install_ready_audio_providers(app, monkeypatch) -> None:
    monkeypatch.setattr(
        app.state.services.object_storage,
        "get_readiness",
        lambda: ProviderReadiness(
            provider="QINIU_OSS",
            status="ready",
            summary="七牛对象存储已就绪。",
            detail="bucket=audio-bucket",
            action_label=None,
        ),
    )
    monkeypatch.setattr(
        app.state.services.audio_transcription,
        "get_readiness",
        lambda: ProviderReadiness(
            provider="ALIYUN_FILETRANS",
            status="ready",
            summary="阿里云音频转写已就绪。",
            detail="region=cn-shanghai",
            action_label=None,
        ),
    )


def install_not_configured_audio_providers(app, monkeypatch) -> None:
    monkeypatch.setattr(
        app.state.services.object_storage,
        "get_readiness",
        lambda: ProviderReadiness(
            provider="QINIU_OSS",
            status="not_configured",
            summary="七牛对象存储未就绪。",
            detail="缺少七牛 AccessKey、SecretKey、Bucket 或 Domain 配置。",
            action_label="配置七牛对象存储",
        ),
    )
    monkeypatch.setattr(
        app.state.services.audio_transcription,
        "get_readiness",
        lambda: ProviderReadiness(
            provider="ALIYUN_FILETRANS",
            status="not_configured",
            summary="阿里云音频转写未就绪。",
            detail="缺少阿里云 AccessKeyId、AccessKeySecret 或 AppKey 配置。",
            action_label="配置阿里云音频转写",
        ),
    )


def test_project_and_source_flow(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_not_configured_evidence_runtime(app, monkeypatch)

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
        assert_source_payload_is_neutral_only(source)
        assert source["name"] == "访谈纪要"
        assert source["normalize_status"] == "parsed"
        assert source["index_status"] == "not_configured"
        assert "安装" in source["index_error"]

        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        sources = sources_response.json()
        assert len(sources) == 1
        assert_source_payload_is_neutral_only(sources[0])
        assert sources[0]["id"] == source["id"]
        assert sources[0]["name"] == "访谈纪要"
        assert sources[0]["normalize_status"] == "parsed"
        assert sources[0]["index_status"] == "not_configured"
        assert "安装" in sources[0]["index_error"]

        state_response = client.get(f"/api/projects/{project_id}/state")
        assert state_response.status_code == 200
        state = state_response.json()
        assert state["current_understanding"] == []
        assert state["artifacts"] == []


def test_project_supports_batch_file_upload(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))

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
        for source in sources:
            assert_source_payload_is_neutral_only(source)
            assert source["upload_kind"] == "file"
            assert source["normalize_status"] == "parsed"
        assert {source["name"] for source in sources} == {"rules-a.md", "rules-b.md"}

        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        stored_sources = sources_response.json()
        assert len(stored_sources) == 2
        for source in stored_sources:
            assert_source_payload_is_neutral_only(source)
            assert source["upload_kind"] == "file"
            assert source["normalize_status"] == "parsed"


def test_source_content_endpoint_returns_full_text_for_text_upload(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "资料预览测试",
                "scenario_type": "general",
                "summary": "验证 source content 返回完整文本",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        text_content = (
            "第一段：这里是为了验证预览读取完整正文而不是摘要。\n\n"
            "第二段：正文长度需要明显超过 240 个字符，因此我继续补充一些背景说明，"
            "包括业务规则、字段口径、异常处理和人工兜底动作，让这段文本足够长。"
            "第三段：最后一段应该仍然能在预览接口里完整返回，而不是只保留前 240 个字符。"
        )

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "长文本资料",
                "text_content": text_content,
            },
        )
        assert upload_response.status_code == 201
        source_id = upload_response.json()["id"]

        content_response = client.get(
            f"/api/projects/{project_id}/sources/{source_id}/content"
        )

    assert content_response.status_code == 200
    payload = content_response.json()
    assert payload["source_id"] == source_id
    assert payload["content_status"] == "full_text"
    assert payload["content_origin"] == "normalized_path"
    assert payload["content"] == text_content
    assert "第三段：最后一段应该仍然能在预览接口里完整返回" in payload["content"]


def test_source_content_endpoint_returns_full_docling_text_for_image_upload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    normalized_markdown = (
        "| name | description |\n"
        "| --- | --- |\n"
        "| code-reviewer | 这是 OCR 识别出来的完整正文，用来验证图片导入后的预览不会只剩摘要。 |\n\n"
        "补充段落：这里继续追加更多说明文字，让内容长度明显超过摘要截断上限。"
        "最终这句“超过 240 字后的正文仍然可见”必须出现在预览接口返回值里。"
    )
    monkeypatch.setattr(
        app.state.services.source_ingestion.docling_normalizer,
        "normalize_to_markdown",
        lambda _path: normalized_markdown,
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "图片预览测试",
                "scenario_type": "general",
                "summary": "验证图片 OCR 预览返回完整正文",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "截图资料"},
            files={"file": ("ocr-sample.png", b"fake-png-binary", "image/png")},
        )
        assert upload_response.status_code == 201
        source_id = upload_response.json()["id"]

        content_response = client.get(
            f"/api/projects/{project_id}/sources/{source_id}/content"
        )

    assert content_response.status_code == 200
    payload = content_response.json()
    assert payload["source_id"] == source_id
    assert payload["content_status"] == "full_text"
    assert payload["content_origin"] == "normalized_path"
    assert payload["content"] == normalized_markdown
    assert "超过 240 字后的正文仍然可见" in payload["content"]


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


def test_global_readiness_payload_uses_evidence_semantics_only(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)

    with TestClient(app) as client:
        readiness_response = client.get("/api/providers/readiness")

    assert readiness_response.status_code == 200
    readiness = readiness_response.json()
    assert readiness["claude"]["provider"] == "CLAUDE_AGENT_SDK"
    assert readiness["evidence"]["provider"] == "QDRANT_LLAMA_INDEX"
    assert "notebooklm" not in readiness


def test_readiness_endpoints_surface_claude_model_not_configured_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)

    real_path_exists = agent_runtime_module.Path.exists

    def fake_exists(path_obj):
        if str(path_obj) == str(app.state.services.agent_runtime.settings.claude_cli_path):
            return True
        return real_path_exists(path_obj)

    monkeypatch.setattr(agent_runtime_module.Path, "exists", fake_exists)

    def fake_run(command, **kwargs):
        assert command == [str(app.state.services.agent_runtime.settings.claude_cli_path), "auth", "status"]
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"loggedIn": true, "authMethod": "oauth_token", "apiProvider": "firstParty"}',
            stderr="",
        )

    monkeypatch.setattr(agent_runtime_module.subprocess, "run", fake_run)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "Claude 模型缺失测试",
                "scenario_type": "general",
                "summary": "验证 readiness 接口会把 Claude 模型缺失显式透出给前端",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        global_readiness = client.get("/api/providers/readiness").json()
        project_readiness = client.get(f"/api/projects/{project_id}/readiness").json()

    assert global_readiness["claude"]["status"] == "not_configured"
    assert "CLAUDE_MODEL" in global_readiness["claude"]["detail"]
    assert global_readiness["claude"]["action_label"]
    assert project_readiness["claude"]["status"] == "not_configured"
    assert "CLAUDE_MODEL" in project_readiness["claude"]["detail"]
    assert project_readiness["claude"]["action_label"]


def test_source_upload_uses_evidence_readiness_for_provider_errors(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    monkeypatch.setattr(
        app.state.services.evidence_runtime,
        "get_global_readiness",
        lambda: ProviderReadiness(
            provider="QDRANT_LLAMA_INDEX",
            status="error",
            summary="Evidence runtime 检查失败。",
            detail="ConnectError",
            action_label="检查 Qdrant/LlamaIndex 配置",
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
        assert_source_payload_is_neutral_only(source)
        assert source["index_status"] == "error"
        assert "ConnectError" in source["index_error"]


def test_reindex_source_updates_failed_source(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)

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

        init_response = client.post(f"/api/projects/{project_id}/knowledge-base/init")
        assert init_response.status_code == 201

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "访谈纪要",
                "text_content": "这里是一段文本资料。",
            },
        )
        assert upload_response.status_code == 201
        created_source = upload_response.json()
        assert_source_payload_is_neutral_only(created_source)
        source_id = created_source["id"]
        assert created_source["normalize_status"] == "parsed"
        assert created_source["index_status"] == "indexed"

        app.state.services.catalog.update_source_index_status(
            source_id=source_id,
            index_status="index_failed",
            index_error="Qdrant collection 暂不可写。",
        )

        def fake_reindex_source(target_project_id: str, target_source_id: str):
            assert target_project_id == project_id
            assert target_source_id == source_id
            app.state.services.catalog.replace_source_chunks(
                project_id=target_project_id,
                source_id=target_source_id,
                chunks=[],
            )
            return app.state.services.catalog.update_source_index_status(
                source_id=target_source_id,
                index_status="indexed",
                index_error=None,
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
        assert_source_payload_is_neutral_only(updated_source)
        assert updated_source["id"] == source_id
        assert updated_source["normalize_status"] == "parsed"
        assert updated_source["index_status"] == "indexed"
        assert updated_source["index_error"] is None


def test_chat_stream_reports_provider_not_configured(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))

    async def fake_query_evidence(*args, **kwargs) -> EvidenceResult:
        return EvidenceResult(summary="当前未执行项目知识库证据检索。", citations=[])

    def fake_claude_not_configured() -> None:
        raise ProviderIssue(
            provider="CLAUDE_AGENT_SDK",
            message="未找到 Claude Code CLI。请安装 claude 或配置 CLAUDE_CODE_CLI_PATH。",
        )

    monkeypatch.setattr(
        app.state.services.chat_service,
        "_query_evidence_with_timeout",
        fake_query_evidence,
    )
    monkeypatch.setattr(
        app.state.services.agent_runtime,
        "ensure_available",
        fake_claude_not_configured,
    )

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
        assert "notebooklm" not in readiness
        assert "notebook_binding" not in readiness


def test_app_bootstrap_and_mainline_readiness_do_not_require_notebooklm_service(
    tmp_path: Path,
) -> None:
    app = create_app(make_settings(tmp_path))
    assert not hasattr(app.state.services, "notebooklm")

    with TestClient(app) as client:
        readiness_response = client.get("/api/providers/readiness")

    assert readiness_response.status_code == 200
    readiness = readiness_response.json()
    assert readiness["evidence"]["provider"] == "QDRANT_LLAMA_INDEX"


def test_legacy_notebook_binding_endpoints_are_removed_from_mainline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "旧接口退场测试",
                "scenario_type": "general",
                "summary": "验证 notebook binding/library 接口退出主链路。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        assert client.get(f"/api/projects/{project_id}/notebook-binding").status_code == 404
        assert client.get(f"/api/projects/{project_id}/notebook-library").status_code == 404
        assert (
            client.post(
                f"/api/projects/{project_id}/notebook-binding",
                json={"source_url": "https://notebooklm.google.com/notebook/abc123"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/projects/{project_id}/notebook-create-and-bind",
                json={},
            ).status_code
            == 404
        )


def test_file_upload_uses_docling_normalized_markdown_before_indexing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.source_ingestion.docling_normalizer,
        "normalize_to_markdown",
        lambda source_path: "# Docling Output\n项目资料已经转换成 Markdown 文本。",
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "Docling 文件上传测试",
                "scenario_type": "general",
                "summary": "验证文件上传主线先走 Docling 再入知识库",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        init_response = client.post(f"/api/projects/{project_id}/knowledge-base/init")
        assert init_response.status_code == 201

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "需求文档"},
            files={"file": ("brief.pdf", b"%PDF-1.4 mock", "application/pdf")},
        )

        assert upload_response.status_code == 201
        source = upload_response.json()
        assert_source_payload_is_neutral_only(source)
        assert source["name"] == "brief.pdf"
        assert source["normalize_status"] == "parsed"
        assert source["index_status"] == "indexed"
        assert source["normalized_path"].endswith(".normalized.md")
        normalized_text = Path(source["normalized_path"]).read_text(encoding="utf-8")
        assert "Docling Output" in normalized_text


def test_file_upload_reports_normalization_failure_without_collapsing_it_into_index_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.source_ingestion.docling_normalizer,
        "normalize_to_markdown",
        lambda source_path: (_ for _ in ()).throw(
            ProviderIssue(
                provider="DOCLING",
                message="当前环境还没有可用的 PDF 转文本链路。",
            )
        ),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "Docling 标准化失败测试",
                "scenario_type": "general",
                "summary": "验证标准化失败不会被误报成索引失败",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        init_response = client.post(f"/api/projects/{project_id}/knowledge-base/init")
        assert init_response.status_code == 201

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "需求文档"},
            files={"file": ("brief.pdf", b"%PDF-1.4 mock", "application/pdf")},
        )

        assert upload_response.status_code == 201
        source = upload_response.json()
        assert_source_payload_is_neutral_only(source)
        assert source["normalize_status"] == "failed"
        assert source["index_status"] == "normalization_failed"
        assert source["index_status"] != "index_failed"
        assert "尚未进入项目知识库" in source["index_error"]
        assert "PDF 转文本链路" in source["index_error"]
        assert app.state.services.catalog.list_source_chunks(
            project_id=project_id,
            source_id=source["id"],
        ) == []


def test_url_upload_stays_out_of_evidence_index_until_page_text_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.evidence_runtime,
        "index_source",
        lambda project_id, source_id: (_ for _ in ()).throw(
            AssertionError("URL source should not be indexed before normalized page text exists")
        ),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "URL 延迟标准化测试",
                "scenario_type": "general",
                "summary": "验证 URL 录入后不会伪装成 evidence-ready 成功",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        init_response = client.post(f"/api/projects/{project_id}/knowledge-base/init")
        assert init_response.status_code == 201

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "url",
                "name": "退款规则链接",
                "source_url": "https://docs.example.com/help/refund-policy",
            },
        )

        assert upload_response.status_code == 201
        source = upload_response.json()
        assert_source_payload_is_neutral_only(source)
        assert source["normalize_status"] == "pending"
        assert source["index_status"] == "normalization_pending"
        assert source["normalized_path"] is None
        assert source["index_input_mode"] is None
        assert "还没有抓取到页面正文" in source["normalize_summary"]
        assert "不会进入项目知识库" in source["index_error"]
        assert app.state.services.catalog.list_source_chunks(
            project_id=project_id,
            source_id=source["id"],
        ) == []


def test_audio_upload_returns_processing_and_exposes_runtime_readiness(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    queued: list[tuple[str, str]] = []

    install_ready_audio_providers(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: queued.append((project_id, source_id)),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "音频上传测试",
                "scenario_type": "general",
                "summary": "验证音频异步标准化返回 processing 并暴露运行时 readiness。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )
        global_readiness_response = client.get("/api/providers/readiness")
        project_readiness_response = client.get(f"/api/projects/{project_id}/readiness")

    assert upload_response.status_code == 201
    source = upload_response.json()
    assert_source_payload_is_neutral_only(source)
    assert source["source_kind"] == "audio"
    assert source["normalize_status"] == "processing"
    assert source["index_status"] == "normalization_pending"
    assert source["normalized_path"] is None
    assert "自动进入项目知识库" in source["index_error"]
    assert queued == [(project_id, source["id"])]

    assert global_readiness_response.status_code == 200
    global_readiness = global_readiness_response.json()
    assert global_readiness["object_storage"]["provider"] == "QINIU_OSS"
    assert global_readiness["object_storage"]["status"] == "ready"
    assert global_readiness["audio_transcription"]["provider"] == "ALIYUN_FILETRANS"
    assert global_readiness["audio_transcription"]["status"] == "ready"

    assert project_readiness_response.status_code == 200
    project_readiness = project_readiness_response.json()
    assert project_readiness["object_storage"]["provider"] == "QINIU_OSS"
    assert project_readiness["audio_transcription"]["provider"] == "ALIYUN_FILETRANS"
    assert "processing_audio_sources=1" in (project_readiness["object_storage"]["detail"] or "")
    assert "failed_audio_sources=0" in (project_readiness["audio_transcription"]["detail"] or "")


def test_audio_upload_reports_not_configured_when_audio_providers_are_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    install_not_configured_audio_providers(app, monkeypatch)
    queued: list[tuple[str, str]] = []

    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: queued.append((project_id, source_id)),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "音频 provider 未配置上传测试",
                "scenario_type": "general",
                "summary": "验证音频 provider 未配置时不会伪装成 processing。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )

    assert upload_response.status_code == 201
    source = upload_response.json()
    assert_source_payload_is_neutral_only(source)
    assert source["source_kind"] == "audio"
    assert source["normalize_status"] == "not_configured"
    assert source["index_status"] == "normalization_failed"
    assert source["normalized_path"] is None
    assert source["index_input_mode"] is None
    assert "七牛" in (source["normalize_summary"] or "")
    assert "阿里云" in (source["normalize_summary"] or "")
    assert "尚未进入项目知识库" in (source["index_error"] or "")
    assert queued == []

    stored = app.state.services.catalog.get_source(source["id"])
    assert stored is not None
    assert stored.normalize_status == "not_configured"
    assert stored.index_status == "normalization_failed"
    assert stored.normalize_summary == source["normalize_summary"]
    assert stored.index_error == source["index_error"]


def test_audio_reindex_restarts_transcription_when_normalized_text_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    queued: list[tuple[str, str]] = []

    install_ready_audio_providers(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: queued.append((project_id, source_id)),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "音频重试测试",
                "scenario_type": "general",
                "summary": "验证音频缺少 normalized text 时会重新发起转写。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )
        assert upload_response.status_code == 201
        created_source = upload_response.json()
        assert_source_payload_is_neutral_only(created_source)
        source_id = created_source["id"]

        app.state.services.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=None,
            index_input_mode=None,
            normalize_status="failed",
            normalize_summary="阿里云转写超时。",
            index_status="normalization_failed",
            index_error="资料标准化失败，尚未进入项目知识库。阿里云转写超时。",
        )

        failed_readiness_response = client.get(f"/api/projects/{project_id}/readiness")
        reindex_response = client.post(
            f"/api/projects/{project_id}/sources/{source_id}/reindex",
        )
        refreshed_readiness_response = client.get(f"/api/projects/{project_id}/readiness")

    assert failed_readiness_response.status_code == 200
    failed_readiness = failed_readiness_response.json()
    assert "processing_audio_sources=0" in (failed_readiness["object_storage"]["detail"] or "")
    assert "failed_audio_sources=1" in (failed_readiness["audio_transcription"]["detail"] or "")

    assert reindex_response.status_code == 200
    payload = reindex_response.json()
    assert_source_payload_is_neutral_only(payload)
    assert payload["id"] == source_id
    assert payload["source_kind"] == "audio"
    assert payload["normalize_status"] == "processing"
    assert payload["index_status"] == "normalization_pending"
    assert payload["normalized_path"] is None
    assert "自动进入项目知识库" in payload["index_error"]
    assert queued == [(project_id, source_id), (project_id, source_id)]

    refreshed = app.state.services.catalog.get_source(source_id)
    assert refreshed is not None
    assert refreshed.normalize_status == "processing"
    assert refreshed.index_status == "normalization_pending"

    assert refreshed_readiness_response.status_code == 200
    refreshed_readiness = refreshed_readiness_response.json()
    assert "processing_audio_sources=1" in (refreshed_readiness["object_storage"]["detail"] or "")
    assert "failed_audio_sources=0" in (refreshed_readiness["audio_transcription"]["detail"] or "")


def test_audio_reindex_reports_not_configured_when_audio_providers_are_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    queued: list[tuple[str, str]] = []

    install_ready_audio_providers(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: queued.append((project_id, source_id)),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "音频 provider 未配置重试测试",
                "scenario_type": "general",
                "summary": "验证音频 provider 未配置时 reindex 会同步报未配置。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )
        assert upload_response.status_code == 201
        created_source = upload_response.json()
        source_id = created_source["id"]
        assert queued == [(project_id, source_id)]
        queued.clear()

        app.state.services.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=None,
            index_input_mode=None,
            normalize_status="failed",
            normalize_summary="阿里云转写超时。",
            index_status="normalization_failed",
            index_error="资料标准化失败，尚未进入项目知识库。阿里云转写超时。",
        )
        install_not_configured_audio_providers(app, monkeypatch)

        reindex_response = client.post(
            f"/api/projects/{project_id}/sources/{source_id}/reindex",
        )

    assert reindex_response.status_code == 200
    payload = reindex_response.json()
    assert_source_payload_is_neutral_only(payload)
    assert payload["id"] == source_id
    assert payload["source_kind"] == "audio"
    assert payload["normalize_status"] == "not_configured"
    assert payload["index_status"] == "normalization_failed"
    assert payload["normalized_path"] is None
    assert payload["index_input_mode"] is None
    assert "七牛" in (payload["normalize_summary"] or "")
    assert "阿里云" in (payload["normalize_summary"] or "")
    assert queued == []

    refreshed = app.state.services.catalog.get_source(source_id)
    assert refreshed is not None
    assert refreshed.normalize_status == "not_configured"
    assert refreshed.index_status == "normalization_failed"
    assert refreshed.normalize_summary == payload["normalize_summary"]
    assert refreshed.index_error == payload["index_error"]


def test_audio_reindex_repairs_stale_processing_when_audio_providers_are_unavailable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    queued: list[tuple[str, str]] = []

    install_ready_audio_providers(app, monkeypatch)
    monkeypatch.setattr(
        app.state.services.audio_ingestion,
        "process_source",
        lambda project_id, source_id: queued.append((project_id, source_id)),
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "音频 processing 卡死修复测试",
                "scenario_type": "general",
                "summary": "验证 processing 音频在 provider 未配置时 reindex 会同步修正状态。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={"upload_kind": "file", "name": "call.mp3"},
            files={"file": ("call.mp3", b"ID3", "audio/mpeg")},
        )
        assert upload_response.status_code == 201
        created_source = upload_response.json()
        source_id = created_source["id"]
        assert queued == [(project_id, source_id)]
        queued.clear()

        app.state.services.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=None,
            index_input_mode=None,
            normalize_status="processing",
            normalize_summary="音频正在转写，完成后会自动进入项目知识库。",
            index_status="normalization_pending",
            index_error="音频正在转写，完成后会自动进入项目知识库。",
        )
        install_not_configured_audio_providers(app, monkeypatch)

        reindex_response = client.post(
            f"/api/projects/{project_id}/sources/{source_id}/reindex",
        )

    assert reindex_response.status_code == 200
    payload = reindex_response.json()
    assert_source_payload_is_neutral_only(payload)
    assert payload["id"] == source_id
    assert payload["source_kind"] == "audio"
    assert payload["normalize_status"] == "not_configured"
    assert payload["index_status"] == "normalization_failed"
    assert payload["normalized_path"] is None
    assert payload["index_input_mode"] is None
    assert "七牛" in (payload["normalize_summary"] or "")
    assert "阿里云" in (payload["normalize_summary"] or "")
    assert queued == []

    refreshed = app.state.services.catalog.get_source(source_id)
    assert refreshed is not None
    assert refreshed.normalize_status == "not_configured"
    assert refreshed.index_status == "normalization_failed"
    assert refreshed.normalize_summary == payload["normalize_summary"]
    assert refreshed.index_error == payload["index_error"]


def test_source_route_persists_neutral_ingestion_fields_without_legacy_writes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_not_configured_evidence_runtime(app, monkeypatch)

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "中性语义映射测试",
                "scenario_type": "general",
                "summary": "验证 route 内部 normalize/index 语义只写 neutral 字段",
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
    assert_source_payload_is_neutral_only(source)
    stored_source = app.state.services.catalog.get_source(source["id"])

    assert stored_source is not None
    assert stored_source.index_input_mode == "direct_text"
    assert stored_source.normalize_status == "parsed"
    assert stored_source.normalize_summary == "这里是一段文本资料。"
    assert source["index_input_mode"] == "direct_text"
    assert source["normalize_status"] == "parsed"
    assert source["normalize_summary"] == "这里是一段文本资料。"

    connection = sqlite3.connect(app.state.services.settings.sqlite_path)
    try:
        stored = fetch_source_storage(connection, source["id"])
    finally:
        connection.close()

    assert_source_neutral_write_storage(
        stored,
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="这里是一段文本资料。",
        index_status="not_configured",
        index_error_predicate=lambda value: any(
            marker in (value or "")
            for marker in ("未配置", "没有安装", "请先安装")
        ),
    )


def test_chat_stream_keeps_evidence_runtime_as_agent_tool(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    assert app.state.services.chat_service.evidence_runtime is app.state.services.evidence_runtime
    assert not hasattr(app.state.services, "notebooklm")

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
        app.state.services.evidence_runtime,
        "query",
        fake_evidence_query,
    )
    monkeypatch.setattr(app.state.services.agent_runtime, "ensure_available", lambda: None)

    async def fake_run_streaming_turn(turn):
        yield ("message_chunk", {"text": "基于项目知识库先给出一轮判断。"})
        yield ("done", {})

    monkeypatch.setattr(
        app.state.services.agent_runtime,
        "run_streaming_turn",
        fake_run_streaming_turn,
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
    assert evidence_calls == []
    assert "基于项目知识库先给出一轮判断。" in response.text


def test_reindex_converts_synced_source_to_indexed_status(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    assert not hasattr(app.state.services, "notebooklm")

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
                "summary": "验证 legacy synced 状态的资料在 reindex 后会升级为 indexed",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "兼容性资料",
                "text_content": "这条资料用于验证 legacy synced 状态在 reindex 后会升级为 indexed。",
            },
        )
        assert upload_response.status_code == 201
        source = upload_response.json()
        assert_source_payload_is_neutral_only(source)
        app.state.services.catalog.update_source_index_status(
            source_id=source["id"],
            index_status="synced",
            index_error=None,
        )

        reindex_response = client.post(
            f"/api/projects/{project_id}/sources/{source['id']}/reindex",
        )
        assert reindex_response.status_code == 200
        reindexed_source = reindex_response.json()
        assert_source_payload_is_neutral_only(reindexed_source)
        assert reindexed_source["id"] == source["id"]
        assert reindexed_source["normalize_status"] == "parsed"
        assert reindexed_source["index_status"] == "indexed"
        assert reindexed_source["index_error"] is None


def test_delete_source_tolerates_evidence_cleanup_failures(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    assert not hasattr(app.state.services, "notebooklm")
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
                "summary": "验证证据层清理失败时资料仍可从本地删除",
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
        app.state.services.catalog.update_source_index_status(
            source_id=source_id,
            index_status="synced",
            index_error=None,
        )

        delete_response = client.delete(f"/api/projects/{project_id}/sources/{source_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["deleted"] is True
        sources_response = client.get(f"/api/projects/{project_id}/sources")
        assert sources_response.status_code == 200
        assert sources_response.json() == []


def test_delete_project_tolerates_evidence_cleanup_failures_and_cascades_local_data(
    tmp_path: Path,
    monkeypatch,
) -> None:
    app = create_app(make_settings(tmp_path))
    assert not hasattr(app.state.services, "notebooklm")
    monkeypatch.setattr(
        app.state.services.evidence_runtime,
        "delete_project",
        lambda project_id: (_ for _ in ()).throw(
            ProviderIssue(
                provider="QDRANT_LLAMA_INDEX",
                message="Qdrant collection 清理失败。",
                status_code=503,
            )
        ),
        raising=False,
    )

    with TestClient(app) as client:
        create_response = client.post(
            "/api/projects",
            json={
                "name": "待删除项目",
                "scenario_type": "general",
                "summary": "验证项目删除时本地级联清理仍会完成。",
            },
        )
        assert create_response.status_code == 201
        project_id = create_response.json()["id"]

        upload_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "待删除资料",
                "text_content": "这是一条会跟着项目一起被删除的资料。",
            },
        )
        assert upload_response.status_code == 201
        source_id = upload_response.json()["id"]

        knowledge_base = app.state.services.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider="QDRANT_LLAMA_INDEX",
            external_knowledge_base_id=f"kb-{project_id}",
            display_name="待删除项目 Evidence KB",
            description="测试项目知识库",
            status="ready",
            status_error=None,
        )
        app.state.services.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=[
                {
                    "knowledge_base_id": knowledge_base.id,
                    "chunk_order": 0,
                    "modality": "text",
                    "content": "项目删除测试 chunk",
                    "embedding_status": "indexed",
                    "index_error": None,
                    "indexed_at": "2026-04-24T10:00:00+08:00",
                }
            ],
        )
        app.state.services.catalog.create_message(
            project_id=project_id,
            role="assistant",
            content="这是一条会跟着项目一起被删除的消息。",
        )
        app.state.services.project_state.replace_category(
            project_id=project_id,
            category="current_understanding",
            items=[
                StateItem(
                    id="state-delete-project",
                    title="删除项目测试",
                    body="验证 state_items 会跟随项目一起清理。",
                )
            ],
        )
        app.state.services.project_state.create_version(
            project_id=project_id,
            trigger_kind="project_delete_test",
            summary="验证版本快照也会随项目一起删除。",
        )

        artifact_dir = app.state.services.settings.projects_dir / project_id / "artifacts" / "page_solution"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "index.html"
        artifact_path.write_text("<html><body>delete me</body></html>", encoding="utf-8")
        app.state.services.catalog.save_artifact(
            project_id=project_id,
            artifact_type="page_solution",
            title="待删除页面方案",
            summary="这份交付物会跟着项目一起删除。",
            status="generated",
            content_format="html",
            storage_path=str(artifact_path),
            body=None,
        )

        delete_response = client.delete(f"/api/projects/{project_id}")
        assert delete_response.status_code == 200
        deleted_payload = delete_response.json()
        assert deleted_payload["id"] == project_id
        assert deleted_payload["name"] == "待删除项目"
        assert deleted_payload["deleted"] is True
        assert deleted_payload["warning"] == "Qdrant collection 清理失败。"

        project_response = client.get(f"/api/projects/{project_id}")
        assert project_response.status_code == 404

    assert not (app.state.services.settings.projects_dir / project_id).exists()

    connection = sqlite3.connect(app.state.services.settings.sqlite_path)
    try:
        for table_name in (
            "projects",
            "sources",
            "messages",
            "state_items",
            "version_snapshots",
            "knowledge_bases",
            "source_chunks",
            "demo_artifacts",
        ):
            row = connection.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE project_id = ?"
                if table_name != "projects"
                else "SELECT COUNT(*) FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            assert row is not None
            assert row[0] == 0
    finally:
        connection.close()


def test_delete_seed_project_is_rejected(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        delete_response = client.delete("/api/projects/seed-reconciliation")

    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "默认 seed project 不能删除。"


def test_chat_image_preview_returns_generated_file(tmp_path: Path) -> None:
    app = create_app(make_settings(tmp_path))

    with TestClient(app) as client:
        image_dir = (
            app.state.services.settings.projects_dir
            / "seed-reconciliation"
            / "chat-images"
            / "image-test123"
        )
        image_dir.mkdir(parents=True, exist_ok=True)
        (image_dir / "image.png").write_bytes(b"fake-png")

        response = client.get("/api/projects/seed-reconciliation/chat-images/image-test123")

    assert response.status_code == 200
    assert response.content == b"fake-png"


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


def test_e2e_upload_index_chat_returns_rag_citations(tmp_path: Path, monkeypatch) -> None:
    app = create_app(make_settings(tmp_path))
    install_fake_evidence_runtime(app, monkeypatch)
    monkeypatch.setattr(app.state.services.agent_runtime, "ensure_available", lambda: None)

    async def fake_agent_turn(turn):
        result = app.state.services.evidence_runtime.query(
            turn.project.id,
            "对账差异怎么处理？",
            selected_source_ids=turn.selected_source_ids,
        )
        citations = [citation.model_dump() for citation in result.citations]
        yield (
            "assistant_status",
            {"phase": "tool_running:query_project_evidence", "label": "检索项目知识库"},
        )
        yield (
            "citations",
            {"items": citations},
        )
        yield (
            "final_message",
            {
                "text": f"根据项目知识库：{result.summary}",
                "citations": citations,
            },
        )
        yield ("done", {})

    monkeypatch.setattr(
        app.state.services.agent_runtime,
        "run_streaming_turn",
        fake_agent_turn,
    )

    with TestClient(app) as client:
        project_response = client.post(
            "/api/projects",
            json={
                "name": "RAG 问答 e2e",
                "scenario_type": "finance-reconciliation",
                "summary": "验证上传资料后通过项目知识库回答并返回引用。",
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]

        init_response = client.post(f"/api/projects/{project_id}/knowledge-base/init")
        assert init_response.status_code == 201
        assert init_response.json()["status"] == "ready"

        source_response = client.post(
            f"/api/projects/{project_id}/sources",
            data={
                "upload_kind": "text",
                "name": "对账规则.md",
                "text_content": "对账差异超过 100 元时必须进入人工复核，并记录差异原因。",
            },
        )
        assert source_response.status_code == 201
        source = source_response.json()
        assert source["normalize_status"] == "parsed"
        assert source["index_status"] == "indexed"

        chat_response = client.post(
            f"/api/projects/{project_id}/chat/stream",
            json={
                "message": "对账差异怎么处理？",
                "selected_source_ids": [source["id"]],
                "request_artifact_types": [],
            },
        )

        assert chat_response.status_code == 200
        stream_text = chat_response.text
        assert "event: citations" in stream_text
        assert "event: final_message" not in stream_text
        assert "根据项目知识库" in stream_text
        assert "对账规则.md" in stream_text
        assert source["id"] in stream_text
        assert "人工复核" in stream_text

        messages_response = client.get(f"/api/projects/{project_id}/messages")
        assert messages_response.status_code == 200
        messages = messages_response.json()
        assistant_message = next(message for message in messages if message["role"] == "assistant")
        assert assistant_message["source_refs"]
        assert assistant_message["source_refs"][0]["source_id"] == source["id"]
