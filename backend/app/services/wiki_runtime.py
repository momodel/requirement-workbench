from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, TYPE_CHECKING
from zoneinfo import ZoneInfo

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    ProviderIssue,
    ProviderReadiness,
    WikiMaintenanceResult,
    WikiPage,
    WikiPageMeta,
    WikiRecord,
)
from .project_catalog import ProjectCatalog
from .wiki_store import (
    INDEX_FILE_NAME,
    WikiStore,
    WikiStoreError,
)

if TYPE_CHECKING:
    from .wiki_maintenance import WikiMaintainer


logger = logging.getLogger(__name__)


WIKI_PROVIDER = "LLM_WIKI"


ReadinessProbe = Callable[[], ProviderReadiness]


class ClaudeWikiRuntime:
    """Project-local LLM Wiki runtime.

    Phase 1 scope: filesystem-backed wiki with skeleton initialization,
    page list/read, and honest readiness reporting. Maintenance via
    Claude Agent SDK lands in phase 2 (`maintain_after_*` raise until then).
    """

    def __init__(
        self,
        settings: AppSettings = DEFAULT_SETTINGS,
        *,
        catalog: ProjectCatalog | None = None,
        store: WikiStore | None = None,
        sdk_readiness_probe: ReadinessProbe | None = None,
        maintainer: "WikiMaintainer | None" = None,
    ):
        self.settings = settings
        self.catalog = catalog or ProjectCatalog(settings)
        self.store = store or WikiStore(settings)
        self._sdk_readiness_probe = sdk_readiness_probe
        self.maintainer = maintainer
        self._event_loop: asyncio.AbstractEventLoop | None = None

    def attach_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Capture the running event loop so sync routes can schedule maintenance."""
        self._event_loop = loop

    # ----- availability -----

    def ensure_available(self) -> Path:
        projects_dir = self.settings.projects_dir
        try:
            projects_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProviderIssue(
                provider=WIKI_PROVIDER,
                message=f"项目数据目录无法创建：{projects_dir} ({exc})",
            ) from exc
        if not os.access(projects_dir, os.W_OK):
            raise ProviderIssue(
                provider=WIKI_PROVIDER,
                message=f"项目数据目录不可写：{projects_dir}",
            )
        return projects_dir

    def get_global_readiness(self) -> ProviderReadiness:
        try:
            location = self.ensure_available()
        except ProviderIssue as exc:
            return ProviderReadiness(
                provider=WIKI_PROVIDER,
                status="error",
                summary="LLM Wiki 数据目录不可用。",
                detail=exc.message,
                action_label="检查 data/projects/ 权限",
            )

        sdk_state = self._probe_sdk_state()
        if self.maintainer is None:
            return ProviderReadiness(
                provider=WIKI_PROVIDER,
                status="not_configured",
                summary="LLM Wiki 维护子 agent 尚未实装。",
                detail=(
                    f"项目数据目录已就绪：{location}。"
                    "WikiMaintainer 未注入，无法触发维护。"
                ),
                action_label="实装 WikiMaintainer",
            )

        if sdk_state == "not_configured":
            return ProviderReadiness(
                provider=WIKI_PROVIDER,
                status="degraded_readonly",
                summary="LLM Wiki 已就绪，但维护子 agent 不可用。",
                detail=(
                    "Claude Agent SDK 尚未配置；现有 wiki 页面可读，"
                    "新的 source 入库不会触发维护。"
                ),
                action_label="配置 Claude Code CLI",
            )

        if sdk_state in {"error", "auth_required"}:
            return ProviderReadiness(
                provider=WIKI_PROVIDER,
                status="degraded_readonly",
                summary="LLM Wiki 维护子 agent 暂不可用。",
                detail=(
                    f"Claude Agent SDK readiness={sdk_state}; "
                    "现有 wiki 页面可读，新维护会被跳过。"
                ),
                action_label="检查 Claude Agent SDK",
            )

        return ProviderReadiness(
            provider=WIKI_PROVIDER,
            status="ready",
            summary="LLM Wiki 维护子 agent 就绪。",
            detail=(
                f"项目数据目录：{location}。"
                "维护通过 Claude Agent SDK 在项目内 wiki 目录里使用 Read/Write/Edit/Glob 工具完成。"
            ),
        )

    def get_project_readiness(
        self,
        project_id: str,
        claude: ProviderReadiness | None = None,
    ) -> ProviderReadiness:
        project = self.catalog.get_project(project_id)
        if not project:
            return ProviderReadiness(
                provider=WIKI_PROVIDER,
                status="missing",
                summary="项目不存在。",
                detail=f"找不到 project_id={project_id}。",
            )

        global_readiness = self.get_global_readiness()
        if global_readiness.status == "error":
            return global_readiness

        index_exists = self.store.index_path(project_id).exists()
        if not index_exists:
            return ProviderReadiness(
                provider=WIKI_PROVIDER,
                status="pending_init",
                summary="当前项目还没有初始化 LLM Wiki。",
                detail=(
                    "GET 项目 readiness 或调用 ensure_project_wiki 会创建骨架。"
                ),
                action_label="初始化 wiki 骨架",
            )

        page_count = len(self.store.list_pages(project_id))
        return ProviderReadiness(
            provider=WIKI_PROVIDER,
            status=global_readiness.status,
            summary=(
                f"项目 wiki 已存在 {page_count} 页。"
                if global_readiness.status != "error"
                else "wiki 数据目录不可用。"
            ),
            detail=global_readiness.detail,
            action_label=global_readiness.action_label,
        )

    # ----- ops -----

    def ensure_project_wiki(self, project_id: str) -> WikiRecord:
        project = self.catalog.get_project(project_id)
        if not project:
            raise ProviderIssue(
                provider=WIKI_PROVIDER,
                message=f"找不到 project_id={project_id}。",
                status_code=404,
            )
        try:
            self.store.ensure_skeleton(project)
        except WikiStoreError as exc:
            raise ProviderIssue(
                provider=WIKI_PROVIDER,
                message=f"初始化 wiki 骨架失败：{exc}",
            ) from exc
        return self._build_record(project_id)

    def list_pages(self, project_id: str) -> list[WikiPageMeta]:
        return self.store.list_pages(project_id)

    def read_page(self, project_id: str, slug: str) -> WikiPage:
        try:
            return self.store.read_page(project_id, slug)
        except FileNotFoundError as exc:
            raise ProviderIssue(
                provider=WIKI_PROVIDER,
                message=str(exc),
                status_code=404,
            ) from exc
        except WikiStoreError as exc:
            raise ProviderIssue(
                provider=WIKI_PROVIDER,
                message=str(exc),
            ) from exc

    def get_record(self, project_id: str) -> WikiRecord:
        return self._build_record(project_id)

    # ----- maintenance (phase 2 entrypoints) -----

    async def maintain_after_ingest(
        self,
        project_id: str,
        source_id: str,
    ) -> WikiMaintenanceResult:
        if self.maintainer is None:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="skipped",
                error="WikiMaintainer 未注入。",
                trigger_kind="source_ingested",
            )
        sdk_state = self._probe_sdk_state()
        if sdk_state in {"not_configured", "auth_required", "error"}:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="skipped",
                error=f"claude_sdk_unavailable: status={sdk_state}",
                trigger_kind="source_ingested",
            )
        return await self.maintainer.run(
            project_id,
            trigger_kind="source_ingested",
            source_id=source_id,
        )

    async def maintain_after_checkpoint(
        self,
        project_id: str,
        version_summary: str | None = None,
    ) -> WikiMaintenanceResult:
        if self.maintainer is None:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="skipped",
                error="WikiMaintainer 未注入。",
                trigger_kind="version_checkpoint",
            )
        sdk_state = self._probe_sdk_state()
        if sdk_state in {"not_configured", "auth_required", "error"}:
            return WikiMaintenanceResult(
                project_id=project_id,
                status="skipped",
                error=f"claude_sdk_unavailable: status={sdk_state}",
                trigger_kind="version_checkpoint",
            )
        return await self.maintainer.run(
            project_id,
            trigger_kind="version_checkpoint",
            version_summary=version_summary,
        )

    async def run_health_probe(self, project_id: str) -> WikiMaintenanceResult:
        if self.maintainer is None:
            raise ProviderIssue(
                provider=WIKI_PROVIDER,
                message="WikiMaintainer 未注入，无法运行健康探针。",
            )
        return await self.maintainer.run_health_probe(project_id)

    # ----- scheduling -----

    def schedule_maintain_after_ingest(
        self,
        project_id: str,
        source_id: str,
    ) -> None:
        """Fire-and-forget wiki maintenance after a source has been indexed.

        Marks source row wiki_sync_status='maintaining' immediately, then schedules
        the maintainer; the resulting status is written back to catalog when the
        maintainer completes (or fails). RAG indexing is unaffected by wiki failure.
        """
        if self.maintainer is None:
            self._record_skipped(source_id, "WikiMaintainer 未注入")
            return
        try:
            self.catalog.update_source_wiki_status(
                source_id=source_id,
                wiki_sync_status="maintaining",
                wiki_error=None,
            )
        except LookupError:
            return

        async def runner() -> None:
            try:
                result = await self.maintain_after_ingest(project_id, source_id)
            except Exception as exc:  # noqa: BLE001 — fire-and-forget must not crash loop
                logger.exception("wiki maintenance crashed")
                self._record_failed(source_id, str(exc))
                return
            self._record_result(source_id, result)

        self._dispatch(runner())

    def schedule_maintain_after_checkpoint(
        self,
        project_id: str,
        version_summary: str | None,
    ) -> None:
        """Fire-and-forget wiki maintenance after a version snapshot was created."""
        if self.maintainer is None:
            return

        async def runner() -> None:
            try:
                await self.maintain_after_checkpoint(project_id, version_summary)
            except Exception:  # noqa: BLE001
                logger.exception("wiki checkpoint maintenance crashed")

        self._dispatch(runner())

    # ----- internals -----

    def _dispatch(self, coro) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            loop.create_task(coro)
            return
        if self._event_loop is not None and self._event_loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self._event_loop)
            return
        logger.warning("wiki maintenance dispatched but no running loop available; dropping")
        coro.close()

    def _record_result(self, source_id: str, result: WikiMaintenanceResult) -> None:
        timestamp = (
            _now_iso(self.settings) if result.status == "maintained" else None
        )
        try:
            self.catalog.update_source_wiki_status(
                source_id=source_id,
                wiki_sync_status=result.status,
                wiki_error=result.error,
                wiki_maintained_at=timestamp,
            )
        except LookupError:
            return

    def _record_skipped(self, source_id: str, reason: str) -> None:
        try:
            self.catalog.update_source_wiki_status(
                source_id=source_id,
                wiki_sync_status="skipped",
                wiki_error=reason,
            )
        except LookupError:
            return

    def _record_failed(self, source_id: str, reason: str) -> None:
        try:
            self.catalog.update_source_wiki_status(
                source_id=source_id,
                wiki_sync_status="failed",
                wiki_error=reason,
            )
        except LookupError:
            return

    # ----- internals -----

    def _probe_sdk_state(self) -> str:
        if self._sdk_readiness_probe is None:
            return "unknown"
        try:
            readiness = self._sdk_readiness_probe()
        except Exception:  # noqa: BLE001 — probe must never crash readiness
            return "error"
        return readiness.status

    def _build_record(self, project_id: str) -> WikiRecord:
        pages = self.store.list_pages(project_id)
        last = max(
            (page.last_maintained_at for page in pages if page.last_maintained_at),
            default=None,
        )
        wiki_dir = self.store.project_wiki_dir(project_id)
        return WikiRecord(
            project_id=project_id,
            page_count=len(pages),
            last_maintained_at=last,
            pending_source_ids=self._pending_source_ids(project_id),
            detail=str(wiki_dir / INDEX_FILE_NAME),
        )

    def _pending_source_ids(self, project_id: str) -> list[str]:
        pending: list[str] = []
        try:
            sources = self.catalog.list_sources(project_id)
        except Exception:  # noqa: BLE001 — runtime info is best-effort
            return pending
        for source in sources:
            if source.wiki_sync_status not in {"maintained"}:
                pending.append(source.id)
        return pending


def _now_iso(settings: AppSettings) -> str:
    return datetime.now(ZoneInfo(settings.default_timezone)).isoformat()
