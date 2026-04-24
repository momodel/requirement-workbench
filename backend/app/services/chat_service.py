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
        evidence_runtime: EvidenceRuntime,
        agent_runtime: AgentRuntime,
        artifact_generation: ArtifactGenerationService,
    ):
        self.catalog = catalog
        self.project_state = project_state
        self.evidence_runtime = evidence_runtime
        self.agent_runtime = agent_runtime
        self.artifact_generation = artifact_generation

    async def _query_evidence_with_timeout(self, *args, **kwargs):
        return await asyncio.wait_for(
            asyncio.to_thread(self.evidence_runtime.query, *args, **kwargs),
            timeout=self.catalog.settings.evidence_query_timeout_seconds,
        )

    def _stream_timeout_for_phase(self, phase: str | None) -> float:
        base_timeout = self.catalog.settings.claude_stream_timeout_seconds
        if not phase:
            return base_timeout

        if phase == "tool_running:generate_artifact":
            return max(
                base_timeout,
                self.catalog.settings.claude_artifact_timeout_seconds + 15,
            )

        if phase == "tool_running:query_project_evidence":
            return max(
                base_timeout,
                self.catalog.settings.evidence_query_timeout_seconds + 10,
            )

        return base_timeout

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
            evidence_summary="当前还没有调用项目知识库检索工具。",
            evidence_citations=[],
            request_artifact_types=payload.request_artifact_types,
            recent_messages=self.catalog.list_recent_messages(project_id, limit=12),
        )

        assistant_saved = False
        final_assistant_message = ""
        final_citations: list[dict] = []
        current_timeout = self.catalog.settings.claude_stream_timeout_seconds

        try:
            iterator = self.agent_runtime.run_streaming_turn(turn_input)
            while True:
                try:
                    event_type, value = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=current_timeout,
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as exc:
                    raise ProviderIssue(
                        provider="CLAUDE_AGENT_SDK",
                        message="Claude 回复超时，当前轮对话已中止。请稍后重试。",
                    ) from exc

                if event_type == "assistant_status":
                    current_timeout = self._stream_timeout_for_phase(
                        str(value.get("phase") or "")
                    )
                else:
                    current_timeout = self.catalog.settings.claude_stream_timeout_seconds

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
