from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from docx import Document
from openpyxl import load_workbook
from pypdf import PdfReader

from ..config import AppSettings, DEFAULT_SETTINGS


@dataclass(slots=True)
class NormalizedSource:
    source_kind: str
    parse_status: str
    parse_summary: str
    normalized_path: str | None = None
    notebook_import_mode: str | None = None


class SourceIngestionService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def project_source_dir(self, project_id: str) -> Path:
        path = self.settings.projects_dir / project_id / "sources"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ingest_text(self, project_id: str, name: str, text_content: str) -> tuple[str | None, NormalizedSource]:
        source_dir = self.project_source_dir(project_id)
        raw_path = source_dir / f"{name}.txt"
        raw_path.write_text(text_content, encoding="utf-8")
        summary = text_content.strip().replace("\n", " ")[:240]
        return str(raw_path), NormalizedSource(
            source_kind="text",
            parse_status="parsed",
            parse_summary=summary or f"{name} 已入库。",
            normalized_path=str(raw_path),
            notebook_import_mode="direct_text",
        )

    def ingest_url(self, project_id: str, name: str, source_url: str) -> tuple[str | None, NormalizedSource]:
        source_dir = self.project_source_dir(project_id)
        raw_path = source_dir / f"{name}.url.txt"
        raw_path.write_text(source_url, encoding="utf-8")
        parsed = urlparse(source_url)
        summary = f"URL source: {parsed.netloc}{parsed.path}"
        return str(raw_path), NormalizedSource(
            source_kind="url",
            parse_status="parsed",
            parse_summary=summary,
            normalized_path=None,
            notebook_import_mode="direct_url",
        )

    def ingest_file(self, project_id: str, filename: str, file_bytes: bytes) -> tuple[str, NormalizedSource]:
        source_dir = self.project_source_dir(project_id)
        raw_path = source_dir / filename
        raw_path.write_bytes(file_bytes)

        suffix = raw_path.suffix.lower()
        source_kind = suffix.lstrip(".") or "file"
        normalized_path = None
        summary = f"{filename} 已入库，等待解析。"
        import_mode = "normalized_text"

        try:
            if suffix in {".md", ".txt"}:
                text = raw_path.read_text(encoding="utf-8", errors="ignore")
                normalized_path = raw_path
                summary = text.strip().replace("\n", " ")[:240] or summary
                import_mode = "direct_text"
            elif suffix == ".pdf":
                text = "\n".join(page.extract_text() or "" for page in PdfReader(str(raw_path)).pages)
                normalized_path = source_dir / f"{raw_path.stem}.normalized.md"
                normalized_path.write_text(text, encoding="utf-8")
                summary = text.strip().replace("\n", " ")[:240] or "PDF 已解析为文本。"
            elif suffix == ".docx":
                document = Document(str(raw_path))
                text = "\n".join(paragraph.text for paragraph in document.paragraphs)
                normalized_path = source_dir / f"{raw_path.stem}.normalized.md"
                normalized_path.write_text(text, encoding="utf-8")
                summary = text.strip().replace("\n", " ")[:240] or "DOCX 已解析为文本。"
            elif suffix == ".xlsx":
                workbook = load_workbook(str(raw_path), read_only=True, data_only=True)
                lines: list[str] = []
                for sheet in workbook.worksheets:
                    lines.append(f"# Sheet: {sheet.title}")
                    rows = list(sheet.iter_rows(values_only=True, max_row=6))
                    if rows:
                        header = [str(cell or "") for cell in rows[0]]
                        lines.append("表头: " + " | ".join(header))
                    for sample_row in rows[1:4]:
                        lines.append("样例: " + " | ".join(str(cell or "") for cell in sample_row))
                    lines.append(f"行数估计: {sheet.max_row}, 列数估计: {sheet.max_column}")
                text = "\n".join(lines)
                normalized_path = source_dir / f"{raw_path.stem}.normalized.md"
                normalized_path.write_text(text, encoding="utf-8")
                summary = text[:240] or "XLSX 已转成摘要文本。"
            elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
                summary = f"{filename} 已入库。图片类 source 需要后续接视觉描述链路。"
            elif suffix in {".mp3", ".wav", ".m4a"}:
                summary = f"{filename} 已入库。音频类 source 需要后续接转写链路。"
            else:
                summary = f"{filename} 已入库，但当前类型仅保留原始文件记录。"
        except Exception as exc:
            return str(raw_path), NormalizedSource(
                source_kind=source_kind,
                parse_status="failed",
                parse_summary=f"{filename} 解析失败：{exc}",
                normalized_path=None,
                notebook_import_mode=None,
            )

        return str(raw_path), NormalizedSource(
            source_kind=source_kind,
            parse_status="parsed",
            parse_summary=summary,
            normalized_path=str(normalized_path) if normalized_path else None,
            notebook_import_mode=import_mode,
        )
