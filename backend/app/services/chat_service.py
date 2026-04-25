from __future__ import annotations

import asyncio
import json
import uuid

from ..models import AgentTurnInput, ChatStreamRequest, ProviderIssue, StateItem
from .artifact_generation import ArtifactGenerationService
from .llm_wiki_service import LLMWikiService
from .project_catalog import ProjectCatalog
from .project_state import ProjectStateService
from .runtime_contracts import AgentRuntime


class ChatService:
    STRUCTURED_TRIGGER_KEYWORDS = (
        "总结",
        "沉淀",
        "结论",
        "范围",
        "边界",
        "方案",
        "mvp",
        "MVP",
        "设计",
        "交付",
        "文档",
        "梳理",
        "收敛",
        "待确认",
        "确认项",
        "风险",
        "版本快照",
        "页面方案",
        "交互稿",
    )
    META_FOLLOW_UP_KEYWORDS = (
        "前一个问题",
        "上一个问题",
        "刚刚问",
        "刚才问",
        "刚才说",
        "上一条",
        "你前面",
        "你刚才",
        "重复一遍",
        "再说一遍",
        "聊天记录",
        "历史记录",
    )

    def __init__(
        self,
        catalog: ProjectCatalog,
        project_state: ProjectStateService,
        agent_runtime: AgentRuntime,
        artifact_generation: ArtifactGenerationService,
        knowledge_wiki: LLMWikiService | None = None,
    ):
        self.catalog = catalog
        self.project_state = project_state
        self.agent_runtime = agent_runtime
        self.artifact_generation = artifact_generation
        self.knowledge_wiki = knowledge_wiki

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
                raise ProviderIssue(
                    provider=provider,
                    message=timeout_message,
                ) from exc

    def _should_run_structured_turn(self, turn: AgentTurnInput) -> bool:
        if turn.request_artifact_types:
            return True

        message = turn.user_message.strip()
        if not message:
            return False

        lowered = message.lower()
        if any(keyword in message for keyword in self.META_FOLLOW_UP_KEYWORDS):
            return False

        state_item_count = (
            len(turn.state.current_understanding)
            + len(turn.state.pending_items)
            + len(turn.state.confirmed_items)
            + len(turn.state.conflict_items)
            + len(turn.state.mvp_items)
        )
        if state_item_count == 0:
            return True

        if any(keyword in message or keyword in lowered for keyword in self.STRUCTURED_TRIGGER_KEYWORDS):
            return True

        return False

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

        sources = self.catalog.list_sources(project_id)
        selected_sources = [
            source for source in sources if source.id in payload.selected_source_ids
        ] or sources
        wiki_context = ""
        if self.knowledge_wiki:
            self.knowledge_wiki.record_source_intake(project, sources)
            wiki_context = self.knowledge_wiki.build_context(project_id).summary

        yield (
            "assistant_status",
            {
                "phase": "source_scan",
                "label": f"正在整理项目资料与 {len(selected_sources)} 份候选资料",
            },
        )

        evidence_summary = wiki_context or "当前没有可用 LLM Wiki 知识库上下文。"
        evidence_citations = []
        yield ("citations", {"items": []})
        yield (
            "assistant_status",
            {
                "phase": "drafting",
                "label": "已读取 LLM Wiki 知识库上下文，正在组织回答",
            },
        )

        state = self.project_state.get_project_state(project_id)
        turn_input = AgentTurnInput(
            project=project,
            state=state,
            user_message=payload.message,
            selected_source_ids=payload.selected_source_ids,
            source_summaries=[source.parse_summary or source.name for source in selected_sources],
            evidence_summary=evidence_summary,
            evidence_citations=evidence_citations,
            request_artifact_types=payload.request_artifact_types,
            recent_messages=self.catalog.list_recent_messages(project_id, limit=12),
            wiki_context=wiki_context,
        )

        try:
            assistant_chunks: list[str] = []
            assistant_saved = False
            streamed_assistant_message = ""
            async for chunk in self._iterate_with_timeout(
                self.agent_runtime.stream_assistant_text(turn_input),
                timeout_seconds=self.catalog.settings.claude_stream_timeout_seconds,
                provider="CLAUDE_AGENT_SDK",
                timeout_message="Claude 回复超时，当前轮对话已中止。请稍后重试。",
            ):
                if not chunk:
                    continue
                assistant_chunks.append(chunk)
                yield ("message_chunk", {"text": chunk})

            streamed_assistant_message = "".join(assistant_chunks).strip()
            if streamed_assistant_message and not self._should_run_structured_turn(turn_input):
                self.catalog.create_message(
                    project_id=project_id,
                    role="assistant",
                    content=streamed_assistant_message,
                    source_refs=[],
                    stream_group_id=stream_group_id,
                )
                assistant_saved = True

            if not self._should_run_structured_turn(turn_input):
                yield ("done", {"stream_group_id": stream_group_id})
                return

            yield (
                "assistant_status",
                {
                    "phase": "state_patch",
                    "label": "正在写入沉淀与版本快照",
                },
            )

            async for event_type, value in self._iterate_with_timeout(
                self.agent_runtime.run_turn(
                    turn_input,
                    assistant_message=streamed_assistant_message or None,
                ),
                timeout_seconds=self.catalog.settings.claude_structured_timeout_seconds,
                provider="CLAUDE_AGENT_SDK",
                timeout_message="Claude 结构化沉淀生成超时，已终止本轮状态写入。请稍后重试。",
            ):
                if event_type == "message_chunk":
                    if not streamed_assistant_message and value:
                        fallback_text = str(value)
                        streamed_assistant_message = f"{streamed_assistant_message}{fallback_text}".strip()
                        yield ("message_chunk", {"text": fallback_text})
                    continue

                result = value
                final_assistant_message = streamed_assistant_message or result.assistant_message
                if not streamed_assistant_message and final_assistant_message:
                    yield ("message_chunk", {"text": final_assistant_message})
                if not assistant_saved:
                    self.catalog.create_message(
                        project_id=project_id,
                        role="assistant",
                        content=final_assistant_message,
                        source_refs=[citation.model_dump() for citation in result.citations],
                        stream_group_id=stream_group_id,
                    )
                    assistant_saved = True
                for category, items in result.state_updates.items():
                    if not items:
                        # 结构化输出里的空数组表示“本轮没有该类新增沉淀”，
                        # 不是要把历史沉淀整类清空。
                        continue
                    state_items = [
                        StateItem(
                            id=f"{category}-{uuid.uuid4().hex[:10]}",
                            title=item.title,
                            body=item.body,
                            status=item.status,
                            category=category,
                            source_ids=item.source_ids,
                        )
                        for item in items
                    ]
                    self.project_state.replace_category(
                        project_id=project_id,
                        category=category,
                        items=state_items,
                    )
                    yield (
                        f"{category}_patch",
                        {
                            "op": "replace",
                            "items": [item.model_dump() for item in state_items],
                        },
                    )

                if result.version_summary:
                    version = self.project_state.create_version(
                        project_id=project_id,
                        trigger_kind="analysis_checkpoint",
                        summary=result.version_summary,
                    )
                    yield (
                        "version_patch",
                        {"op": "upsert", "items": [version.model_dump()]},
                    )

                if self.knowledge_wiki:
                    self.knowledge_wiki.record_state_checkpoint(
                        project,
                        self.project_state.get_project_state(project_id),
                        trigger_kind="analysis_checkpoint",
                        summary=result.version_summary,
                    )

                artifact_types = list(dict.fromkeys(payload.request_artifact_types + result.request_artifacts))
                if artifact_types:
                    yield (
                        "assistant_status",
                        {
                            "phase": "artifact_generation",
                            "label": "正在生成交付物预览",
                        },
                    )
                    state_after = self.project_state.get_project_state(project_id)
                    created_artifacts = []
                    for artifact_type in artifact_types:
                        created_artifacts.append(
                            await self.artifact_generation.generate_from_model(
                                project=project,
                                state=state_after,
                                artifact_type=artifact_type,
                                agent_runtime=self.agent_runtime,
                            )
                        )
                    yield (
                        "artifact_patch",
                        {
                            "op": "upsert",
                            "items": [artifact.model_dump() for artifact in created_artifacts],
                        },
                    )
        except ProviderIssue as exc:
            if streamed_assistant_message and not assistant_saved:
                self.catalog.create_message(
                    project_id=project_id,
                    role="assistant",
                    content=streamed_assistant_message,
                    source_refs=[],
                    stream_group_id=stream_group_id,
                )
            if not streamed_assistant_message:
                yield (
                    "error",
                    {
                        "provider": exc.provider,
                        "message": exc.message,
                    },
                )

        yield ("done", {"stream_group_id": stream_group_id})
