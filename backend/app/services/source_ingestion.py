from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ..config import PROJECTS_DIR
from ..db import get_connection
from ..models import SourceRecord


TEXT_SOURCE_KINDS = {"text", "txt", "markdown", "md", "pdf", "docx", "url"}
TABULAR_SOURCE_KINDS = {"xlsx", "csv", "tsv"}
IMAGE_SOURCE_KINDS = {"image", "png", "jpg", "jpeg", "webp"}
AUDIO_SOURCE_KINDS = {"audio", "mp3", "wav", "m4a"}


@dataclass
class NormalizedSource:
    parse_status: str
    parse_summary: str
    normalized_content: str


def _source_dir(project_id: str, source_id: str) -> Path:
    path = PROJECTS_DIR / project_id / "sources" / source_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _guess_source_kind(name: str, source_kind: str | None) -> str:
    if source_kind:
        return source_kind.lower()

    suffix = Path(name).suffix.lower().lstrip(".")
    return suffix or "text"


def _decode_preview_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="ignore")


def _summarize_text_like(name: str, text: str, source_kind: str) -> NormalizedSource:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    preview = " ".join(lines[:3])[:180]
    summary = preview or f"{name} 已完成 {source_kind} 标准化。"
    return NormalizedSource(
        parse_status="parsed",
        parse_summary=summary,
        normalized_content=f"# {name}\n\n{text.strip()}\n",
    )


def _summarize_tabular(name: str, text: str) -> NormalizedSource:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header = lines[1] if len(lines) > 1 and lines[0].startswith("sheet:") else lines[0] if lines else ""
    sample = lines[2] if len(lines) > 2 else lines[1] if len(lines) > 1 else ""
    summary = f"{name} 已抽取表头 {header or '未知'}，样例 {sample or '暂无'}。"
    if lines and lines[0].startswith("sheet:"):
        summary = f"{name} 已抽取 {lines[0]}，表头 {header or '未知'}。"

    return NormalizedSource(
        parse_status="parsed",
        parse_summary=summary,
        normalized_content="\n".join(
            [
                f"# {name}",
                "",
                "## 表格摘要",
                f"- 行数预览：{max(len(lines) - 1, 0)}",
                f"- 表头：{header or '未知'}",
                f"- 样例：{sample or '暂无'}",
                "",
                "## 原始片段",
                text.strip(),
                "",
            ]
        ),
    )


def _summarize_binary(name: str, source_kind: str, mime_type: str | None, size: int) -> NormalizedSource:
    normalized_content = "\n".join(
        [
            f"# {name}",
            "",
            "## 标准化说明",
            f"- 文件类型：{source_kind}",
            f"- MIME：{mime_type or 'unknown'}",
            f"- 文件大小：{size} bytes",
            "",
            "当前环境未接入真实 OCR / ASR / 二进制解析器，先保留元信息供 NotebookLM 工作流引用。",
            "",
        ]
    )
    return NormalizedSource(
        parse_status="parsed",
        parse_summary=f"{name} 已登记为 {source_kind} 文件，并生成可检索的元信息摘要。",
        normalized_content=normalized_content,
    )


def normalize_source(
    *,
    name: str,
    source_kind: str,
    text: str | None = None,
    content: bytes | None = None,
    mime_type: str | None = None,
) -> NormalizedSource:
    source_kind = _guess_source_kind(name, source_kind)

    if source_kind in TEXT_SOURCE_KINDS:
        return _summarize_text_like(name, text or _decode_preview_text(content or b""), source_kind)

    if source_kind in TABULAR_SOURCE_KINDS:
        return _summarize_tabular(name, text or _decode_preview_text(content or b""))

    if source_kind in IMAGE_SOURCE_KINDS or source_kind in AUDIO_SOURCE_KINDS:
        return _summarize_binary(name, source_kind, mime_type, len(content or b""))

    return _summarize_binary(name, source_kind, mime_type, len(content or b""))


def _insert_source(
    *,
    source_id: str,
    project_id: str,
    name: str,
    source_kind: str,
    upload_kind: str,
    storage_path: str,
    normalized_path: str,
    parse_status: str,
    parse_summary: str,
) -> SourceRecord:
    created_at = datetime.now().isoformat()
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO sources (
              id, project_id, name, source_kind, upload_kind, storage_path, normalized_path,
              notebook_import_mode, parse_status, sync_status, parse_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                project_id,
                name,
                source_kind,
                upload_kind,
                storage_path,
                normalized_path,
                "normalized-text",
                parse_status,
                "pending",
                parse_summary,
                created_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return SourceRecord(
        id=source_id,
        project_id=project_id,
        name=name,
        source_kind=source_kind,
        upload_kind=upload_kind,
        storage_path=storage_path,
        normalized_path=normalized_path,
        parse_status=parse_status,
        parse_summary=parse_summary,
        sync_status="pending",
    )


def _write_text_source(
    *,
    project_id: str,
    name: str,
    source_kind: str,
    upload_kind: str,
    raw_text: str,
    normalized: NormalizedSource,
) -> SourceRecord:
    source_id = f"src-{uuid4().hex[:8]}"
    source_dir = _source_dir(project_id, source_id)
    raw_path = source_dir / name
    normalized_path = source_dir / "normalized.md"

    raw_path.write_text(raw_text, encoding="utf-8")
    normalized_path.write_text(normalized.normalized_content, encoding="utf-8")

    return _insert_source(
        source_id=source_id,
        project_id=project_id,
        name=name,
        source_kind=source_kind,
        upload_kind=upload_kind,
        storage_path=str(raw_path),
        normalized_path=str(normalized_path),
        parse_status=normalized.parse_status,
        parse_summary=normalized.parse_summary,
    )


def ingest_text_source(project_id: str, name: str, text: str) -> SourceRecord:
    normalized = normalize_source(name=name, source_kind="text", text=text)
    return _write_text_source(
        project_id=project_id,
        name=name,
        source_kind="text",
        upload_kind="text",
        raw_text=text,
        normalized=normalized,
    )


def ingest_url_source(project_id: str, name: str, url: str) -> SourceRecord:
    normalized = normalize_source(
        name=name,
        source_kind="url",
        text=f"来源链接：{url}",
    )
    return _write_text_source(
        project_id=project_id,
        name=name,
        source_kind="url",
        upload_kind="url",
        raw_text=url,
        normalized=normalized,
    )


def ingest_file_source(
    *,
    project_id: str,
    name: str,
    content: bytes,
    source_kind: str | None = None,
    mime_type: str | None = None,
) -> SourceRecord:
    normalized_kind = _guess_source_kind(name, source_kind)
    normalized = normalize_source(
        name=name,
        source_kind=normalized_kind,
        content=content,
        mime_type=mime_type,
    )

    source_id = f"src-{uuid4().hex[:8]}"
    source_dir = _source_dir(project_id, source_id)
    raw_path = source_dir / name
    normalized_path = source_dir / "normalized.md"

    raw_path.write_bytes(content)
    normalized_path.write_text(normalized.normalized_content, encoding="utf-8")

    return _insert_source(
        source_id=source_id,
        project_id=project_id,
        name=name,
        source_kind=normalized_kind,
        upload_kind="file",
        storage_path=str(raw_path),
        normalized_path=str(normalized_path),
        parse_status=normalized.parse_status,
        parse_summary=normalized.parse_summary,
    )
