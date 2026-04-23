from __future__ import annotations

import importlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue


EVIDENCE_PROVIDER = "QDRANT_LLAMA_INDEX"
DEFAULT_DISTANCE = "COSINE"


@dataclass(frozen=True, slots=True)
class VectorDocument:
    chunk_id: str
    source_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VectorQueryHit:
    chunk_id: str
    source_id: str
    text: str
    score: float | None
    metadata: dict[str, Any]


class QdrantLlamaIndexVectorStore:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings
        self._client: Any | None = None
        self._embed_model: Any | None = None

    @property
    def qdrant_path(self) -> Path:
        return self.settings.qdrant_path or (self.settings.data_dir / "qdrant")

    def _load_qdrant_client_class(self):
        try:
            module = importlib.import_module("qdrant_client")
        except ModuleNotFoundError as exc:
            raise ProviderIssue(
                provider=EVIDENCE_PROVIDER,
                message=(
                    "当前后端环境没有安装 qdrant-client。"
                    "请先在 backend 虚拟环境里安装 Task 3 所需依赖。"
                ),
            ) from exc
        return module.QdrantClient

    def _load_qdrant_models(self):
        try:
            return importlib.import_module("qdrant_client.models")
        except ModuleNotFoundError as exc:
            raise ProviderIssue(
                provider=EVIDENCE_PROVIDER,
                message=(
                    "当前后端环境缺少 qdrant-client models。"
                    "请先在 backend 虚拟环境里安装 Task 3 所需依赖。"
                ),
            ) from exc

    def _load_fastembed_class(self):
        try:
            importlib.import_module("llama_index.vector_stores.qdrant")
            module = importlib.import_module("llama_index.embeddings.fastembed")
            importlib.import_module("fastembed")
        except ModuleNotFoundError as exc:
            raise ProviderIssue(
                provider=EVIDENCE_PROVIDER,
                message=(
                    "当前后端环境没有安装 LlamaIndex Qdrant/FastEmbed 依赖。"
                    "请先在 backend 虚拟环境里安装 Task 3 所需依赖。"
                ),
            ) from exc
        return module.FastEmbedEmbedding

    def _get_client(self):
        if self._client is not None:
            return self._client

        client_class = self._load_qdrant_client_class()
        if self.settings.qdrant_url:
            self._client = client_class(url=self.settings.qdrant_url)
        else:
            self.qdrant_path.mkdir(parents=True, exist_ok=True)
            self._client = client_class(path=str(self.qdrant_path))
        return self._client

    def _get_embed_model(self):
        if self._embed_model is None:
            embedder_class = self._load_fastembed_class()
            try:
                self._embed_model = embedder_class()
            except ImportError as exc:
                raise ProviderIssue(
                    provider=EVIDENCE_PROVIDER,
                    message=(
                        "当前后端环境没有安装 LlamaIndex Qdrant/FastEmbed 依赖。"
                        "请先在 backend 虚拟环境里安装 Task 3 所需依赖。"
                    ),
                ) from exc
            except Exception as exc:  # pragma: no cover - depends on optional runtime deps
                raise self._wrap_error(exc, "初始化 embedding 模型") from exc
        return self._embed_model

    def _wrap_error(self, exc: Exception, action: str) -> ProviderIssue:
        message = str(exc).strip() or exc.__class__.__name__
        return ProviderIssue(
            provider=EVIDENCE_PROVIDER,
            message=f"Qdrant/LlamaIndex 在{action}时失败：{message}",
        )

    def ensure_available(self) -> Path:
        self.qdrant_path.mkdir(parents=True, exist_ok=True)
        self._load_qdrant_client_class()
        self._load_qdrant_models()
        self._get_embed_model()
        self._get_client()
        return self.qdrant_path

    def collection_name(self, project_id: str) -> str:
        safe_project_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", project_id).strip("_") or "project"
        prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", self.settings.qdrant_collection_prefix).strip("_") or "project"
        return f"{prefix}__{safe_project_id}"

    def _collection_exists(self, collection_name: str) -> bool:
        client = self._get_client()
        if hasattr(client, "collection_exists"):
            return bool(client.collection_exists(collection_name))
        try:
            client.get_collection(collection_name)
        except Exception:
            return False
        return True

    def _embed_text(self, text: str, *, query: bool) -> list[float]:
        embed_model = self._get_embed_model()
        try:
            if query:
                embedding = embed_model.get_query_embedding(text)
            else:
                embedding = embed_model.get_text_embedding(text)
        except Exception as exc:  # pragma: no cover - depends on optional runtime deps
            raise self._wrap_error(exc, "生成向量") from exc
        return list(embedding)

    def ensure_collection(self, project_id: str) -> str:
        collection_name = self.collection_name(project_id)
        if self._collection_exists(collection_name):
            return collection_name

        models = self._load_qdrant_models()
        vector_size = len(self._embed_text("project knowledge base bootstrap", query=False))
        try:
            self._get_client().create_collection(
                collection_name=collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=getattr(models.Distance, DEFAULT_DISTANCE),
                ),
            )
        except Exception as exc:  # pragma: no cover - depends on optional runtime deps
            raise self._wrap_error(exc, "创建 collection") from exc
        return collection_name

    def upsert(self, project_id: str, documents: list[VectorDocument]) -> None:
        if not documents:
            return

        collection_name = self.ensure_collection(project_id)
        models = self._load_qdrant_models()
        try:
            points = [
                models.PointStruct(
                    id=document.chunk_id,
                    vector=self._embed_text(document.text, query=False),
                    payload={
                        "chunk_id": document.chunk_id,
                        "source_id": document.source_id,
                        "text": document.text,
                        **document.metadata,
                    },
                )
                for document in documents
            ]
            self._get_client().upsert(
                collection_name=collection_name,
                points=points,
                wait=True,
            )
        except Exception as exc:  # pragma: no cover - depends on optional runtime deps
            raise self._wrap_error(exc, "写入向量") from exc

    def delete_source(self, project_id: str, source_id: str) -> None:
        collection_name = self.collection_name(project_id)
        if not self._collection_exists(collection_name):
            return

        models = self._load_qdrant_models()
        try:
            self._get_client().delete(
                collection_name=collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key="source_id",
                                match=models.MatchValue(value=source_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception as exc:  # pragma: no cover - depends on optional runtime deps
            raise self._wrap_error(exc, "删除 source 向量") from exc

    def _build_source_filter(self, source_ids: list[str] | None):
        if not source_ids:
            return None

        models = self._load_qdrant_models()
        if len(source_ids) == 1:
            return models.Filter(
                must=[
                    models.FieldCondition(
                        key="source_id",
                        match=models.MatchValue(value=source_ids[0]),
                    )
                ]
            )

        return models.Filter(
            should=[
                models.FieldCondition(
                    key="source_id",
                    match=models.MatchValue(value=source_id),
                )
                for source_id in source_ids
            ]
        )

    def query(
        self,
        project_id: str,
        question: str,
        *,
        top_k: int,
        source_ids: list[str] | None = None,
    ) -> list[VectorQueryHit]:
        collection_name = self.collection_name(project_id)
        if not self._collection_exists(collection_name):
            return []

        try:
            response = self._get_client().query_points(
                collection_name=collection_name,
                query=self._embed_text(question, query=True),
                query_filter=self._build_source_filter(source_ids),
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        except Exception as exc:  # pragma: no cover - depends on optional runtime deps
            raise self._wrap_error(exc, "检索证据") from exc

        points = getattr(response, "points", response)
        hits: list[VectorQueryHit] = []
        for point in points:
            payload = dict(getattr(point, "payload", {}) or {})
            hits.append(
                VectorQueryHit(
                    chunk_id=str(payload.get("chunk_id") or getattr(point, "id")),
                    source_id=str(payload.get("source_id") or ""),
                    text=str(payload.get("text") or ""),
                    score=getattr(point, "score", None),
                    metadata=payload,
                )
            )
        return hits
