from __future__ import annotations

import asyncio
import importlib
import threading
import uuid
from pathlib import Path
from typing import Awaitable, Callable, TypeVar
from urllib.parse import urlparse

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    BindNotebookRequest,
    ChatCitation,
    CreateNotebookBindingResponse,
    CreateNotebookRequest,
    EvidenceResult,
    NotebookLibraryItem,
    NotebookBindingRecord,
    ProjectReadiness,
    ProviderIssue,
    ProviderReadiness,
)
from .project_catalog import ProjectCatalog


NOTEBOOKLM_PROVIDER = "NOTEBOOKLM_PY"
NOTEBOOK_BASE_URL = "https://notebooklm.google.com/notebook"
NOTEBOOK_MOCK_BASE_URL = "mock://notebooklm"
T = TypeVar("T")


class NotebookLMService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings
        self.catalog = ProjectCatalog(settings)

    @property
    def notebooklm_home_dir(self) -> Path:
        return self.settings.notebooklm_home_dir

    @property
    def storage_state_path(self) -> Path:
        return self.notebooklm_home_dir / "storage_state.json"

    @property
    def mock_enabled(self) -> bool:
        return self.settings.notebooklm_mode == "mock"

    def _login_command(self) -> str:
        return (
            "cd backend && "
            f"NOTEBOOKLM_HOME={self.settings.notebooklm_home_dir} "
            "./.venv/bin/notebooklm login"
        )

    def _load_client_class(self):
        if self.mock_enabled:
            return None
        try:
            module = importlib.import_module("notebooklm.client")
        except ModuleNotFoundError as exc:
            raise ProviderIssue(
                provider=NOTEBOOKLM_PROVIDER,
                message=(
                    "当前后端环境没有安装 notebooklm-py。"
                    "请先在 backend 虚拟环境里安装依赖，再启动服务。"
                ),
            ) from exc
        return module.NotebookLMClient

    def ensure_available(self) -> Path:
        if self.mock_enabled:
            self.notebooklm_home_dir.mkdir(parents=True, exist_ok=True)
            return self.notebooklm_home_dir
        self.notebooklm_home_dir.mkdir(parents=True, exist_ok=True)
        self._load_client_class()
        if not self.storage_state_path.exists():
            raise ProviderIssue(
                provider=NOTEBOOKLM_PROVIDER,
                message=(
                    "NotebookLM 还没有完成项目内认证。"
                    f"请先执行：{self._login_command()}"
                ),
            )
        return self.storage_state_path

    def _wrap_client_error(self, exc: Exception) -> ProviderIssue:
        message = str(exc).strip()
        lowered = message.lower()
        if (
            "storage_state" in lowered
            or "notebooklm login" in lowered
            or "authentication expired" in lowered
            or "re-authenticate" in lowered
        ):
            return ProviderIssue(
                provider=NOTEBOOKLM_PROVIDER,
                message=(
                    "NotebookLM 认证失效或还未完成项目内认证。"
                    f"请先执行：{self._login_command()}"
                ),
            )

        return ProviderIssue(
            provider=NOTEBOOKLM_PROVIDER,
            message=f"NotebookLM 调用失败：{message or exc.__class__.__name__}",
        )

    def _run_async(self, factory: Callable[[], Awaitable[T]]) -> T:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(factory())

        result: dict[str, T] = {}
        error: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(factory())
            except BaseException as exc:  # pragma: no cover - forwarded to caller
                error["value"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()

        if "value" in error:
            raise error["value"]
        return result["value"]

    def _with_client(self, callback: Callable[[object], Awaitable[T]]) -> T:
        client_class = self._load_client_class()
        storage_state_path = self.ensure_available()

        async def operation() -> T:
            async with await client_class.from_storage(str(storage_state_path)) as client:
                return await callback(client)

        try:
            return self._run_async(operation)
        except ProviderIssue:
            raise
        except Exception as exc:
            raise self._wrap_client_error(exc) from exc

    @staticmethod
    def _build_notebook_url(notebook_id: str) -> str:
        return f"{NOTEBOOK_BASE_URL}/{notebook_id}"

    @staticmethod
    def _build_mock_notebook_url(notebook_id: str) -> str:
        return f"{NOTEBOOK_MOCK_BASE_URL}/{notebook_id}"

    @staticmethod
    def _extract_notebook_id_from_url(source_url: str) -> str:
        parsed = urlparse(source_url)
        parts = [part for part in parsed.path.split("/") if part]
        if "notebook" not in parts:
            raise ProviderIssue(
                provider=NOTEBOOKLM_PROVIDER,
                message=f"无法从链接里解析 notebook_id：{source_url}",
                status_code=400,
            )

        notebook_index = parts.index("notebook")
        if notebook_index + 1 >= len(parts) or not parts[notebook_index + 1]:
            raise ProviderIssue(
                provider=NOTEBOOKLM_PROVIDER,
                message=f"链接里缺少 notebook_id：{source_url}",
                status_code=400,
            )
        return parts[notebook_index + 1]

    def _to_library_item(self, notebook: object) -> NotebookLibraryItem:
        created_at = getattr(notebook, "created_at", None)
        return NotebookLibraryItem(
            id=str(getattr(notebook, "id")),
            name=str(getattr(notebook, "title")),
            url=self._build_notebook_url(str(getattr(notebook, "id"))),
            description="",
            topics=[],
            use_count=0,
            last_used=created_at.isoformat() if created_at else None,
        )

    def get_global_readiness(self) -> ProviderReadiness:
        if self.mock_enabled:
            return ProviderReadiness(
                provider=NOTEBOOKLM_PROVIDER,
                status="ready",
                summary="NotebookLM mock 模式已启用，证据检索将走本地快速摘要。",
                detail=(
                    "当前不会访问真实 NotebookLM notebook。\n"
                    "适合本地联调和提速验证；切回真实模式请设置 NOTEBOOKLM_MODE=real。"
                ),
            )

        try:
            self._load_client_class()
        except ProviderIssue as exc:
            return ProviderReadiness(
                provider=NOTEBOOKLM_PROVIDER,
                status="not_configured",
                summary="NotebookLM provider 未就绪。",
                detail=exc.message,
                action_label="安装 notebooklm-py",
            )

        self.notebooklm_home_dir.mkdir(parents=True, exist_ok=True)
        if not self.storage_state_path.exists():
            return ProviderReadiness(
                provider=NOTEBOOKLM_PROVIDER,
                status="auth_required",
                summary="NotebookLM 还没有完成项目内认证。",
                detail=(
                    f"当前项目内 home 目录：{self.notebooklm_home_dir}\n"
                    f"请先执行：{self._login_command()}"
                ),
                action_label="完成项目内登录",
            )

        try:
            self._with_client(lambda client: client.notebooks.list())
        except ProviderIssue as exc:
            return ProviderReadiness(
                provider=NOTEBOOKLM_PROVIDER,
                status="error",
                summary="NotebookLM provider 检查失败。",
                detail=exc.message,
                action_label="检查 NotebookLM 配置",
            )

        return ProviderReadiness(
            provider=NOTEBOOKLM_PROVIDER,
            status="ready",
            summary="NotebookLM provider 已就绪。",
            detail=f"项目内 home 目录：{self.notebooklm_home_dir}",
        )

    def get_project_readiness(self, project_id: str, claude: ProviderReadiness) -> ProjectReadiness:
        notebook_global = self.get_global_readiness()
        binding = self.catalog.get_notebook_binding(project_id)

        if self.mock_enabled:
            notebook_status = ProviderReadiness(
                provider=NOTEBOOKLM_PROVIDER,
                status="ready",
                summary="当前项目走 NotebookLM mock 证据模式，无需绑定真实 notebook。",
                detail="项目资料会直接参与本地快速摘要与引用生成。",
            )
        elif notebook_global.status != "ready":
            notebook_status = notebook_global
        elif binding is None:
            notebook_status = ProviderReadiness(
                provider=NOTEBOOKLM_PROVIDER,
                status="binding_required",
                summary="当前项目还没有绑定专属 NotebookLM notebook。",
                detail="需要先为这个项目创建或绑定专属 notebook，不能复用全局默认 notebook。",
                action_label="绑定项目 notebook",
            )
        else:
            notebook_status = ProviderReadiness(
                provider=NOTEBOOKLM_PROVIDER,
                status="ready",
                summary="当前项目已绑定专属 NotebookLM notebook。",
                detail=f"Notebook ID: {binding.notebook_id}",
            )

        return ProjectReadiness(
            project_id=project_id,
            claude=claude,
            notebooklm=notebook_status,
            notebook_binding=binding,
        )

    def list_library(self) -> list[NotebookLibraryItem]:
        if self.mock_enabled:
            items: list[NotebookLibraryItem] = []
            for project in self.catalog.list_projects():
                binding = self.catalog.get_notebook_binding(project.id)
                if not binding:
                    continue
                items.append(
                    NotebookLibraryItem(
                        id=binding.notebook_id,
                        name=f"{project.name}（mock）",
                        url=binding.source_url or self._build_mock_notebook_url(binding.notebook_id),
                        description="本地 mock notebook 绑定，仅用于联调。",
                        topics=[],
                        use_count=0,
                        last_used=binding.last_synced_at,
                    )
                )
            return items

        async def load(client) -> list[NotebookLibraryItem]:
            notebooks = await client.notebooks.list()
            return [self._to_library_item(notebook) for notebook in notebooks]

        return self._with_client(load)

    def bind_project_notebook(
        self,
        project_id: str,
        payload: BindNotebookRequest,
    ) -> NotebookBindingRecord:
        project = self.catalog.get_project(project_id)
        if not project:
            raise LookupError("Project not found")

        if self.mock_enabled:
            notebook_id = (
                payload.notebook_id
                or (
                    self._extract_notebook_id_from_url(payload.source_url)
                    if payload.source_url
                    else f"mock-{project_id}"
                )
            )
            binding = self.catalog.upsert_notebook_binding(
                project_id=project_id,
                notebook_id=notebook_id,
                provider=NOTEBOOKLM_PROVIDER,
                sync_status="bound",
                source_url=payload.source_url or self._build_mock_notebook_url(notebook_id),
            )
            self.sync_project_sources(project_id)
            return binding

        notebook_id = payload.notebook_id or self._extract_notebook_id_from_url(payload.source_url or "")

        async def load(client):
            return await client.notebooks.get(notebook_id)

        notebook = self._with_client(load)
        binding = self.catalog.upsert_notebook_binding(
            project_id=project_id,
            notebook_id=str(getattr(notebook, "id")),
            provider=NOTEBOOKLM_PROVIDER,
            sync_status="bound",
            source_url=payload.source_url or self._build_notebook_url(str(getattr(notebook, "id"))),
        )
        self.sync_project_sources(project_id)
        return binding

    def create_and_bind_project_notebook(
        self,
        project_id: str,
        payload: CreateNotebookRequest,
    ) -> CreateNotebookBindingResponse:
        project = self.catalog.get_project(project_id)
        if not project:
            raise LookupError("Project not found")

        notebook_name = payload.notebook_name or project.name

        if self.mock_enabled:
            notebook_id = f"mock-{project_id}-{uuid.uuid4().hex[:6]}"
            notebook = NotebookLibraryItem(
                id=notebook_id,
                name=notebook_name,
                url=self._build_mock_notebook_url(notebook_id),
                description="本地 mock notebook，仅用于联调。",
                topics=payload.topics,
                use_count=0,
                last_used=None,
            )
            binding = self.catalog.upsert_notebook_binding(
                project_id=project_id,
                notebook_id=notebook.id,
                provider=NOTEBOOKLM_PROVIDER,
                sync_status="bound",
                source_url=notebook.url,
            )
            self.sync_project_sources(project_id)
            return CreateNotebookBindingResponse(notebook=notebook, binding=binding)

        async def create(client):
            return await client.notebooks.create(notebook_name)

        notebook = self._with_client(create)
        notebook_item = self._to_library_item(notebook)
        binding = self.catalog.upsert_notebook_binding(
            project_id=project_id,
            notebook_id=notebook_item.id,
            provider=NOTEBOOKLM_PROVIDER,
            sync_status="bound",
            source_url=notebook_item.url,
        )
        self.sync_project_sources(project_id)
        return CreateNotebookBindingResponse(notebook=notebook_item, binding=binding)

    def _resolve_upload_target(self, source_record) -> tuple[str, str]:
        raw_path = Path(source_record.storage_path) if source_record.storage_path else None
        normalized_path = (
            Path(source_record.normalized_path) if source_record.normalized_path else None
        )

        if source_record.source_kind == "url":
            if not raw_path or not raw_path.exists():
                raise ProviderIssue(
                    provider=NOTEBOOKLM_PROVIDER,
                    message=f"URL source {source_record.name} 缺少原始 URL 记录。",
                )
            source_url = raw_path.read_text(encoding="utf-8").strip()
            if not source_url:
                raise ProviderIssue(
                    provider=NOTEBOOKLM_PROVIDER,
                    message=f"URL source {source_record.name} 的 URL 内容为空。",
                )
            return ("url", source_url)

        if normalized_path and normalized_path.exists():
            return ("text", normalized_path.read_text(encoding="utf-8", errors="ignore"))

        if raw_path and raw_path.exists():
            return ("file", str(raw_path))

        raise ProviderIssue(
            provider=NOTEBOOKLM_PROVIDER,
            message=f"source {source_record.name} 缺少可同步文件。",
        )

    def sync_source(self, source_id: str):
        source_record = self.catalog.get_source(source_id)
        if not source_record:
            raise LookupError("Source not found")

        if self.mock_enabled:
            return self.catalog.update_source_sync_status(
                source_id=source_id,
                sync_status="synced",
                sync_error=None,
            )

        binding = self.catalog.get_notebook_binding(source_record.project_id)
        if not binding:
            return self.catalog.update_source_sync_status(
                source_id=source_id,
                sync_status="binding_required",
                sync_error="当前项目还没有绑定专属 NotebookLM notebook。",
            )

        try:
            upload_kind, payload = self._resolve_upload_target(source_record)

            async def upload(client):
                if upload_kind == "url":
                    return await client.sources.add_url(binding.notebook_id, payload, wait=True)
                if upload_kind == "text":
                    return await client.sources.add_text(
                        binding.notebook_id,
                        source_record.name,
                        payload,
                        wait=True,
                    )
                return await client.sources.add_file(binding.notebook_id, payload, wait=True)

            self._with_client(upload)
            return self.catalog.update_source_sync_status(
                source_id=source_id,
                sync_status="synced",
                sync_error=None,
            )
        except ProviderIssue as exc:
            return self.catalog.update_source_sync_status(
                source_id=source_id,
                sync_status="sync_failed",
                sync_error=exc.message,
            )

    def sync_project_sources(self, project_id: str) -> list:
        synced = []
        for source_record in self.catalog.list_sources(project_id):
            synced.append(self.sync_source(source_record.id))
        return synced

    def delete_source(self, source_id: str):
        source_record = self.catalog.get_source(source_id)
        if not source_record:
            raise LookupError("Source not found")

        binding = self.catalog.get_notebook_binding(source_record.project_id)
        remote_delete_required = (
            binding is not None
            and source_record.sync_status == "synced"
        )

        if remote_delete_required:
            async def remove_remote_source(client):
                notebook_sources = await client.sources.list(binding.notebook_id)
                matched_sources = [
                    source for source in notebook_sources if getattr(source, "title", None) == source_record.name
                ]
                if not matched_sources:
                    raise ProviderIssue(
                        provider=NOTEBOOKLM_PROVIDER,
                        message=(
                            f"NotebookLM notebook 里没有找到同名 source：{source_record.name}。"
                            "为避免本地和 notebook 状态不一致，本次没有执行删除。"
                        ),
                        status_code=409,
                    )
                if len(matched_sources) > 1:
                    raise ProviderIssue(
                        provider=NOTEBOOKLM_PROVIDER,
                        message=(
                            f"NotebookLM notebook 里找到多个同名 source：{source_record.name}。"
                            "当前无法安全判断该删哪一个，请先在 notebook 里清理重名资料。"
                        ),
                        status_code=409,
                    )
                await client.sources.delete(binding.notebook_id, str(getattr(matched_sources[0], "id")))

            self._with_client(remove_remote_source)

        return self.catalog.delete_source(source_id)

    def query(
        self,
        project_id: str,
        question: str,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        if self.mock_enabled:
            return self._query_in_mock_mode(project_id, question, selected_source_ids)

        binding = self.catalog.get_notebook_binding(project_id)
        if not binding:
            raise ProviderIssue(
                provider=NOTEBOOKLM_PROVIDER,
                message="当前项目未绑定 NotebookLM notebook。",
            )

        async def ask(client):
            answer = await client.chat.ask(binding.notebook_id, question)
            notebook_sources = await client.sources.list(binding.notebook_id)
            return answer, notebook_sources

        answer, notebook_sources = self._with_client(ask)
        cleaned_answer = (getattr(answer, "answer", "") or "").strip()
        if not cleaned_answer:
            raise ProviderIssue(
                provider=NOTEBOOKLM_PROVIDER,
                message="NotebookLM 未返回任何内容。",
            )

        local_source_map = {
            source.name: source.id for source in self.catalog.list_sources(project_id)
        }
        notebook_source_titles = {
            str(getattr(source, "id")): (
                getattr(source, "title", None)
                or getattr(source, "url", None)
                or f"NotebookLM source {getattr(source, 'id')}"
            )
            for source in notebook_sources
        }

        citations: list[ChatCitation] = []
        seen_citations: set[tuple[str, str | None, str | None]] = set()
        for reference in getattr(answer, "references", []):
            title = notebook_source_titles.get(
                str(getattr(reference, "source_id")),
                f"NotebookLM source {getattr(reference, 'source_id')}",
            )
            snippet = getattr(reference, "cited_text", None) or None
            local_source_id = local_source_map.get(title)
            citation_key = (title, snippet, local_source_id)
            if citation_key in seen_citations:
                continue
            seen_citations.add(citation_key)
            citations.append(
                ChatCitation(
                    title=title,
                    snippet=snippet,
                    source_id=local_source_id,
                )
            )

        return EvidenceResult(
            summary=cleaned_answer,
            citations=citations,
            sync_status="queried",
        )

    def _query_in_mock_mode(
        self,
        project_id: str,
        question: str,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        sources = self.catalog.list_sources(project_id)
        if selected_source_ids:
            selected = set(selected_source_ids)
            sources = [source for source in sources if source.id in selected] or sources
        if not sources:
            return EvidenceResult(
                summary="当前项目还没有可用资料，暂时无法给出 grounded 证据摘要。",
                citations=[],
                sync_status="mock_queried",
            )

        def score_source(source) -> tuple[int, int]:
            haystack = " ".join(
                part
                for part in [
                    source.name,
                    source.parse_summary or "",
                    source.source_kind,
                    source.upload_kind,
                ]
                if part
            ).lower()
            tokens = [token for token in question.lower().replace("？", " ").replace("，", " ").split() if token]
            score = sum(1 for token in tokens if token and token in haystack)
            if source.parse_summary:
                score += 1
            return score, len(source.parse_summary or "")

        ranked_sources = sorted(
            sources,
            key=score_source,
            reverse=True,
        )
        picked_sources = ranked_sources[: min(3, len(ranked_sources))]

        summary_lines = []
        citations: list[ChatCitation] = []
        for source in picked_sources:
            excerpt = (source.parse_summary or source.name or "").strip()
            if excerpt:
                summary_lines.append(f"{source.name} 提到：{excerpt}")
            citations.append(
                ChatCitation(
                    title=source.name,
                    snippet=excerpt or None,
                    source_id=source.id,
                )
            )

        summary = "；".join(summary_lines) if summary_lines else "当前资料里还没有可用摘要。"
        return EvidenceResult(
            summary=summary,
            citations=citations,
            sync_status="mock_queried",
        )
