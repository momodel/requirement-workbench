from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue, SourceRecord
from .project_catalog import source_chunk_content_hash
from .vector_store import VectorDocument


MAX_CHUNK_CHARS = 500
DEFAULT_CHUNK_OVERLAP = 120
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;\n])")
TEXT_LIKE_SOURCE_KINDS = {
    "text",
    "markdown",
    "md",
    "txt",
    "html",
    "csv",
    "tsv",
    "json",
    "xml",
}
TEXT_LIKE_UPLOAD_KINDS = {"text", "seed"}
TEXT_LIKE_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".yaml",
    ".yml",
    ".log",
}


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


def _normalized_not_indexable_issue(source: SourceRecord) -> ProviderIssue:
    return ProviderIssue(
        provider="QDRANT_LLAMA_INDEX",
        message=(
            f"source {source.name} 尚未完成可索引文本标准化。"
            f"当前 source_kind={source.source_kind} 的原始资料不能直接按 UTF-8 文本索引，"
            "请先生成 normalized text 后再重试。"
        ),
    )


def _read_text_file(path: Path, *, source: SourceRecord, path_label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ProviderIssue(
            provider="QDRANT_LLAMA_INDEX",
            message=(
                f"source {source.name} 的{path_label}不是有效 UTF-8 文本。"
                "请先完成文本标准化后再索引。"
            ),
        ) from exc


def _is_safe_raw_text_fallback(source: SourceRecord) -> bool:
    source_kind = source.source_kind.strip().lower()
    upload_kind = source.upload_kind.strip().lower()
    if source_kind == "url" or upload_kind == "url":
        return False

    if source_kind in TEXT_LIKE_SOURCE_KINDS or upload_kind in TEXT_LIKE_UPLOAD_KINDS:
        return True

    candidate_path = source.storage_path or source.normalized_path or source.name
    suffix = Path(candidate_path).suffix.lower()
    return suffix in TEXT_LIKE_SUFFIXES


def load_source_text(source: SourceRecord) -> str:
    normalized_path = Path(source.normalized_path) if source.normalized_path else None
    raw_fallback_allowed = _is_safe_raw_text_fallback(source)
    if normalized_path and normalized_path.exists():
        text = _read_text_file(
            normalized_path,
            source=source,
            path_label="normalized_path",
        )
        if text.strip():
            return text
        if not raw_fallback_allowed:
            raise _normalized_not_indexable_issue(source)

    storage_path = Path(source.storage_path) if source.storage_path else None
    if storage_path and storage_path.exists() and raw_fallback_allowed:
        text = _read_text_file(
            storage_path,
            source=source,
            path_label="storage_path",
        )
        if text.strip():
            return text

    if not raw_fallback_allowed:
        raise _normalized_not_indexable_issue(source)

    if source.normalize_summary and source.normalize_summary.strip():
        return source.normalize_summary

    raise ProviderIssue(
        provider="QDRANT_LLAMA_INDEX",
        message=f"source {source.name} 缺少可索引文本。",
    )


def _normalize_whitespace(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _split_paragraph(paragraph: str, chunk_size: int) -> list[str]:
    if len(paragraph) <= chunk_size:
        return [paragraph]

    # 先按中英文句末标点切句子，保留分隔符；再把短句重新拼到接近 chunk_size。
    sentences = [s for s in _SENTENCE_BOUNDARY.split(paragraph) if s.strip()]
    if not sentences:
        return [paragraph]

    segments: list[str] = []
    buffer = ""
    for sentence in sentences:
        if len(sentence) > chunk_size:
            if buffer:
                segments.append(buffer.strip())
                buffer = ""
            for start in range(0, len(sentence), chunk_size):
                segments.append(sentence[start : start + chunk_size].strip())
            continue
        if len(buffer) + len(sentence) > chunk_size and buffer:
            segments.append(buffer.strip())
            buffer = sentence
        else:
            buffer += sentence
    if buffer.strip():
        segments.append(buffer.strip())
    return [segment for segment in segments if segment]


def _apply_overlap(chunks: list[str], chunk_overlap: int) -> list[str]:
    if chunk_overlap <= 0 or len(chunks) <= 1:
        return chunks
    out: list[str] = [chunks[0]]
    for prev, curr in zip(chunks, chunks[1:]):
        tail = prev[-chunk_overlap:].lstrip()
        out.append(f"{tail}\n\n{curr}" if tail else curr)
    return out


def _chunk_text(
    text: str,
    *,
    chunk_size: int = MAX_CHUNK_CHARS,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    paragraphs = [part.strip() for part in _normalize_whitespace(text).split("\n\n") if part.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for paragraph in paragraphs:
        for segment in _split_paragraph(paragraph, chunk_size):
            projected = current_length + len(segment) + (2 if current else 0)
            if current and projected > chunk_size:
                chunks.append("\n\n".join(current))
                current = [segment]
                current_length = len(segment)
                continue

            current.append(segment)
            current_length = projected if current_length else len(segment)

    if current:
        chunks.append("\n\n".join(current))
    return _apply_overlap(chunks, chunk_overlap)


def _source_locator(source: SourceRecord, chunk_order: int) -> dict[str, object]:
    locator: dict[str, object] = {
        "chunk_order": chunk_order,
        "source_name": source.name,
        "source_kind": source.source_kind,
    }
    if source.source_kind in {"image", "audio"}:
        locator["locator_kind"] = "source_level"
    return locator


def prepare_source_chunks(
    *,
    source: SourceRecord,
    knowledge_base_id: str,
    settings: AppSettings = DEFAULT_SETTINGS,
) -> list[PreparedSourceChunk]:
    text = load_source_text(source)
    chunks = _chunk_text(
        text,
        chunk_size=getattr(settings, "chunk_size", MAX_CHUNK_CHARS),
        chunk_overlap=getattr(settings, "chunk_overlap", DEFAULT_CHUNK_OVERLAP),
    )
    prepared: list[PreparedSourceChunk] = []
    for chunk_order, content in enumerate(chunks):
        locator_json = json.dumps(_source_locator(source, chunk_order), ensure_ascii=False)
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
                    "source_kind": source.source_kind,
                    "chunk_order": chunk_order,
                    "locator_json": locator_json,
                },
            )
        )
    return prepared
