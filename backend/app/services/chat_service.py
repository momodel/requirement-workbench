from __future__ import annotations

import asyncio
import uuid

from ..models import AgentTurnInput, ChatStreamRequest, ProviderIssue
from .artifact_generation import ArtifactGenerationService
from .project_catalog import ProjectCatalog
from .project_state import ProjectStateService
from .runtime_contracts import AgentRuntime, EvidenceRuntime


class ChatService:
    def __init__(
        self,
        catalog: ProjectCatalog,
        project_state: ProjectStateService,
        notebooklm: EvidenceRuntime,
        agent_runtime: AgentRuntime,
        artifact_generation: ArtifactGenerationService,
    ):
        self.catalog = catalog
        self.project_state = project_state
        self.notebooklm = notebooklm
        self.agent_runtime = agent_runtime
        self.artifact_generation = artifact_generation

    async def _iterate_with_timeout(
        self,
        iterator,
        *,
        timeout_seconds: float,
        provider: str,
        timeout_message: str,
    ):
        while True:
            try:
                yield await asyncio.wait_for(iterator.__anext__(), timeout=timeout_seconds)
            except StopAsyncIteration:
                return
            except asyncio.TimeoutError as exc:
                raise ProviderIssue(provider=provider, message=timeout_message) from exc

    async def stream_turn(self, project_id: str, payload: ChatStreamRequest):
        project = self.catalog.get_project(project_id)
        if not project:
            raise LookupError("Project not found")

        stream_group_id = f"stream-{uuid.uuid4().hex[:10]}"
        self.catalog.create_message(
            project_id=project_id,
            role="user",
            content=payload.message,
            stream_group_id=stream_group_id,
        )

        state = self.project_state.get_project_state(project_id)
        sources = self.catalog.list_sources(project_id)
        selected_sources = [
            source for source in sources if source.id in payload.selected_source_ids
        ] or sources
        turn_input = AgentTurnInput(
            project=project,
            state=state,
            user_message=payload.message,
            selected_source_ids=payload.selected_source_ids,
            source_summaries=[source.parse_summary or source.name for source in selected_sources],
            evidence_summary="当前还没有调用 NotebookLM 证据工具。",
            evidence_citations=[],
            request_artifact_types=payload.request_artifact_types,
            recent_messages=self.catalog.list_recent_messages(project_id, limit=12),
        )

        assistant_saved = False
        final_assistant_message = ""
        final_citations: list[dict] = []

        try:
            async for event_type, value in self._iterate_with_timeout(
                self.agent_runtime.run_streaming_turn(turn_input),
                timeout_seconds=self.catalog.settings.claude_stream_timeout_seconds,
                provider="CLAUDE_AGENT_SDK",
                timeout_message="Claude 回复超时，当前轮对话已中止。请稍后重试。",
            ):
                if event_type == "final_message":
                    final_assistant_message = str(value.get("text") or "").strip()
                    raw_citations = value.get("citations")
                    final_citations = raw_citations if isinstance(raw_citations, list) else []
                    if final_assistant_message:
                        yield (
                            "message_chunk",
                            {
                                "text": final_assistant_message,
                                "replace": True,
                            },
                        )
                    if final_assistant_message and not assistant_saved:
                        self.catalog.create_message(
                            project_id=project_id,
                            role="assistant",
                            content=final_assistant_message,
                            source_refs=final_citations,
                            stream_group_id=stream_group_id,
                        )
                        assistant_saved = True
                    continue

                if event_type == "done":
                    continue

                yield (event_type, value)
        except ProviderIssue as exc:
            if final_assistant_message and not assistant_saved:
                self.catalog.create_message(
                    project_id=project_id,
                    role="assistant",
                    content=final_assistant_message,
                    source_refs=final_citations,
                    stream_group_id=stream_group_id,
                )
            yield (
                "error",
                {
                    "provider": exc.provider,
                    "message": exc.message,
                },
            )

        yield ("done", {"stream_group_id": stream_group_id})
