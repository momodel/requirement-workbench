from __future__ import annotations

from importlib import import_module
from pathlib import Path

from ..models import ProviderIssue


DOCLING_PROVIDER = "DOCLING"


class DoclingNormalizer:
    DOCUMENT_SUFFIXES = {
        ".pdf",
        ".docx",
        ".pptx",
        ".html",
        ".htm",
    }
    IMAGE_SUFFIXES = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".tif",
        ".tiff",
    }
    AUDIO_SUFFIXES = {
        ".mp3",
        ".wav",
        ".m4a",
        ".aac",
        ".flac",
        ".ogg",
    }
    SUPPORTED_SUFFIXES = DOCUMENT_SUFFIXES | IMAGE_SUFFIXES

    def supports(self, source_path: Path) -> bool:
        return source_path.suffix.lower() in self.SUPPORTED_SUFFIXES

    def normalize_to_markdown(self, source_path: Path) -> str:
        suffix = source_path.suffix.lower()
        if suffix in self.AUDIO_SUFFIXES:
            raise ProviderIssue(
                provider=DOCLING_PROVIDER,
                message="音频标准化不再走 Docling；请使用 AudioTranscriptionService。",
            )
        converter_class = self._load_document_converter(suffix=suffix)
        converter = converter_class()

        try:
            result = converter.convert(str(source_path))
        except Exception as exc:  # pragma: no cover - exercised via service tests with fakes
            raise self._conversion_issue(source_path, exc) from exc

        document = getattr(result, "document", None)
        export_to_markdown = getattr(document, "export_to_markdown", None)
        if export_to_markdown is None:
            raise ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=f"Docling 返回了不完整结果，{source_path.name} 缺少 Markdown 导出能力。",
            )

        markdown = export_to_markdown()
        if not isinstance(markdown, str) or not markdown.strip():
            raise ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=f"Docling 没有从 {source_path.name} 提取到可索引文本。",
            )
        return markdown

    def _load_document_converter(self, *, suffix: str):
        try:
            module = import_module("docling.document_converter")
        except ModuleNotFoundError as exc:
            raise self._missing_runtime_issue(suffix=suffix) from exc

        converter_class = getattr(module, "DocumentConverter", None)
        if converter_class is None:
            raise ProviderIssue(
                provider=DOCLING_PROVIDER,
                message="当前环境里的 docling 缺少 DocumentConverter，无法执行标准化。",
            )
        return converter_class

    def _missing_runtime_issue(self, *, suffix: str) -> ProviderIssue:
        if suffix in self.AUDIO_SUFFIXES:
            return ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=(
                    "当前环境还没有可用的音频转文本链路。"
                    "请先在项目内环境安装 Docling/ASR 依赖。"
                ),
            )
        if suffix in self.IMAGE_SUFFIXES:
            return ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=(
                    "当前环境还没有可用的图片转文本链路。"
                    "请先在项目内环境安装 Docling/OCR 依赖。"
                ),
            )
        return ProviderIssue(
            provider=DOCLING_PROVIDER,
            message=(
                "当前环境未安装 Docling，无法把文档标准化为文本。"
                "请先在项目内环境安装 backend/requirements.txt。"
            ),
        )

    def _conversion_issue(self, source_path: Path, exc: Exception) -> ProviderIssue:
        suffix = source_path.suffix.lower()
        if suffix in self.AUDIO_SUFFIXES:
            return ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=(
                    f"{source_path.name} 当前还没有完成可用的音频转文本标准化：{exc}"
                ),
            )
        if suffix in self.IMAGE_SUFFIXES:
            return ProviderIssue(
                provider=DOCLING_PROVIDER,
                message=(
                    f"{source_path.name} 当前还没有完成可用的图片转文本标准化：{exc}"
                ),
            )
        return ProviderIssue(
            provider=DOCLING_PROVIDER,
            message=f"Docling 解析 {source_path.name} 失败：{exc}",
        )
