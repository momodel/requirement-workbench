from __future__ import annotations

import json
from pathlib import Path
import uuid

import pytest

from app.services import vector_store as vector_store_module
from app.config import AppSettings
from app.db import init_db
from app.models import ChatCitation, CreateProjectRequest, ProviderIssue, ProviderReadiness
from app.services.evidence_indexing import load_source_text
from app.services.evidence_runtime import EVIDENCE_PROVIDER, QdrantLlamaIndexEvidenceRuntime
from app.services.project_catalog import ProjectCatalog
from app.services.vector_store import QdrantLlamaIndexVectorStore, VectorDocument, VectorQueryHit


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


class FakeVectorStore:
    def __init__(self) -> None:
        self.available = False
        self.documents_by_project: dict[str, list[VectorDocument]] = {}
        self.ensure_calls: list[str] = []
        self.deleted_sources: list[tuple[str, str]] = []
        self.last_query_source_ids: list[str] | None = None
        self.override_hits: list[VectorQueryHit] | None = None

    def ensure_available(self) -> Path:
        self.available = True
        root = Path("/fake-qdrant")
        return root

    def collection_name(self, project_id: str) -> str:
        return f"project__{project_id}"

    def ensure_collection(self, project_id: str) -> str:
        self.ensure_calls.append(project_id)
        self.documents_by_project.setdefault(project_id, [])
        return self.collection_name(project_id)

    def upsert(
        self,
        project_id: str,
        documents: list[VectorDocument],
    ) -> None:
        existing = [doc for doc in self.documents_by_project.get(project_id, []) if doc.source_id != documents[0].source_id]
        self.documents_by_project[project_id] = existing + list(documents)

    def delete_source(self, project_id: str, source_id: str) -> None:
        self.deleted_sources.append((project_id, source_id))
        self.documents_by_project[project_id] = [
            doc for doc in self.documents_by_project.get(project_id, []) if doc.source_id != source_id
        ]

    def query(
        self,
        project_id: str,
        question: str,
        *,
        top_k: int,
        source_ids: list[str] | None = None,
    ) -> list[VectorQueryHit]:
        self.last_query_source_ids = list(source_ids) if source_ids is not None else None
        if self.override_hits is not None:
            return list(self.override_hits)

        lowered_question = question.lower()
        hits: list[VectorQueryHit] = []
        for document in self.documents_by_project.get(project_id, []):
            if source_ids and document.source_id not in source_ids:
                continue
            score = 1.0
            if lowered_question and lowered_question not in document.text.lower():
                score = 0.2
            hits.append(
                VectorQueryHit(
                    chunk_id=document.chunk_id,
                    source_id=document.source_id,
                    text=document.text,
                    score=score,
                    metadata=dict(document.metadata),
                )
            )
        hits.sort(key=lambda item: item.score or 0.0, reverse=True)
        return hits[:top_k]


class MissingDependencyVectorStore(FakeVectorStore):
    def ensure_available(self) -> Path:
        raise ProviderIssue(
            provider=EVIDENCE_PROVIDER,
            message="当前后端环境没有安装 LlamaIndex Qdrant/FastEmbed 依赖。请先在 backend 虚拟环境里安装 Task 3 所需依赖。",
        )


def _create_source_file(base_dir: Path, name: str, content: str) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / name
    path.write_text(content, encoding="utf-8")
    return path


def _create_binary_source_file(base_dir: Path, name: str, content: bytes) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / name
    path.write_bytes(content)
    return path


def test_ensure_project_knowledge_base_initializes_catalog_record(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="证据项目",
            scenario_type="general",
            summary="测试项目级知识库初始化",
        )
    )
    vector_store = FakeVectorStore()
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=vector_store,
    )

    knowledge_base = runtime.ensure_project_knowledge_base(project.id)
    persisted = catalog.get_knowledge_base(project_id=project.id, provider=EVIDENCE_PROVIDER)

    assert vector_store.available is True
    assert vector_store.ensure_calls == [project.id]
    assert knowledge_base.provider == EVIDENCE_PROVIDER
    assert knowledge_base.external_knowledge_base_id == vector_store.collection_name(project.id)
    assert knowledge_base.status == "ready"
    assert persisted == knowledge_base


def test_query_passes_selected_source_ids_to_vector_store_and_filters_results(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="过滤项目",
            scenario_type="general",
            summary="测试 selected_source_ids 过滤",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    path_a = _create_source_file(source_dir, "a.md", "退款规则需要独立映射口径。")
    path_b = _create_source_file(source_dir, "b.md", "对账规则也涉及映射，但重点是财务科目确认。")
    source_a = catalog.create_source(
        project_id=project.id,
        name="退款规则.md",
        source_kind="text",
        upload_kind="text",
        storage_path=str(path_a),
        normalized_path=str(path_a),
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="退款规则",
        index_status="pending_sync",
        index_error=None,
    )
    source_b = catalog.create_source(
        project_id=project.id,
        name="对账规则.md",
        source_kind="text",
        upload_kind="text",
        storage_path=str(path_b),
        normalized_path=str(path_b),
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="对账规则",
        index_status="pending_sync",
        index_error=None,
    )
    vector_store = FakeVectorStore()
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=vector_store,
    )

    runtime.index_source(project.id, source_a.id)
    runtime.index_source(project.id, source_b.id)

    result = runtime.query(
        project.id,
        "映射规则是什么？",
        selected_source_ids=[source_b.id],
    )

    assert vector_store.last_query_source_ids == [source_b.id]
    assert result.sync_status == "queried"
    assert result.citations
    assert {citation.source_id for citation in result.citations} == {source_b.id}
    assert all(citation.title == "对账规则.md" for citation in result.citations)
    assert "财务科目确认" in result.summary
    assert "退款规则" not in result.summary


def test_query_shapes_citations_and_deduplicates_duplicate_hits(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="引用项目",
            scenario_type="general",
            summary="测试 citation shaping",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    path = _create_source_file(
        source_dir,
        "orders.md",
        "订单金额字段和财务科目映射口径不一致，需要补人工确认。",
    )
    source = catalog.create_source(
        project_id=project.id,
        name="订单字段说明.md",
        source_kind="text",
        upload_kind="text",
        storage_path=str(path),
        normalized_path=str(path),
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="订单字段说明",
        index_status="pending_sync",
        index_error=None,
    )
    vector_store = FakeVectorStore()
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=vector_store,
    )

    indexed_chunks = runtime.index_source(project.id, source.id)
    assert indexed_chunks
    chunk = indexed_chunks[0]
    vector_store.override_hits = [
        VectorQueryHit(
            chunk_id=chunk.id,
            source_id=source.id,
            text=chunk.content,
            score=0.92,
            metadata={"source_id": source.id},
        ),
        VectorQueryHit(
            chunk_id=chunk.id,
            source_id=source.id,
            text=chunk.content,
            score=0.91,
            metadata={"source_id": source.id},
        ),
    ]

    result = runtime.query(project.id, "当前核心冲突是什么？")

    assert result.sync_status == "queried"
    assert result.citations == [
        ChatCitation(
            title="订单字段说明.md",
            snippet="订单金额字段和财务科目映射口径不一致，需要补人工确认。",
            source_id=source.id,
        )
    ]
    assert "已检索到 1 条相关证据" in result.summary
    assert "订单字段说明.md" in result.summary


def test_query_filters_hits_for_sources_deleted_from_catalog(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="删除过滤项目",
            scenario_type="general",
            summary="测试删除后的 ghost vector 不会继续出现在查询里",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    path = _create_source_file(
        source_dir,
        "deleted.md",
        "这条资料稍后会被删除，但向量命中仍会残留。",
    )
    source = catalog.create_source(
        project_id=project.id,
        name="待删除资料.md",
        source_kind="text",
        upload_kind="text",
        storage_path=str(path),
        normalized_path=str(path),
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="待删除资料",
        index_status="indexed",
        index_error=None,
    )
    vector_store = FakeVectorStore()
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=vector_store,
    )

    indexed_chunks = runtime.index_source(project.id, source.id)
    assert indexed_chunks
    chunk = indexed_chunks[0]
    vector_store.override_hits = [
        VectorQueryHit(
            chunk_id=chunk.id,
            source_id=source.id,
            text=chunk.content,
            score=0.95,
            metadata={"source_id": source.id, "source_name": source.name},
        )
    ]
    deleted = catalog.delete_source(source.id)
    assert deleted.id == source.id

    result = runtime.query(project.id, "删除后的资料还会被引用吗？")

    assert result.sync_status == "queried"
    assert result.citations == []
    assert result.summary == "当前项目知识库里没有检索到相关证据。"


def test_index_source_rejects_url_without_normalized_page_text(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="URL 项目",
            scenario_type="general",
            summary="测试 URL 不能用裸链接文本冒充可索引正文",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    url_path = _create_source_file(
        source_dir,
        "refund-policy.url.txt",
        "https://docs.example.com/help/refund-policy",
    )
    source = catalog.create_source(
        project_id=project.id,
        name="退款规则链接",
        source_kind="url",
        upload_kind="url",
        storage_path=str(url_path),
        normalized_path=None,
        index_input_mode=None,
        normalize_status="pending",
        normalize_summary="URL 已记录，但还没有抓取到页面正文。",
        index_status="normalization_pending",
        index_error="URL 已记录，但还没有抓取到页面正文；生成 normalized text 前不会进入项目知识库。",
    )
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(ProviderIssue, match="尚未完成可索引文本标准化"):
        runtime.index_source(project.id, source.id)


def test_index_source_rejects_binary_source_without_normalized_text(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="二进制项目",
            scenario_type="general",
            summary="测试二进制 source 索引边界",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    binary_path = _create_binary_source_file(source_dir, "spec.pdf", b"%PDF-1.4\x00\x81\x82binary")
    source = catalog.create_source(
        project_id=project.id,
        name="需求说明.pdf",
        source_kind="pdf",
        upload_kind="file",
        storage_path=str(binary_path),
        normalized_path=None,
        index_input_mode="file_upload",
        normalize_status="parsed",
        normalize_summary="这是 PDF 摘要，但还没有标准化文本。",
        index_status="pending_sync",
        index_error=None,
    )
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(ProviderIssue, match="尚未完成可索引文本标准化"):
        runtime.index_source(project.id, source.id)


def test_indexed_image_and_audio_chunks_keep_source_level_locator(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="多模态项目",
            scenario_type="general",
            summary="验证 text-first locator",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    image_text = _create_source_file(
        source_dir,
        "flowchart.normalized.md",
        "OCR: 退款审批流包含财务复核节点",
    )
    audio_text = _create_source_file(
        source_dir,
        "interview.normalized.md",
        "00:00-00:20 客户要求逐笔核对订单与财务入账",
    )
    image_source = catalog.create_source(
        project_id=project.id,
        name="流程图.png",
        source_kind="image",
        upload_kind="file",
        storage_path=str(source_dir / "flowchart.png"),
        normalized_path=str(image_text),
        index_input_mode="normalized_text",
        normalize_status="parsed",
        normalize_summary="OCR 已提取流程图文本。",
        index_status="pending",
        index_error=None,
    )
    audio_source = catalog.create_source(
        project_id=project.id,
        name="访谈录音.mp3",
        source_kind="audio",
        upload_kind="file",
        storage_path=str(source_dir / "interview.mp3"),
        normalized_path=str(audio_text),
        index_input_mode="normalized_text",
        normalize_status="parsed",
        normalize_summary="ASR 已生成转写文本。",
        index_status="pending",
        index_error=None,
    )
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=FakeVectorStore(),
    )

    runtime.index_source(project.id, image_source.id)
    runtime.index_source(project.id, audio_source.id)

    chunks = catalog.list_source_chunks(project_id=project.id)
    locators = [json.loads(chunk.locator_json or "{}") for chunk in chunks]
    locator_pairs = [
        {key: value for key, value in locator.items() if key in {"source_kind", "locator_kind"}}
        for locator in locators
    ]
    assert {"source_kind": "image", "locator_kind": "source_level"} in locator_pairs
    assert {"source_kind": "audio", "locator_kind": "source_level"} in locator_pairs


def test_preparation_failure_marks_knowledge_base_error_and_project_readiness(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="失败项目",
            scenario_type="general",
            summary="测试准备失败状态",
        )
    )
    source_dir = settings.projects_dir / project.id / "sources"
    binary_path = _create_binary_source_file(source_dir, "voice.wav", b"RIFF\x00\x00\x00\x00WAVEfmt ")
    source = catalog.create_source(
        project_id=project.id,
        name="访谈录音.wav",
        source_kind="audio",
        upload_kind="file",
        storage_path=str(binary_path),
        normalized_path=None,
        index_input_mode="file_upload",
        normalize_status="parsed",
        normalize_summary="录音摘要",
        index_status="pending_sync",
        index_error=None,
    )
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=catalog,
        vector_store=FakeVectorStore(),
    )

    with pytest.raises(ProviderIssue, match="尚未完成可索引文本标准化"):
        runtime.index_source(project.id, source.id)

    knowledge_base = catalog.get_knowledge_base(project_id=project.id, provider=EVIDENCE_PROVIDER)
    readiness = runtime.get_project_readiness(
        project.id,
        claude=ProviderReadiness(
            provider="CLAUDE_AGENT_SDK",
            status="ready",
            summary="Claude ready",
        ),
    )

    assert knowledge_base is not None
    assert knowledge_base.status == "error"
    assert knowledge_base.status_error is not None
    assert "尚未完成可索引文本标准化" in knowledge_base.status_error
    assert catalog.list_source_chunks(project_id=project.id, source_id=source.id) == []
    assert readiness.status == "error"
    assert "尚未完成可索引文本标准化" in (readiness.detail or "")


def test_global_readiness_reports_missing_provider_dependency(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=ProjectCatalog(settings),
        vector_store=MissingDependencyVectorStore(),
    )

    readiness = runtime.get_global_readiness()

    assert readiness == ProviderReadiness(
        provider=EVIDENCE_PROVIDER,
        status="not_configured",
        summary="项目内证据运行时未就绪。",
        detail="当前后端环境没有安装 LlamaIndex Qdrant/FastEmbed 依赖。请先在 backend 虚拟环境里安装 Task 3 所需依赖。",
        action_label="安装 Qdrant/LlamaIndex 依赖",
    )


def test_global_readiness_reports_missing_fastembed_runtime_dependency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    runtime = QdrantLlamaIndexEvidenceRuntime(
        settings=settings,
        catalog=ProjectCatalog(settings),
    )

    monkeypatch.setattr(runtime.vector_store, "_load_qdrant_client_class", lambda: object)
    monkeypatch.setattr(runtime.vector_store, "_load_qdrant_models", lambda: object())
    monkeypatch.setattr(runtime.vector_store, "_get_client", lambda: object())

    def fake_import_module(name: str):
        if name == "llama_index.vector_stores.qdrant":
            return object()
        if name == "llama_index.embeddings.fastembed":
            return type("FastEmbedModule", (), {"FastEmbedEmbedding": object})()
        if name == "fastembed":
            raise ModuleNotFoundError("No module named 'fastembed'")
        raise AssertionError(f"unexpected import in readiness test: {name}")

    monkeypatch.setattr(
        vector_store_module.importlib,
        "import_module",
        fake_import_module,
    )

    readiness = runtime.get_global_readiness()

    assert readiness == ProviderReadiness(
        provider=EVIDENCE_PROVIDER,
        status="not_configured",
        summary="项目内证据运行时未就绪。",
        detail="当前后端环境没有安装 LlamaIndex Qdrant/FastEmbed 依赖。请先在 backend 虚拟环境里安装 Task 3 所需依赖。",
        action_label="安装 Qdrant/LlamaIndex 依赖",
    )


def test_ensure_collection_wraps_remote_connection_error(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    store = QdrantLlamaIndexVectorStore(settings)

    class FailingClient:
        def collection_exists(self, collection_name: str) -> bool:
            raise RuntimeError("ConnectError")

    store._client = FailingClient()

    with pytest.raises(ProviderIssue, match="检查 collection 是否存在"):
        store.ensure_collection("project-1")


def test_vector_store_upsert_uses_qdrant_compatible_point_ids(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    store = QdrantLlamaIndexVectorStore(settings)

    captured: dict[str, object] = {}

    class FakePointStruct:
        def __init__(self, *, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload

    class FakeModels:
        PointStruct = FakePointStruct

    class FakeClient:
        def upsert(self, *, collection_name, points, wait):
            captured["collection_name"] = collection_name
            captured["points"] = points
            captured["wait"] = wait

    monkeypatch.setattr(store, "ensure_collection", lambda project_id: "project__project-1")
    monkeypatch.setattr(store, "_load_qdrant_models", lambda: FakeModels)
    monkeypatch.setattr(store, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(store, "_embed_text", lambda text, query=False: [0.1, 0.2, 0.3])

    document = VectorDocument(
        chunk_id="chunk-src-e4e4dc5af1-0-8de84d2414",
        source_id="src-e4e4dc5af1",
        text="订单金额字段与财务科目映射口径不一致，需要逐笔核对。",
        metadata={"chunk_order": 0},
    )

    store.upsert("project-1", [document])

    points = captured["points"]
    assert isinstance(points, list)
    assert len(points) == 1
    point = points[0]
    assert point.payload["chunk_id"] == document.chunk_id
    assert point.id != document.chunk_id
    assert str(uuid.UUID(point.id)) == point.id
