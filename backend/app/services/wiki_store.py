from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    ProjectSummary,
    WikiPage,
    WikiPageMeta,
)


WIKI_DIR_NAME = "wiki"
PAGES_DIR_NAME = "pages"
INDEX_FILE_NAME = "index.md"
LOG_FILE_NAME = "log.md"
HEALTH_FILE_NAME = ".health"
META_FILE_NAME = ".meta.json"

FRONT_MATTER_FENCE = "---"
FRONT_MATTER_PATTERN = re.compile(
    r"^---\s*\n(?P<front>.*?)\n---\s*\n?(?P<body>.*)$",
    re.DOTALL,
)

ALLOWED_KINDS = {
    "overview",
    "source-intake",
    "glossary",
    "rules-and-conflicts",
    "open-questions",
    "entity",
    "term",
    "rule",
    "conflict",
    "open_question",
    "log",
}

SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]*$")


SKELETON_PAGES = (
    {
        "slug": "overview",
        "title": "Project Overview",
        "kind": "overview",
        "body_template": (
            "# Project Overview\n\n"
            "项目: {project_name}\n\n"
            "场景: {project_scenario}\n\n"
            "## 当前理解\n\n"
            "_骨架页，待维护者根据 source 内容写入。_\n"
        ),
    },
    {
        "slug": "source-intake",
        "title": "Source Intake",
        "kind": "source-intake",
        "body_template": (
            "# Source Intake\n\n"
            "项目: {project_name}\n\n"
            "_骨架页，待维护者随 source 入库填入合成摘要。_\n"
        ),
    },
    {
        "slug": "glossary",
        "title": "Glossary",
        "kind": "glossary",
        "body_template": (
            "# Glossary\n\n"
            "项目: {project_name}\n\n"
            "_骨架页。术语条目要带 `[src: <source_id>]` 内联引用。_\n"
        ),
    },
    {
        "slug": "rules-and-conflicts",
        "title": "Rules And Conflicts",
        "kind": "rules-and-conflicts",
        "body_template": (
            "# Rules And Conflicts\n\n"
            "项目: {project_name}\n\n"
            "## 规则\n\n_骨架页。_\n\n"
            "## 冲突\n\n_骨架页。_\n"
        ),
    },
    {
        "slug": "open-questions",
        "title": "Open Questions",
        "kind": "open-questions",
        "body_template": (
            "# Open Questions\n\n"
            "项目: {project_name}\n\n"
            "_骨架页。每条 open question 都要标注观察到该问题的 source_id。_\n"
        ),
    },
)


class WikiStoreError(ValueError):
    """Raised when a wiki page fails structural validation."""


class WikiStore:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    # ----- paths -----

    def project_wiki_dir(self, project_id: str) -> Path:
        return self.settings.projects_dir / project_id / WIKI_DIR_NAME

    def pages_dir(self, project_id: str) -> Path:
        return self.project_wiki_dir(project_id) / PAGES_DIR_NAME

    def page_path(self, project_id: str, slug: str) -> Path:
        validate_slug(slug)
        return self.pages_dir(project_id) / f"{slug}.md"

    def index_path(self, project_id: str) -> Path:
        return self.project_wiki_dir(project_id) / INDEX_FILE_NAME

    def log_path(self, project_id: str) -> Path:
        return self.project_wiki_dir(project_id) / LOG_FILE_NAME

    def health_path(self, project_id: str) -> Path:
        return self.project_wiki_dir(project_id) / HEALTH_FILE_NAME

    def meta_path(self, project_id: str) -> Path:
        return self.project_wiki_dir(project_id) / META_FILE_NAME

    # ----- skeleton -----

    def ensure_skeleton(self, project: ProjectSummary) -> bool:
        """Create wiki dirs and seed skeleton pages if missing.

        Returns True if anything new was created. Idempotent.
        """
        wiki_dir = self.project_wiki_dir(project.id)
        wiki_dir.mkdir(parents=True, exist_ok=True)
        self.pages_dir(project.id).mkdir(parents=True, exist_ok=True)

        created = False
        index_path = self.index_path(project.id)
        if not index_path.exists():
            self._atomic_write_text(index_path, _render_initial_index())
            created = True

        log_path = self.log_path(project.id)
        if not log_path.exists():
            self._atomic_write_text(log_path, _render_initial_log())
            created = True

        timestamp = _now_iso(self.settings)
        for spec in SKELETON_PAGES:
            page_path = self.page_path(project.id, spec["slug"])
            if page_path.exists():
                continue
            page = WikiPage(
                slug=spec["slug"],
                title=spec["title"],
                kind=spec["kind"],
                source_ids=[],
                last_maintained_at=timestamp,
                last_maintained_by="skeleton",
                body=spec["body_template"].format(
                    project_name=project.name,
                    project_scenario=project.scenario_type,
                ),
            )
            self._write_page_unchecked(project.id, page)
            created = True

        return created

    # ----- read -----

    def list_pages(self, project_id: str) -> list[WikiPageMeta]:
        pages_dir = self.pages_dir(project_id)
        if not pages_dir.exists():
            return []
        results: list[WikiPageMeta] = []
        for entry in sorted(pages_dir.iterdir()):
            if entry.is_file() and entry.suffix == ".md":
                page = self._read_page_at(entry)
                results.append(_meta_from_page(page))
        return results

    def read_page(self, project_id: str, slug: str) -> WikiPage:
        path = self.page_path(project_id, slug)
        if not path.exists():
            raise FileNotFoundError(f"Wiki page not found: {slug}")
        return self._read_page_at(path)

    def read_log(self, project_id: str) -> str:
        path = self.log_path(project_id)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    # ----- write -----

    def write_page(self, project_id: str, page: WikiPage) -> None:
        validate_page(page)
        self.pages_dir(project_id).mkdir(parents=True, exist_ok=True)
        self._write_page_unchecked(project_id, page)

    def append_log(
        self,
        project_id: str,
        *,
        operation: str,
        summary: str,
        source_ids: list[str] | None = None,
        pages_changed: list[str] | None = None,
    ) -> None:
        path = self.log_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = _now_iso(self.settings)
        lines = [f"\n## [{timestamp}] {operation}", f"- {summary}"]
        if pages_changed:
            lines.append(f"- pages_changed: {', '.join(pages_changed)}")
        if source_ids:
            lines.append(f"- source_ids: {', '.join(source_ids)}")
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")

    def write_health(self, project_id: str, marker: str) -> Path:
        path = self.health_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_text(path, marker)
        return path

    def read_health(self, project_id: str) -> str | None:
        path = self.health_path(project_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    # ----- internals -----

    def _write_page_unchecked(self, project_id: str, page: WikiPage) -> None:
        text = serialize_page(page)
        path = self.page_path(project_id, page.slug)
        self._atomic_write_text(path, text)

    @staticmethod
    def _atomic_write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, path)

    @staticmethod
    def _read_page_at(path: Path) -> WikiPage:
        text = path.read_text(encoding="utf-8")
        slug = path.stem
        return parse_page(text, slug=slug)


# ---------- pure helpers ----------


def validate_slug(slug: str) -> None:
    if not slug:
        raise WikiStoreError("slug 不能为空")
    if not SLUG_PATTERN.match(slug):
        raise WikiStoreError(
            f"slug `{slug}` 不合法，只允许小写字母、数字和连字符（首字符不能是连字符）"
        )


def validate_page(page: WikiPage) -> None:
    validate_slug(page.slug)
    if page.kind not in ALLOWED_KINDS:
        raise WikiStoreError(f"page.kind `{page.kind}` 不在允许列表里")
    expanded_kinds = {"entity", "term", "rule", "conflict", "open_question"}
    if page.kind in expanded_kinds and not page.source_ids:
        raise WikiStoreError(
            f"kind={page.kind} 的展开页 `{page.slug}` 必须至少带 1 条 source_id"
        )
    for source_id in page.source_ids:
        if not isinstance(source_id, str) or not source_id.strip():
            raise WikiStoreError("source_ids 中存在空值")


def serialize_page(page: WikiPage) -> str:
    front = {
        "title": page.title,
        "kind": page.kind,
        "source_ids": list(page.source_ids),
        "last_maintained_at": page.last_maintained_at,
        "last_maintained_by": page.last_maintained_by,
    }
    front_text = json.dumps(front, ensure_ascii=False, indent=2)
    body = page.body if page.body.endswith("\n") else page.body + "\n"
    return f"{FRONT_MATTER_FENCE}\n{front_text}\n{FRONT_MATTER_FENCE}\n\n{body}"


def parse_page(text: str, *, slug: str) -> WikiPage:
    match = FRONT_MATTER_PATTERN.match(text)
    if not match:
        raise WikiStoreError(f"page `{slug}` 缺少 front-matter")
    front_raw = match.group("front").strip()
    body = match.group("body").lstrip("\n")
    try:
        front = json.loads(front_raw)
    except json.JSONDecodeError as exc:
        raise WikiStoreError(f"page `{slug}` front-matter JSON 解析失败: {exc}") from exc
    if not isinstance(front, dict):
        raise WikiStoreError(f"page `{slug}` front-matter 不是对象")
    title = front.get("title")
    kind = front.get("kind")
    source_ids = front.get("source_ids") or []
    if not isinstance(title, str) or not title.strip():
        raise WikiStoreError(f"page `{slug}` 缺少 title")
    if not isinstance(kind, str):
        raise WikiStoreError(f"page `{slug}` 缺少 kind")
    if not isinstance(source_ids, list):
        raise WikiStoreError(f"page `{slug}` source_ids 必须是数组")
    page = WikiPage(
        slug=slug,
        title=title,
        kind=kind,
        source_ids=[str(item) for item in source_ids],
        last_maintained_at=front.get("last_maintained_at"),
        last_maintained_by=front.get("last_maintained_by"),
        body=body,
    )
    return page


def _meta_from_page(page: WikiPage) -> WikiPageMeta:
    return WikiPageMeta(
        slug=page.slug,
        title=page.title,
        kind=page.kind,
        source_ids=list(page.source_ids),
        last_maintained_at=page.last_maintained_at,
        last_maintained_by=page.last_maintained_by,
    )


def _render_initial_index() -> str:
    return (
        "# Wiki Index\n\n"
        "这个目录由 LLM Wiki 维护层管理。\n\n"
        "| Slug | Kind | Title |\n"
        "| --- | --- | --- |\n"
        "| overview | overview | Project Overview |\n"
        "| source-intake | source-intake | Source Intake |\n"
        "| glossary | glossary | Glossary |\n"
        "| rules-and-conflicts | rules-and-conflicts | Rules And Conflicts |\n"
        "| open-questions | open-questions | Open Questions |\n\n"
        "维护者新增页面时必须更新本表。\n"
    )


def _render_initial_log() -> str:
    return "# Wiki Log\n\n本文件按时间顺序追加维护记录，不要 Edit 历史条目。\n"


def _now_iso(settings: AppSettings) -> str:
    return datetime.now(ZoneInfo(settings.default_timezone)).isoformat()
