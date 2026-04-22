from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..models import ProviderIssue, SourceRecord
from .project_catalog import source_chunk_content_hash
from .vector_store import VectorDocument


MAX_CHUNK_CHARS = 800


@dataclass(frozen=True, slots=True)
class PreparedSourceChunk:
    id: str
    chunk_order: int
    content: str
    locator_json: str
    content_hash: str
    metadata: dict[str, object]

    def to_catalog_row(self, *, knowledge_base_id: str, embedding_status: str, index_error: str | None, indexed_at: str | None) -> dict[str, object]:
        return {
            "id": self.id,
            "knowledge_base_id": knowledge_base_id,
            "chunk_order": self.chunk_order,
            "modality": "text",
            "content": self.content,
            "locator_json": self.locator_json,
            "content_hash": self.content_hash,
            "embedding_status": embedding_status,
            "index_error": index_error,
            "indexed_at": indexed_at,
        }

    def to_vector_document(self, *, source_id: str) -> VectorDocument:
        return VectorDocument(
            chunk_id=self.id,
            source_id=source_id,
            text=self.content,
            metadata=dict(self.metadata),
        )


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def load_source_text(source: SourceRecord) -> str:
    normalized_path = Path(source.normalized_path) if source.normalized_path else None
    if normalized_path and normalized_path.exists():
        text = _read_text_file(normalized_path)
        if text.strip():
            return text

    storage_path = Path(source.storage_path) if source.storage_path else None
    if storage_path and storage_path.exists():
        text = _read_text_file(storage_path)
        if text.strip():
            return text

    if source.parse_summary and source.parse_summary.strip():
        return source.parse_summary

    raise ProviderIssue(
        provider="QDRANT_LLAMA_INDEX",
        message=f"source {source.name} 缺少可索引文本。",
    )


def _normalize_whitespace(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _split_paragraph(paragraph: str) -> list[str]:
    if len(paragraph) <= MAX_CHUNK_CHARS:
        return [paragraph]

    segments: list[str] = []
    start = 0
    step = MAX_CHUNK_CHARS
    while start < len(paragraph):
        end = min(len(paragraph), start + step)
        segments.append(paragraph[start:end].strip())
        start = end
    return [segment for segment in segments if segment]


def _chunk_text(text: str) -> list[str]:
    paragraphs = [part.strip() for part in _normalize_whitespace(text).split("\n\n") if part.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        for segment in _split_paragraph(paragraph):
            projected = current_length + len(segment) + (2 if current else 0)
            if current and projected > MAX_CHUNK_CHARS:
                chunks.append("\n\n".join(current))
                current = [segment]
                current_length = len(segment)
                continue

            current.append(segment)
            current_length = projected if current_length else len(segment)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def prepare_source_chunks(
    *,
    source: SourceRecord,
    knowledge_base_id: str,
) -> list[PreparedSourceChunk]:
    text = load_source_text(source)
    chunks = _chunk_text(text)
    prepared: list[PreparedSourceChunk] = []
    for chunk_order, content in enumerate(chunks):
        locator_json = json.dumps(
            {
                "chunk_order": chunk_order,
                "source_name": source.name,
            },
            ensure_ascii=False,
        )
        content_hash = source_chunk_content_hash(content, locator_json)
        prepared.append(
            PreparedSourceChunk(
                id=f"chunk-{source.id}-{chunk_order}-{content_hash[:10]}",
                chunk_order=chunk_order,
                content=content,
                locator_json=locator_json,
                content_hash=content_hash,
                metadata={
                    "knowledge_base_id": knowledge_base_id,
                    "source_id": source.id,
                    "source_name": source.name,
                    "chunk_order": chunk_order,
                    "locator_json": locator_json,
                },
            )
        )
    return prepared
