from __future__ import annotations

from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    ChatCitation,
    EvidenceResult,
    KnowledgeBaseRecord,
    ProviderIssue,
    ProviderReadiness,
    SourceChunkRecord,
)
from .evidence_indexing import prepare_source_chunks
from .project_catalog import ProjectCatalog, now_iso
from .vector_store import (
    EVIDENCE_PROVIDER,
    QdrantLlamaIndexVectorStore,
    VectorQueryHit,
)


class QdrantLlamaIndexEvidenceRuntime:
    def __init__(
        self,
        settings: AppSettings = DEFAULT_SETTINGS,
        *,
        catalog: ProjectCatalog | None = None,
        vector_store: QdrantLlamaIndexVectorStore | None = None,
    ):
        self.settings = settings
        self.catalog = catalog or ProjectCatalog(settings)
        self.vector_store = vector_store or QdrantLlamaIndexVectorStore(settings)

    def ensure_available(self) -> Path:
        if self.settings.evidence_backend != "qdrant_llamaindex":
            raise ProviderIssue(
                provider=EVIDENCE_PROVIDER,
                message=(
                    "当前 evidence backend 不是 qdrant_llamaindex。"
                    "请先把 REQUIREMENT_WORKBENCH_EVIDENCE_BACKEND 配成 qdrant_llamaindex。"
                ),
            )
        return self.vector_store.ensure_available()

    def get_global_readiness(self) -> ProviderReadiness:
        try:
            location = self.ensure_available()
        except ProviderIssue as exc:
            status = "error"
            action_label = "检查 Qdrant/LlamaIndex 配置"
            if (
                "没有安装" in exc.message
                or "缺少" in exc.message
                or "backend 不是 qdrant_llamaindex" in exc.message
            ):
                status = "not_configured"
                action_label = "安装 Qdrant/LlamaIndex 依赖"
            if "backend 不是 qdrant_llamaindex" in exc.message:
                action_label = "切换 evidence backend"
            return ProviderReadiness(
                provider=EVIDENCE_PROVIDER,
                status=status,
                summary="项目内证据运行时未就绪。",
                detail=exc.message,
                action_label=action_label,
            )

        detail = f"Qdrant path: {location}"
        if self.settings.qdrant_url:
            detail = f"Qdrant url: {self.settings.qdrant_url}"
        return ProviderReadiness(
            provider=EVIDENCE_PROVIDER,
            status="ready",
            summary="项目内证据运行时已就绪。",
            detail=detail,
        )

    def _get_project_readiness(
        self,
        project_id: str,
        claude: ProviderReadiness | None = None,
    ) -> ProviderReadiness:
        project = self.catalog.get_project(project_id)
        if not project:
            return ProviderReadiness(
                provider=EVIDENCE_PROVIDER,
                status="missing",
                summary="项目不存在。",
                detail=f"找不到 project_id={project_id}。",
            )

        global_readiness = self.get_global_readiness()
        if global_readiness.status != "ready":
            return global_readiness

        knowledge_base = self.catalog.get_knowledge_base(
            project_id=project_id,
            provider=EVIDENCE_PROVIDER,
        )
        if knowledge_base is None:
            return ProviderReadiness(
                provider=EVIDENCE_PROVIDER,
                status="knowledge_base_missing",
                summary="当前项目还没有初始化项目内知识库。",
                detail="需要先创建项目级 collection，并为 source 建立本地向量索引。",
                action_label="初始化知识库",
            )

        chunks = self.catalog.list_source_chunks(
            project_id=project_id,
            knowledge_base_id=knowledge_base.id,
        )
        failed_chunks = [chunk for chunk in chunks if chunk.embedding_status == "failed"]
        pending_chunks = [chunk for chunk in chunks if chunk.embedding_status != "indexed"]

        if knowledge_base.status == "error":
            return ProviderReadiness(
                provider=EVIDENCE_PROVIDER,
                status="error",
                summary="项目内知识库状态异常。",
                detail=knowledge_base.status_error or "知识库标记为 error。",
                action_label="重新索引 source",
            )
        if not chunks:
            return ProviderReadiness(
                provider=EVIDENCE_PROVIDER,
                status="empty",
                summary="项目内知识库已创建，但还没有索引任何资料。",
                detail=f"Collection: {knowledge_base.external_knowledge_base_id}",
                action_label="索引 source",
            )
        if failed_chunks:
            return ProviderReadiness(
                provider=EVIDENCE_PROVIDER,
                status="degraded",
                summary="项目内知识库已有资料，但存在索引失败的分块。",
                detail=failed_chunks[0].index_error or "至少有一个 chunk 索引失败。",
                action_label="重新索引 source",
            )
        if pending_chunks:
            return ProviderReadiness(
                provider=EVIDENCE_PROVIDER,
                status="indexing",
                summary="项目内知识库正在索引资料。",
                detail=f"Collection: {knowledge_base.external_knowledge_base_id}",
            )

        return ProviderReadiness(
            provider=EVIDENCE_PROVIDER,
            status="ready",
            summary="当前项目知识库可用于证据检索。",
            detail=(
                f"Collection: {knowledge_base.external_knowledge_base_id}; "
                f"indexed chunks: {len(chunks)}"
            ),
        )

    # 保留可选 claude 参数，兼容旧 readiness 调用链；当前证据运行时不消费它。
    def get_project_readiness(
        self,
        project_id: str,
        claude: ProviderReadiness | None = None,
    ) -> ProviderReadiness:
        return self._get_project_readiness(project_id, claude=claude)

    def _require_project(self, project_id: str):
        project = self.catalog.get_project(project_id)
        if not project:
            raise LookupError("Project not found")
        return project

    def _require_source(self, project_id: str, source_id: str):
        source = self.catalog.get_source(source_id)
        if not source:
            raise LookupError("Source not found")
        if source.project_id != project_id:
            raise ValueError("source_id does not belong to the provided project_id")
        return source

    def ensure_project_knowledge_base(self, project_id: str) -> KnowledgeBaseRecord:
        self.ensure_available()
        project = self._require_project(project_id)
        collection_name = self.vector_store.ensure_collection(project_id)
        return self.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider=EVIDENCE_PROVIDER,
            external_knowledge_base_id=collection_name,
            display_name=f"{project.name} Evidence KB",
            description=project.summary,
            status="ready",
            status_error=None,
        )

    def _persist_chunks(
        self,
        *,
        project_id: str,
        source_id: str,
        knowledge_base_id: str,
        prepared_chunks,
        embedding_status: str,
        index_error: str | None,
        indexed_at: str | None,
    ) -> list[SourceChunkRecord]:
        rows = [
            chunk.to_catalog_row(
                knowledge_base_id=knowledge_base_id,
                embedding_status=embedding_status,
                index_error=index_error,
                indexed_at=indexed_at,
            )
            for chunk in prepared_chunks
        ]
        return self.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=rows,
        )

    def _mark_source_index_failure(
        self,
        *,
        project_id: str,
        source_id: str,
        knowledge_base: KnowledgeBaseRecord,
        message: str,
    ) -> None:
        try:
            self.vector_store.delete_source(project_id, source_id)
        except Exception:
            # 这里不能再伪装成成功，但也不能让清理失败覆盖主失败原因。
            pass

        self.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=[],
        )
        self.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider=EVIDENCE_PROVIDER,
            external_knowledge_base_id=knowledge_base.external_knowledge_base_id,
            display_name=knowledge_base.display_name,
            description=knowledge_base.description,
            status="error",
            status_error=message,
        )

    @staticmethod
    def _is_embedding_dimension_mismatch(exc: ProviderIssue) -> bool:
        message = exc.message.lower()
        return (
            "could not broadcast input array from shape" in message
            or "dimension" in message and "vector" in message
            or "expected dim" in message
            or "vector size" in message
            or (
                "index " in message
                and " out of bounds for axis " in message
                and "qdrant/llamaindex" in message
            )
        )

    def _mark_project_reindex_failure(
        self,
        *,
        project_id: str,
        knowledge_base: KnowledgeBaseRecord,
        message: str,
    ) -> None:
        self.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider=EVIDENCE_PROVIDER,
            external_knowledge_base_id=knowledge_base.external_knowledge_base_id,
            display_name=knowledge_base.display_name,
            description=knowledge_base.description,
            status="error",
            status_error=message,
        )
        for source in self.catalog.list_sources(project_id):
            if source.normalize_status != "parsed":
                continue
            self.catalog.replace_source_chunks(
                project_id=project_id,
                source_id=source.id,
                chunks=[],
            )
            self.catalog.update_source_index_status(
                source_id=source.id,
                index_status="index_failed",
                index_error=message,
            )

    def _rebuild_project_collection(
        self,
        *,
        project_id: str,
        knowledge_base: KnowledgeBaseRecord,
    ) -> None:
        try:
            self.vector_store.delete_project(project_id)
            reset_client = getattr(self.vector_store, "reset_client", None)
            if callable(reset_client):
                reset_client()
        except ProviderIssue:
            raise
        except Exception as exc:
            raise ProviderIssue(
                provider=EVIDENCE_PROVIDER,
                message=f"重建项目 collection 前删除旧 collection 失败：{exc}",
            ) from exc

        collection_name = self.vector_store.ensure_collection(project_id)
        knowledge_base = self.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider=EVIDENCE_PROVIDER,
            external_knowledge_base_id=collection_name,
            display_name=knowledge_base.display_name,
            description=knowledge_base.description,
            status="indexing",
            status_error=None,
        )
        indexed_at = now_iso(self.settings)

        try:
            for source in self.catalog.list_sources(project_id):
                if source.normalize_status != "parsed":
                    continue
                prepared_chunks = prepare_source_chunks(
                    source=source,
                    knowledge_base_id=knowledge_base.id,
                    settings=self.settings,
                )
                self._persist_chunks(
                    project_id=project_id,
                    source_id=source.id,
                    knowledge_base_id=knowledge_base.id,
                    prepared_chunks=prepared_chunks,
                    embedding_status="pending",
                    index_error=None,
                    indexed_at=None,
                )
                if prepared_chunks:
                    self.vector_store.upsert(
                        project_id,
                        [
                            chunk.to_vector_document(source_id=source.id)
                            for chunk in prepared_chunks
                        ],
                    )
                self._persist_chunks(
                    project_id=project_id,
                    source_id=source.id,
                    knowledge_base_id=knowledge_base.id,
                    prepared_chunks=prepared_chunks,
                    embedding_status="indexed",
                    index_error=None,
                    indexed_at=indexed_at,
                )
                self.catalog.update_source_index_status(
                    source_id=source.id,
                    index_status="indexed",
                    index_error=None,
                )
        except ProviderIssue as exc:
            self._mark_project_reindex_failure(
                project_id=project_id,
                knowledge_base=knowledge_base,
                message=exc.message,
            )
            raise
        except Exception as exc:
            issue = ProviderIssue(
                provider=EVIDENCE_PROVIDER,
                message=f"重建项目 collection 时失败：{exc}",
            )
            self._mark_project_reindex_failure(
                project_id=project_id,
                knowledge_base=knowledge_base,
                message=issue.message,
            )
            raise issue from exc

        self.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider=EVIDENCE_PROVIDER,
            external_knowledge_base_id=knowledge_base.external_knowledge_base_id,
            display_name=knowledge_base.display_name,
            description=knowledge_base.description,
            status="ready",
            status_error=None,
        )

    def index_source(
        self,
        project_id: str,
        source_id: str,
    ) -> list[SourceChunkRecord]:
        self.ensure_available()
        source = self._require_source(project_id, source_id)
        knowledge_base = self.ensure_project_knowledge_base(project_id)
        try:
            prepared_chunks = prepare_source_chunks(
                source=source,
                knowledge_base_id=knowledge_base.id,
                settings=self.settings,
            )
        except Exception as exc:
            provider_issue = exc
            if not isinstance(exc, ProviderIssue):
                provider_issue = ProviderIssue(
                    provider=EVIDENCE_PROVIDER,
                    message=f"准备 source 分块时失败：{exc}",
                )
            self._mark_source_index_failure(
                project_id=project_id,
                source_id=source_id,
                knowledge_base=knowledge_base,
                message=provider_issue.message,
            )
            raise provider_issue
        if not prepared_chunks:
            return self.catalog.replace_source_chunks(
                project_id=project_id,
                source_id=source_id,
                chunks=[],
            )

        self._persist_chunks(
            project_id=project_id,
            source_id=source_id,
            knowledge_base_id=knowledge_base.id,
            prepared_chunks=prepared_chunks,
            embedding_status="pending",
            index_error=None,
            indexed_at=None,
        )

        try:
            self.vector_store.delete_source(project_id, source_id)
            self.vector_store.upsert(
                project_id,
                [chunk.to_vector_document(source_id=source_id) for chunk in prepared_chunks],
            )
        except ProviderIssue as exc:
            if self._is_embedding_dimension_mismatch(exc):
                self._rebuild_project_collection(
                    project_id=project_id,
                    knowledge_base=knowledge_base,
                )
                return self.catalog.list_source_chunks(
                    project_id=project_id,
                    source_id=source_id,
                )
            self._persist_chunks(
                project_id=project_id,
                source_id=source_id,
                knowledge_base_id=knowledge_base.id,
                prepared_chunks=prepared_chunks,
                embedding_status="failed",
                index_error=exc.message,
                indexed_at=None,
            )
            self.catalog.upsert_knowledge_base(
                project_id=project_id,
                provider=EVIDENCE_PROVIDER,
                external_knowledge_base_id=knowledge_base.external_knowledge_base_id,
                display_name=knowledge_base.display_name,
                description=knowledge_base.description,
                status="error",
                status_error=exc.message,
            )
            raise

        indexed_at = now_iso(self.settings)
        records = self._persist_chunks(
            project_id=project_id,
            source_id=source_id,
            knowledge_base_id=knowledge_base.id,
            prepared_chunks=prepared_chunks,
            embedding_status="indexed",
            index_error=None,
            indexed_at=indexed_at,
        )
        self.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider=EVIDENCE_PROVIDER,
            external_knowledge_base_id=knowledge_base.external_knowledge_base_id,
            display_name=knowledge_base.display_name,
            description=knowledge_base.description,
            status="ready",
            status_error=None,
        )
        return records

    def delete_source(self, project_id: str, source_id: str) -> None:
        self.ensure_available()
        self.vector_store.delete_source(project_id, source_id)
        source = self.catalog.get_source(source_id)
        if source is None:
            return
        if source.project_id != project_id:
            raise ValueError("source_id does not belong to the provided project_id")
        self.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=[],
        )

    def delete_project(self, project_id: str) -> None:
        self.ensure_available()
        self._require_project(project_id)
        self.vector_store.delete_project(project_id)

    def reindex_source(
        self,
        project_id: str,
        source_id: str,
    ) -> list[SourceChunkRecord]:
        return self.index_source(project_id, source_id)

    @staticmethod
    def _trim_snippet(text: str, *, limit: int = 180) -> str:
        snippet = " ".join(text.split())
        if len(snippet) <= limit:
            return snippet
        return f"{snippet[: limit - 3].rstrip()}..."

    def _dedupe_hits(self, hits: list[VectorQueryHit]) -> list[VectorQueryHit]:
        deduped: list[VectorQueryHit] = []
        seen_chunk_ids: set[str] = set()
        for hit in hits:
            if hit.chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(hit.chunk_id)
            deduped.append(hit)
        return deduped

    def _build_summary(
        self,
        hits: list[VectorQueryHit],
        source_titles: dict[str, str],
    ) -> str:
        if not hits:
            return "当前项目知识库里没有检索到相关证据。"

        lines = []
        for index, hit in enumerate(hits, start=1):
            source_title = source_titles.get(hit.source_id, hit.metadata.get("source_name") or hit.source_id)
            lines.append(f"{index}. {source_title}: {self._trim_snippet(hit.text, limit=120)}")
        return f"已检索到 {len(hits)} 条相关证据。\n" + "\n".join(lines)

    def query(
        self,
        project_id: str,
        question: str,
        *,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        self.ensure_available()
        self._require_project(project_id)
        self.ensure_project_knowledge_base(project_id)

        source_filter = list(selected_source_ids) if selected_source_ids else None
        hits = self.vector_store.query(
            project_id,
            question,
            top_k=self.settings.evidence_top_k,
            source_ids=source_filter,
        )
        sources = self.catalog.list_sources(project_id)
        source_titles = {source.id: source.name for source in sources}
        current_source_ids = set(source_titles)
        filtered_hits = [
            hit for hit in hits if hit.source_id and hit.source_id in current_source_ids
        ]
        deduped_hits = self._dedupe_hits(filtered_hits)
        citations: list[ChatCitation] = []
        for hit in deduped_hits:
            source_title = source_titles.get(
                hit.source_id,
                str(hit.metadata.get("source_name") or hit.source_id),
            )
            citations.append(
                ChatCitation(
                    title=source_title,
                    snippet=self._trim_snippet(hit.text),
                    source_id=hit.source_id or None,
                )
            )

        return EvidenceResult(
            summary=self._build_summary(deduped_hits, source_titles),
            citations=citations,
            sync_status="queried",
        )
