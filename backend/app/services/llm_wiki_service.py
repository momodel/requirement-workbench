from __future__ import annotations

from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    KnowledgeWikiContext,
    ProjectReadiness,
    ProjectState,
    ProjectSummary,
    ProviderReadiness,
    SourceRecord,
    StateItem,
)
from .project_catalog import now_iso


WIKI_INDEX_TEMPLATE = """# Knowledge Base Index

这个目录由后端 LLM Wiki 知识整理层维护。

| 页面 | 作用 |
| --- | --- |
| [Project Overview](project-overview.md) | 项目背景和当前工作理解 |
| [Source Intake](source-intake.md) | 已接入资料的摘要索引 |
| [State Summary](state-summary.md) | 当前项目状态的阶段性沉淀 |
| [Rules And Conflicts](rules-and-conflicts.md) | 业务规则、冲突和待验证口径 |
"""

WIKI_LOG_TEMPLATE = "# Wiki Log\n"


class LLMWikiService:
    """Project-local LLM Wiki knowledge layer.

    It stores working understanding and source intake context without requiring
    a remote notebook provider.
    """

    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def wiki_dir(self, project_id: str) -> Path:
        path = self.settings.projects_dir / project_id / "wiki"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_global_readiness(self) -> ProviderReadiness:
        self.settings.projects_dir.mkdir(parents=True, exist_ok=True)
        return ProviderReadiness(
            provider="LLM_WIKI",
            status="ready",
            summary="LLM Wiki 知识库已启用。",
            detail=f"项目知识库目录：{self.settings.projects_dir}",
        )

    def get_project_readiness(
        self,
        project: ProjectSummary,
        claude: ProviderReadiness,
    ) -> ProjectReadiness:
        context = self.initialize_project(project)
        return ProjectReadiness(
            project_id=project.id,
            claude=claude,
            knowledge_wiki=ProviderReadiness(
                provider="LLM_WIKI",
                status="ready",
                summary="当前项目已启用 LLM Wiki 知识库。",
                detail=context.detail,
            ),
        )

    def initialize_project(self, project: ProjectSummary) -> KnowledgeWikiContext:
        wiki_dir = self.wiki_dir(project.id)
        self._write_once(wiki_dir / "index.md", WIKI_INDEX_TEMPLATE)
        self._write_once(wiki_dir / "log.md", WIKI_LOG_TEMPLATE)
        self._write_once(
            wiki_dir / "project-overview.md",
            self._project_overview(project),
        )
        self._write_once(
            wiki_dir / "source-intake.md",
            "# Source Intake\n\n当前还没有写入 source 摘要。\n",
        )
        self._write_once(
            wiki_dir / "state-summary.md",
            "# State Summary\n\n当前还没有阶段性状态沉淀。\n",
        )
        self._write_once(
            wiki_dir / "rules-and-conflicts.md",
            "# Rules And Conflicts\n\n当前还没有稳定业务规则或冲突沉淀。\n",
        )
        self._append_log(wiki_dir, "initialize", "初始化项目 LLM Wiki 骨架")
        return KnowledgeWikiContext(
            summary=(
                "LLM Wiki 当前只有初始化骨架。它用于保存项目工作理解，"
                "并作为本项目知识库上下文。"
            ),
            citations=[],
            detail=str(wiki_dir),
        )

    def record_source_intake(
        self,
        project: ProjectSummary,
        sources: list[SourceRecord],
    ) -> KnowledgeWikiContext:
        wiki_dir = self.wiki_dir(project.id)
        if not (wiki_dir / "index.md").exists():
            self.initialize_project(project)

        content = self._source_intake(project, sources)
        source_intake_path = wiki_dir / "source-intake.md"
        existing = source_intake_path.read_text(encoding="utf-8") if source_intake_path.exists() else ""
        if existing != content:
            source_intake_path.write_text(content, encoding="utf-8")
            self._append_log(wiki_dir, "source_intake", f"记录 {len(sources)} 份 source 摘要")
        return self.build_context(project.id)

    def record_state_checkpoint(
        self,
        project: ProjectSummary,
        state: ProjectState,
        *,
        trigger_kind: str,
        summary: str | None,
    ) -> KnowledgeWikiContext:
        wiki_dir = self.wiki_dir(project.id)
        if not (wiki_dir / "index.md").exists():
            self.initialize_project(project)

        changed = False
        state_content = self._state_summary(project, state, trigger_kind, summary)
        changed = self._write_if_changed(wiki_dir / "state-summary.md", state_content) or changed

        rules_content = self._rules_and_conflicts(project, state)
        changed = self._write_if_changed(wiki_dir / "rules-and-conflicts.md", rules_content) or changed

        if changed:
            self._append_log(
                wiki_dir,
                "state_checkpoint",
                summary or f"记录 {trigger_kind} 阶段性沉淀",
            )
        return self.build_context(project.id)

    def build_context(self, project_id: str) -> KnowledgeWikiContext:
        wiki_dir = self.wiki_dir(project_id)
        if not (wiki_dir / "index.md").exists():
            return KnowledgeWikiContext(
                summary=(
                    "当前项目还没有初始化 LLM Wiki。"
                    "LLM Wiki 是项目知识库层。"
                ),
                citations=[],
                detail=str(wiki_dir),
            )

        sections = [
            self._read_page_summary(wiki_dir / "project-overview.md"),
            self._read_page_summary(wiki_dir / "source-intake.md"),
            self._read_page_summary(wiki_dir / "state-summary.md"),
            self._read_page_summary(wiki_dir / "rules-and-conflicts.md"),
        ]
        compact = "\n\n".join(section for section in sections if section).strip()
        summary = (
            "LLM Wiki 是当前项目的知识库和连续记忆。\n\n"
            f"{compact or '当前还没有可用 Wiki 内容。'}"
        )
        return KnowledgeWikiContext(summary=summary, citations=[], detail=str(wiki_dir))

    @staticmethod
    def _write_once(path: Path, content: str) -> None:
        if path.exists():
            return
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def _write_if_changed(path: Path, content: str) -> bool:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if existing == content:
            return False
        path.write_text(content, encoding="utf-8")
        return True

    def _append_log(self, wiki_dir: Path, operation: str, summary: str) -> None:
        log_path = wiki_dir / "log.md"
        timestamp = now_iso(self.settings)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n## [{timestamp}] {operation}\n- {summary}\n")

    @staticmethod
    def _project_overview(project: ProjectSummary) -> str:
        return f"""# Project Overview

## 项目
- ID: {project.id}
- 名称: {project.name}
- 场景: {project.scenario_type}
- 状态: {project.status}

## 当前摘要
{project.summary}

## 使用边界
LLM Wiki 保存的是可修订的工作理解。涉及资料出处时，优先使用本地 source_id 和原始 source。
"""

    @staticmethod
    def _source_intake(project: ProjectSummary, sources: list[SourceRecord]) -> str:
        lines = [
            "# Source Intake",
            "",
            f"项目: {project.name}",
            "",
            "这些条目来自本地 source 记录的 parse summary，用于组织项目知识库上下文。",
            "",
        ]
        if not sources:
            lines.append("当前还没有写入 source 摘要。")
            return "\n".join(lines) + "\n"

        for source in sources:
            summary = source.parse_summary or source.name
            lines.extend(
                [
                    f"## {source.name}",
                    f"- source_id: {source.id}",
                    f"- source_kind: {source.source_kind}",
                    f"- parse_status: {source.parse_status}",
                    f"- sync_status: {source.sync_status}",
                    f"- summary: {summary}",
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def _state_summary(
        project: ProjectSummary,
        state: ProjectState,
        trigger_kind: str,
        summary: str | None,
    ) -> str:
        lines = [
            "# State Summary",
            "",
            f"项目: {project.name}",
            f"触发: {trigger_kind}",
            f"摘要: {summary or '本次没有额外摘要。'}",
            "",
            "阶段性沉淀代表当前工作理解。confirmed 判断仍由主智能体结合 source 和用户确认完成。",
            "",
        ]
        sections = [
            ("当前理解", state.current_understanding),
            ("待确认项", state.pending_items),
            ("已确认项", state.confirmed_items),
            ("冲突项", state.conflict_items),
            ("MVP", state.mvp_items),
        ]
        for title, items in sections:
            lines.append(f"## {title}")
            if not items:
                lines.extend(["当前无。", ""])
                continue
            lines.extend(LLMWikiService._format_state_items(items))
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _rules_and_conflicts(project: ProjectSummary, state: ProjectState) -> str:
        lines = [
            "# Rules And Conflicts",
            "",
            f"项目: {project.name}",
            "",
            "本页保存业务规则、映射关系和冲突的工作理解；原文依据回查本地 source。",
            "",
            "## 冲突项",
        ]
        if state.conflict_items:
            lines.extend(LLMWikiService._format_state_items(state.conflict_items))
        else:
            lines.append("当前无。")

        lines.extend(["", "## MVP 相关规则"])
        if state.mvp_items:
            lines.extend(LLMWikiService._format_state_items(state.mvp_items))
        else:
            lines.append("当前无。")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_state_items(items: list[StateItem]) -> list[str]:
        lines: list[str] = []
        for item in items:
            source_suffix = f" source_ids={item.source_ids}" if item.source_ids else ""
            lines.append(f"- {item.title}: {item.body}{source_suffix}")
        return lines

    @staticmethod
    def _read_page_summary(path: Path, max_chars: int = 1800) -> str:
        if not path.exists():
            return ""
        text = path.read_text(encoding="utf-8").strip()
        if len(text) <= max_chars:
            return text
        return f"{text[:max_chars].rstrip()}\n...（已截断）"
