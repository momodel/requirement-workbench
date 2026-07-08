from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from .llm_model import build_chat_model

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    ProjectSummary,
    ProviderIssue,
    SourceRecord,
    WikiMaintenanceResult,
    WikiPage,
)
from .project_catalog import ProjectCatalog
from .runtime_contracts import EvidenceRuntime
from .wiki_store import (
    HEALTH_FILE_NAME,
    INDEX_FILE_NAME,
    LOG_FILE_NAME,
    PAGES_DIR_NAME,
    WikiStore,
    WikiStoreError,
)


WIKI_MAINTAINER_PROVIDER = "LLM_WIKI_MAINTAINER"

DEFAULT_MAX_TURNS = 16
HEALTH_PROBE_MAX_TURNS = 6
HEALTH_PROBE_TIMEOUT_SECONDS = 240.0


@dataclass(slots=True)
class _Snapshot:
    files: dict[str, tuple[float, int]]


class WikiMaintenanceError(ProviderIssue):
    """Raised when wiki maintenance fails. ProviderIssue subclass for HTTP mapping."""


class WikiMaintainer:
    """Subagent that maintains the project's LLM Wiki via Claude Agent SDK.

    The maintainer runs `claude_agent_sdk.query()` with the wiki directory
    as cwd and Read/Write/Edit/Glob as allowed tools. It is intentionally
    decoupled from the chat loop and runs as a fire-and-forget background
    task on ingest / checkpoint events.
    """

    def __init__(
        self,
        settings: AppSettings = DEFAULT_SETTINGS,
        *,
        store: WikiStore,
        catalog: ProjectCatalog,
        evidence_runtime: EvidenceRuntime | None = None,
        skill_path: Path | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        self.settings = settings
        self.store = store
        self.catalog = catalog
        self.evidence_runtime = evidence_runtime
        self.max_turns = max_turns
        self._project_locks: dict[str, asyncio.Lock] = {}

        if skill_path is None:
            skill_path = (
                settings.root_dir
                / "backend"
                / ".claude"
                / "skills"
                / "llm-wiki-knowledge-workflow"
                / "SKILL.md"
            )
        self.skill_path = skill_path

    # ----- public entry points -----

    async def run(
        self,
        project_id: str,
        *,
        trigger_kind: str,
        source_id: str | None = None,
        version_summary: str | None = None,
    ) -> WikiMaintenanceResult:
        lock = self._project_locks.setdefault(project_id, asyncio.Lock())
        async with lock:
            return await self._run_locked(
                project_id,
                trigger_kind=trigger_kind,
                source_id=source_id,
                version_summary=version_summary,
            )

    async def run_health_probe(self, project_id: str) -> WikiMaintenanceResult:
        """Run a tiny SDK call that writes wiki/.health and verifies the marker.

        Used by ClaudeWikiRuntime.get_global_readiness to determine if the full
        maintenance pipeline (SDK + filesystem + permissions) is wired correctly.
        """
        project = self.catalog.get_project(project_id)
        if not project:
            raise WikiMaintenanceError(
                provider=WIKI_MAINTAINER_PROVIDER,
                message=f"找不到 project_id={project_id}。",
                status_code=404,
            )
        self.store.ensure_skeleton(project)

        marker = f"probe-{os.urandom(8).hex()}"
        wiki_dir = self.store.project_wiki_dir(project_id)
        prompt = (
            f"使用 write_file 工具创建文件 `.health`（相对路径，文件工具已收口在 wiki 根目录），内容只包含一行：`{marker}`。"
            f"完成后停止，不要执行其他操作。"
        )
        try:
            await asyncio.wait_for(
                self._run_query(
                    prompt=prompt,
                    cwd=wiki_dir,
                    system_prompt=(
                        f"你是 LLM Wiki 健康探针。"
                        f"文件工具已收口在 wiki 根目录。"
                        f"只允许使用 write_file 工具，且只能写入 `.health` 文件（相对路径）。"
                        f"不要写入任何其他路径。"
                    ),
                    allowed_tools=["Write"],
                    max_turns=HEALTH_PROBE_MAX_TURNS,
                ),
                timeout=HEALTH_PROBE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise WikiMaintenanceError(
                provider=WIKI_MAINTAINER_PROVIDER,
                message="LLM Wiki 健康探针超时。",
            ) from exc

        actual = self.store.read_health(project_id)
        if actual is None or marker not in actual:
            raise WikiMaintenanceError(
                provider=WIKI_MAINTAINER_PROVIDER,
                message="LLM Wiki 健康探针未能写入预期标记。",
            )
        return WikiMaintenanceResult(
            project_id=project_id,
            status="maintained",
            pages_changed=[HEALTH_FILE_NAME],
            log_entry="health probe ok",
            trigger_kind="health_probe",
        )

    # ----- internals -----

    async def _run_locked(
        self,
        project_id: str,
        *,
        trigger_kind: str,
        source_id: str | None,
        version_summary: str | None,
    ) -> WikiMaintenanceResult:
        project = self.catalog.get_project(project_id)
        if not project:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="failed",
                error=f"项目不存在: {project_id}",
                trigger_kind=trigger_kind,
            )
        self.store.ensure_skeleton(project)

        sources = self.catalog.list_sources(project_id)
        focus_source: SourceRecord | None = None
        if source_id:
            focus_source = next((s for s in sources if s.id == source_id), None)

        wiki_dir = self.store.project_wiki_dir(project_id)
        prompt = self._build_prompt(
            project=project,
            sources=sources,
            trigger_kind=trigger_kind,
            focus_source=focus_source,
            version_summary=version_summary,
            wiki_dir=wiki_dir,
        )
        before = self._snapshot(wiki_dir)
        try:
            await self._run_query(
                prompt=prompt,
                cwd=wiki_dir,
                system_prompt=self._system_prompt(wiki_dir=wiki_dir),
                allowed_tools=["Read", "Write", "Edit", "Glob"],
                max_turns=self.max_turns,
            )
        except ProviderIssue as exc:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="skipped",
                error=exc.message,
                trigger_kind=trigger_kind,
            )
        except ProviderIssue as exc:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="failed",
                error=exc.message,
                trigger_kind=trigger_kind,
            )

        after = self._snapshot(wiki_dir)
        changed = self._diff_snapshots(before, after)
        validation_error = self._validate_changes(project_id, changed, sources)
        if validation_error:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="failed",
                pages_changed=changed,
                error=validation_error,
                trigger_kind=trigger_kind,
            )

        log_entry = self._log_summary(
            trigger_kind=trigger_kind,
            focus_source=focus_source,
            version_summary=version_summary,
        )
        try:
            self.store.append_log(
                project_id,
                operation=trigger_kind,
                summary=log_entry,
                source_ids=[focus_source.id] if focus_source else None,
                pages_changed=changed,
            )
        except OSError as exc:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="failed",
                pages_changed=changed,
                error=f"log.md 追加失败: {exc}",
                trigger_kind=trigger_kind,
            )

        return WikiMaintenanceResult(
            project_id=project_id,
            status="maintained",
            pages_changed=changed,
            log_entry=log_entry,
            trigger_kind=trigger_kind,
        )

    def _get_model(self):
        return build_chat_model(self.settings, timeout=180, max_retries=1)

    async def _run_query(
        self,
        *,
        prompt: str,
        cwd: Path,
        system_prompt: str,
        allowed_tools: list[str],
        max_turns: int,
    ) -> None:
        # Deep Agents filesystem backend scoped to the wiki dir. virtual_mode=True
        # keeps file operations inside root_dir (relative paths only).
        backend = FilesystemBackend(root_dir=str(cwd), virtual_mode=True)
        agent = create_deep_agent(
            model=self._get_model(),
            system_prompt=system_prompt,
            backend=backend,
        )
        try:
            async for _mode, _chunk in agent.astream(
                {"messages": prompt},
                stream_mode=["updates"],
                config={"recursion_limit": max(max_turns * 4, 40)},
            ):
                pass
        except ProviderIssue:
            raise
        except Exception as exc:
            raise ProviderIssue(
                provider=WIKI_MAINTAINER_PROVIDER,
                message=str(exc) or "Wiki 维护子 agent 运行失败。",
            ) from exc

    def _system_prompt(self, wiki_dir: Path | None = None) -> str:
        skill_text = ""
        try:
            skill_text = self.skill_path.read_text(encoding="utf-8")
        except OSError:
            skill_text = ""
        cwd_line = (
            f"项目 wiki 根目录：{wiki_dir}。所有文件操作使用相对路径（如 pages/<slug>.md、.health），文件工具已收口在该目录下，不要使用绝对路径或 .. 跳出。"
            if wiki_dir
            else "所有文件操作使用相对路径，落在 wiki 根目录下。"
        )
        return (
            "你是项目 LLM Wiki 的维护子 agent。"
            f"{cwd_line}"
            "你只能使用 read_file / write_file / edit_file / ls / glob 工具。"
            "不要写入 wiki 之外的任何文件；不要修改 log.md 的历史条目。"
            "不允许伪造 source_id：用户提示词会列出本项目允许的 source_id 列表，只能从中挑。"
            "维护规则参考下面的 skill。\n\n"
            f"--- skill: llm-wiki-knowledge-workflow ---\n{skill_text}\n--- end skill ---"
        )

    def _build_prompt(
        self,
        *,
        project: ProjectSummary,
        sources: list[SourceRecord],
        trigger_kind: str,
        focus_source: SourceRecord | None,
        version_summary: str | None,
        wiki_dir: Path | None = None,
    ) -> str:
        page_metas = self.store.list_pages(project.id)
        page_index_lines = []
        for meta in page_metas:
            page_index_lines.append(
                json.dumps(
                    {
                        "slug": meta.slug,
                        "title": meta.title,
                        "kind": meta.kind,
                        "source_ids": meta.source_ids,
                        "last_maintained_at": meta.last_maintained_at,
                    },
                    ensure_ascii=False,
                )
            )

        allowed_source_ids = sorted({s.id for s in sources})
        allowed_source_block = json.dumps(allowed_source_ids, ensure_ascii=False)

        focus_block = self._render_focus_source(focus_source) if focus_source else ""
        version_block = (
            f"\n## 版本快照摘要\n{version_summary}\n" if version_summary else ""
        )

        cwd_block = (
            f"\n# 工作目录\nwiki 根目录：{wiki_dir}（文件工具已收口在此目录）。\n"
            f"所有文件操作使用相对路径；页面文件位于 `pages/<slug>.md`。\n"
            if wiki_dir
            else ""
        )
        return (
            f"# 触发\n{trigger_kind}\n"
            + cwd_block
            + f"\n# 项目\n- id: {project.id}\n- name: {project.name}\n"
            f"- scenario: {project.scenario_type}\n- summary: {project.summary}\n"
            f"\n# 当前 wiki 页面索引（仅元信息；页面正文用 read_file 自取）\n"
            + ("\n".join(page_index_lines) or "（暂无页面，先初始化）")
            + "\n"
            f"\n# 本项目允许引用的 source_id 白名单\n{allowed_source_block}\n"
            f"\n# 本项目所有 source 元信息\n"
            + (self._render_sources(sources) or "（当前没有 source）")
            + "\n"
            + focus_block
            + version_block
            + "\n# 硬规则\n"
            "1. 不许伪造 source_id，只能使用上面白名单里的。\n"
            "2. 每段断言必须能追到至少一个 source_id；front-matter 的 `source_ids` 字段务必保持完整。\n"
            "3. 优先用 edit_file 改写已有 markdown；只在确实需要新页面时才用 write_file。\n"
            "4. 不要修改 `log.md` 的历史条目；维护完成后由宿主追加。\n"
            "5. front-matter 是 JSON 格式，写入时严格保持合法 JSON。\n"
            "6. 不要离开 wiki 工作目录，也不要 write_file 任何 wiki 之外的路径。\n"
            "7. 完成维护就结束；不要循环 Read。\n"
            "\n开始维护。"
        )

    def _render_focus_source(self, source: SourceRecord) -> str:
        snippet_lines: list[str] = []
        if self.evidence_runtime is not None:
            try:
                evidence = self.evidence_runtime.query(
                    source.project_id,
                    source.name,
                    selected_source_ids=[source.id],
                )
                for citation in evidence.citations[:3]:
                    snippet = (citation.snippet or "").strip().replace("\n", " ")
                    if snippet:
                        snippet_lines.append(f"- {snippet[:240]}")
            except Exception:  # noqa: BLE001 — RAG snapshot is best-effort
                snippet_lines = []
        snippet_block = (
            "\n## RAG 抽样（仅参考，不构成 citation）\n"
            + "\n".join(snippet_lines)
            + "\n"
            if snippet_lines
            else ""
        )
        return (
            "\n# 焦点 source\n"
            f"- id: {source.id}\n"
            f"- name: {source.name}\n"
            f"- normalize_status: {source.normalize_status}\n"
            f"- index_status: {source.index_status}\n"
            f"- summary: {(source.normalize_summary or '').strip() or '（暂无摘要）'}\n"
            + snippet_block
        )

    def _render_sources(self, sources: list[SourceRecord]) -> str:
        if not sources:
            return ""
        lines = []
        for source in sources:
            lines.append(
                json.dumps(
                    {
                        "id": source.id,
                        "name": source.name,
                        "kind": source.source_kind,
                        "normalize_status": source.normalize_status,
                        "index_status": source.index_status,
                        "summary": (source.normalize_summary or "")[:200],
                    },
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines)

    def _log_summary(
        self,
        *,
        trigger_kind: str,
        focus_source: SourceRecord | None,
        version_summary: str | None,
    ) -> str:
        parts = [trigger_kind]
        if focus_source:
            parts.append(f"focus_source={focus_source.id}")
        if version_summary:
            parts.append(f"version_summary={version_summary[:80]}")
        return " | ".join(parts)

    # ----- snapshot / diff / validate -----

    @staticmethod
    def _snapshot(wiki_dir: Path) -> _Snapshot:
        files: dict[str, tuple[float, int]] = {}
        if not wiki_dir.exists():
            return _Snapshot(files=files)
        for entry in wiki_dir.rglob("*"):
            if not entry.is_file():
                continue
            rel = entry.relative_to(wiki_dir)
            # Skip anything under a dotted directory (e.g. `.runtime/` SDK state)
            # or whose own filename is dotted (e.g. `.health`, `.meta.json`).
            if any(part.startswith(".") for part in rel.parts):
                continue
            try:
                stat = entry.stat()
            except OSError:
                continue
            files[rel.as_posix()] = (stat.st_mtime, stat.st_size)
        return _Snapshot(files=files)

    @staticmethod
    def _diff_snapshots(before: _Snapshot, after: _Snapshot) -> list[str]:
        changed: list[str] = []
        for rel, info in after.files.items():
            if before.files.get(rel) != info:
                changed.append(rel)
        for rel in before.files:
            if rel not in after.files:
                changed.append(f"{rel} (deleted)")
        return sorted(set(changed))

    def _validate_changes(
        self,
        project_id: str,
        changed: Iterable[str],
        sources: list[SourceRecord],
    ) -> str | None:
        allowed_source_ids = {s.id for s in sources}
        wiki_dir = self.store.project_wiki_dir(project_id)
        for rel in changed:
            if rel.endswith(" (deleted)"):
                return f"维护子 agent 删除了文件: {rel.removesuffix(' (deleted)')}"
            absolute = wiki_dir / rel
            if rel == LOG_FILE_NAME or rel == INDEX_FILE_NAME or rel == HEALTH_FILE_NAME:
                continue
            if not rel.startswith(f"{PAGES_DIR_NAME}/"):
                return f"维护子 agent 写入了非法路径: {rel}"
            if not rel.endswith(".md"):
                return f"维护子 agent 写入了非 markdown 文件: {rel}"
            try:
                page = self.store.read_page(project_id, absolute.stem)
            except WikiStoreError as exc:
                return f"页面 {rel} 校验失败: {exc}"
            except FileNotFoundError:
                return f"页面 {rel} 写入后无法读取"
            for source_id in page.source_ids:
                if source_id not in allowed_source_ids:
                    return (
                        f"页面 {rel} 引用了未知 source_id={source_id}; "
                        f"白名单包含 {len(allowed_source_ids)} 个 ID"
                    )
        return None
