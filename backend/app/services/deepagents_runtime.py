from __future__ import annotations

import asyncio
import json
import os
import uuid
from typing import Any, AsyncIterator

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from deepagents import create_deep_agent

from .agent_runtime import (
    ClaudeAgentRuntime,
    _coerce_html_artifact_payload,
    _coerce_json_payload,
    _normalize_generated_artifact_output_payload,
    _state_tool_categories,
)
from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    AgentTurnInput,
    ArtifactRecord,
    ArtifactType,
    GeneratedArtifactOutput,
    ProjectState,
    ProjectSummary,
    ProviderIssue,
    ProviderReadiness,
    SourceUpsert,
    StateCategory,
    StateItem,
)

PROVIDER = "DEEP_AGENTS"


def _extract_text(content: Any) -> str:
    """Extract plain text from a LangChain message content (str or Anthropic-style block list)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


# --------------------------------------------------------------------------- #
# Tool argument schemas (Pydantic)                                            #
# --------------------------------------------------------------------------- #
class StateItemInput(BaseModel):
    title: str
    body: str
    source_ids: list[str] = Field(default_factory=list)
    status: str | None = None


class UpdateProjectStateArgs(BaseModel):
    current_understanding: list[StateItemInput] | None = None
    pending_items: list[StateItemInput] | None = None
    confirmed_items: list[StateItemInput] | None = None
    conflict_items: list[StateItemInput] | None = None
    mvp_items: list[StateItemInput] | None = None


class QueryEvidenceArgs(BaseModel):
    question: str
    selected_source_ids: list[str] | None = None


class CreateSnapshotArgs(BaseModel):
    summary: str
    trigger_kind: str = "analysis_checkpoint"


class GenerateArtifactArgs(BaseModel):
    artifact_type: str
    title: str
    summary: str
    focus: str | None = None
    working_notes: str | None = None


class GenerateMockupArgs(BaseModel):
    title: str
    summary: str
    prompt: str
    size: str | None = None
    resolution: str | None = None
    n: int | None = None
    quality: str | None = None
    style: str | None = None
    reference_image_urls: list[str] | None = None
    extra_parameters: dict[str, Any] | None = None


class ReadWikiPageArgs(BaseModel):
    slug: str


_TOOL_PHASES = {
    "query_project_evidence": "tool_running:query_project_evidence",
    "update_project_state": "tool_running:update_project_state",
    "create_version_snapshot": "tool_running:create_version_snapshot",
    "generate_artifact": "tool_running:generate_artifact",
    "generate_visual_mockup": "tool_running:generate_visual_mockup",
    "wiki_list_pages": "tool_running:wiki_list_pages",
    "wiki_read_page": "tool_running:wiki_read_page",
}


class DeepAgentsRuntime(ClaudeAgentRuntime):
    """Agent runtime backed by Deep Agents Harness (LangGraph) + LangChain chat model.

    Replaces claude-agent-sdk. The conversational agent loop runs through
    `deepagents.create_deep_agent`; artifact content generation uses a Pydantic AI
    Agent bridged to the same LangChain chat model via FunctionModel.
    """

    def __init__(
        self,
        settings: AppSettings = DEFAULT_SETTINGS,
        evidence_runtime=None,
    ) -> None:
        super().__init__(settings, evidence_runtime=evidence_runtime)
        self._model: ChatAnthropic | None = None

    # ------------------------------------------------------------------ #
    # Model + readiness                                                  #
    # ------------------------------------------------------------------ #
    def _resolve_model_config(self) -> tuple[str, str, str | None]:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        base_url = os.environ.get("ANTHROPIC_BASE_URL") or None
        model_name = self.settings.claude_model or os.environ.get("CLAUDE_MODEL", "")
        return api_key, base_url, model_name

    def _get_model(self) -> ChatAnthropic:
        if self._model is None:
            api_key, base_url, model_name = self._resolve_model_config()
            if not api_key:
                raise ProviderIssue(provider=PROVIDER, message="未配置 ANTHROPIC_API_KEY。")
            if not model_name:
                raise ProviderIssue(provider=PROVIDER, message="未配置 CLAUDE_MODEL。")
            self._model = ChatAnthropic(
                model=model_name,
                api_key=api_key,
                base_url=base_url,
                timeout=self.settings.claude_stream_timeout_seconds or 120,
                max_retries=2,
            )
        return self._model

    def ensure_available(self) -> None:
        api_key, _base_url, model_name = self._resolve_model_config()
        if not api_key:
            raise ProviderIssue(provider=PROVIDER, message="未配置 ANTHROPIC_API_KEY。")
        if not model_name:
            raise ProviderIssue(
                provider=PROVIDER,
                message="未配置 CLAUDE_MODEL，主链路无法启动。",
            )

    def resolved_cli_path(self) -> str | None:  # no CLI in this runtime
        return None

    def get_readiness(self) -> ProviderReadiness:
        try:
            self.ensure_available()
        except ProviderIssue as exc:
            return ProviderReadiness(
                provider=PROVIDER,
                status="not_configured",
                summary="Deep Agents 运行时还没有准备好。",
                detail=exc.message,
                action_label="配置 Claude 模型",
            )
        _api_key, base_url, model_name = self._resolve_model_config()
        detail = f"当前模型：{model_name}"
        if base_url:
            detail += f"；base_url：{base_url}"
        return ProviderReadiness(
            provider=PROVIDER,
            status="ready",
            summary="Deep Agents 运行时已就绪，且已锁定模型配置。",
            detail=detail,
        )

    # ------------------------------------------------------------------ #
    # Tool factories (LangChain StructuredTool)                          #
    # ------------------------------------------------------------------ #
    def _build_turn_tools(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        default_selected_source_ids: list[str],
        evidence_results: list[dict],
        applied_state_updates: dict[StateCategory, list[StateItem]],
        generated_artifacts: list[ArtifactRecord],
        generated_versions: list[StateItem],
        generated_image_tasks: list[asyncio.Task],
        wiki_reads: list[dict],
    ) -> list[StructuredTool]:
        tools: list[StructuredTool] = []

        async def query_project_evidence(question: str, selected_source_ids: list[str] | None = None) -> str:
            try:
                question = (question or "").strip()
                if not question:
                    raise ValueError("question 不能为空。")
                ids = selected_source_ids or default_selected_source_ids or None
                try:
                    evidence = await asyncio.wait_for(
                        asyncio.to_thread(self.evidence_runtime.query, project.id, question, selected_source_ids=ids),
                        timeout=self.settings.evidence_query_timeout_seconds,
                    )
                except asyncio.TimeoutError as exc:
                    raise ProviderIssue(provider="QDRANT_LLAMA_INDEX", message="项目知识库检索超时，当前证据工具暂不可用。") from exc
                payload = {
                    "summary": evidence.summary,
                    "citations": [c.model_dump() for c in evidence.citations],
                    "source_refs": [c.source_id for c in evidence.citations if c.source_id],
                    "coverage_hint": "grounded" if evidence.citations else "ungrounded",
                }
                evidence_results.append(payload)
                return json.dumps(payload, ensure_ascii=False)
            except Exception as exc:
                return f"ERROR: {exc.message if isinstance(exc, ProviderIssue) else exc}"

        tools.append(StructuredTool.from_function(query_project_evidence, name="query_project_evidence", description="基于当前项目知识库查询 grounded 证据和 citations。", args_schema=QueryEvidenceArgs))

        async def update_project_state(
            current_understanding: list[StateItemInput] | None = None,
            pending_items: list[StateItemInput] | None = None,
            confirmed_items: list[StateItemInput] | None = None,
            conflict_items: list[StateItemInput] | None = None,
            mvp_items: list[StateItemInput] | None = None,
        ) -> str:
            try:
                allowed_source_ids = {s.id for s in self.catalog.list_sources(project.id)}
                applied: dict[str, int] = {}
                buckets = {
                    "current_understanding": current_understanding,
                    "pending_items": pending_items,
                    "confirmed_items": confirmed_items,
                    "conflict_items": conflict_items,
                    "mvp_items": mvp_items,
                }
                for category, raw_items in buckets.items():
                    if not raw_items:
                        continue
                    normalized = [SourceUpsert.model_validate(item.model_dump()) for item in raw_items]
                    if category == "confirmed_items":
                        for item in normalized:
                            if not item.source_ids:
                                raise ValueError("confirmed_items 必须带 source_ids；citation 只能来自 query_project_evidence 真实返回的 source。")
                            unknown = [sid for sid in item.source_ids if sid not in allowed_source_ids]
                            if unknown:
                                raise ValueError(f"confirmed_items 中包含未知 source_id={unknown}；wiki slug 不是 source 引用。")
                    state_items = [
                        StateItem(id=f"{category}-{uuid.uuid4().hex[:10]}", title=i.title, body=i.body, status=i.status, category=category, source_ids=i.source_ids)
                        for i in normalized
                    ]
                    self.project_state_service.append_category(project_id=project.id, category=category, items=state_items)
                    applied_state_updates[category] = state_items
                    applied[category] = len(state_items)
                return json.dumps({"project_id": project.id, "applied_categories": applied}, ensure_ascii=False)
            except Exception as exc:
                return f"ERROR: {exc}"

        tools.append(StructuredTool.from_function(update_project_state, name="update_project_state", description="把本轮确认过的项目沉淀真实写入项目状态。只写本轮增量。", args_schema=UpdateProjectStateArgs))

        async def create_version_snapshot(summary: str, trigger_kind: str = "analysis_checkpoint") -> str:
            try:
                version = self.project_state_service.create_version(project_id=project.id, trigger_kind=trigger_kind, summary=summary.strip())
                generated_versions.append(version)
                return json.dumps({"project_id": project.id, "version_id": version.id, "title": version.title}, ensure_ascii=False)
            except Exception as exc:
                return f"ERROR: {exc}"

        tools.append(StructuredTool.from_function(create_version_snapshot, name="create_version_snapshot", description="在关键轮次生成一个项目版本快照。", args_schema=CreateSnapshotArgs))

        async def generate_artifact_tool(artifact_type: str, title: str, summary: str, focus: str | None = None, working_notes: str | None = None) -> str:
            try:
                atype = self._normalize_artifact_type(artifact_type)
                title = title.strip() or {"document": "需求文档稿", "page_solution": "页面方案原型", "interaction_flow": "交互稿原型"}[atype]
                summary = summary.strip() or "交付物正在生成中。"
                content_format = "markdown" if atype == "document" else "html"
                artifact = self.artifact_generation_service.catalog.save_artifact(
                    project_id=project.id, artifact_type=atype, title=title, summary=summary,
                    status="generating", content_format=content_format, storage_path=None, body=None,
                    metadata={"generator": "deepagents-async-job", "focus": (focus or "").strip() or None, "working_notes": (working_notes or "").strip() or None},
                )
                generated_artifacts.append(artifact)
                self._schedule_artifact_generation_job(
                    project=project, state=state, artifact_type=atype, artifact_id=artifact.id,
                    title=artifact.title, summary=artifact.summary,
                    additional_instruction=(focus or working_notes or "").strip() or None,
                )
                return json.dumps({"artifact_id": artifact.id, "artifact_type": artifact.artifact_type, "title": artifact.title, "summary": artifact.summary, "status": artifact.status}, ensure_ascii=False)
            except Exception as exc:
                return f"ERROR: {exc}"

        tools.append(StructuredTool.from_function(generate_artifact_tool, name="generate_artifact", description="登记一个后台交付物生成任务并立即返回生成中记录；不要在参数里生成完整正文或 HTML。", args_schema=GenerateArtifactArgs))

        async def generate_visual_mockup(title: str, summary: str, prompt: str, size: str | None = None, resolution: str | None = None, n: int | None = None, quality: str | None = None, style: str | None = None, reference_image_urls: list[str] | None = None, extra_parameters: dict[str, Any] | None = None) -> str:
            image_id = f"image-{uuid.uuid4().hex[:10]}"
            title = title.strip() or "交互视觉稿"
            summary = summary.strip() or "视觉稿正在生成中。"

            async def complete_image_job() -> dict:
                result = await self.image_generation_service.generate(
                    project_id=project.id, artifact_id=image_id, title=title, summary=summary, prompt=prompt,
                    size=(size or "").strip() or None, resolution=(resolution or "").strip() or None,
                    n=n, quality=(quality or "").strip() or None, style=(style or "").strip() or None,
                    reference_image_urls=self._normalize_reference_image_urls(reference_image_urls or []),
                    extra_parameters=extra_parameters if isinstance(extra_parameters, dict) else None,
                    output_dir=self.settings.projects_dir / project.id / "chat-images" / image_id,
                )
                return {"id": image_id, "title": result.title, "summary": result.summary, "url": f"/api/projects/{project.id}/chat-images/{image_id}", "content_type": result.content_type, "prompt": result.prompt, "provider_url": result.provider_url, "metadata": result.metadata}

            try:
                task = asyncio.create_task(complete_image_job())
                generated_image_tasks.append(task)
                return json.dumps({"image_id": image_id, "title": title, "summary": summary, "status": "generating"}, ensure_ascii=False)
            except Exception as exc:
                return f"ERROR: {exc}"

        tools.append(StructuredTool.from_function(generate_visual_mockup, name="generate_visual_mockup", description="调用图像模型生成页面/交互视觉稿。", args_schema=GenerateMockupArgs))

        async def wiki_list_pages() -> str:
            if self.wiki_runtime is None:
                return "ERROR: wiki_runtime 未注入。"
            try:
                pages = await asyncio.to_thread(self.wiki_runtime.list_pages, project.id)
            except Exception as exc:
                return f"ERROR: {exc}"
            payload = {"pages": [p.model_dump() for p in pages]}
            wiki_reads.append({"op": "list", "page_count": len(pages)})
            return json.dumps(payload, ensure_ascii=False)

        tools.append(StructuredTool.from_function(wiki_list_pages, name="wiki_list_pages", description="列出当前项目 LLM Wiki 中所有页面的元信息（不含正文）。", args_schema=type("_Empty", (BaseModel,), {})))

        async def wiki_read_page(slug: str) -> str:
            if self.wiki_runtime is None:
                return "ERROR: wiki_runtime 未注入。"
            slug = (slug or "").strip()
            if not slug:
                return "ERROR: slug 不能为空。"
            try:
                page = await asyncio.to_thread(self.wiki_runtime.read_page, project.id, slug)
            except Exception as exc:
                return f"ERROR: {exc.message if isinstance(exc, ProviderIssue) else exc}"
            wiki_reads.append({"op": "read", "slug": slug, "title": page.title})
            return json.dumps(page.model_dump(), ensure_ascii=False)

        tools.append(StructuredTool.from_function(wiki_read_page, name="wiki_read_page", description="读取当前项目 LLM Wiki 中某个页面的正文（仅补充上下文，不可作为 citation）。", args_schema=ReadWikiPageArgs))

        return tools

    # ------------------------------------------------------------------ #
    # Main streaming turn (deepagents loop)                              #
    # ------------------------------------------------------------------ #
    async def run_streaming_turn(self, turn: AgentTurnInput) -> AsyncIterator[tuple[str, dict]]:
        self.ensure_available()
        model = self._get_model()

        applied_state_updates: dict[StateCategory, list[StateItem]] = {}
        evidence_results: list[dict] = []
        generated_artifacts: list[ArtifactRecord] = []
        generated_versions: list[StateItem] = []
        generated_image_tasks: list[asyncio.Task] = []
        wiki_reads: list[dict] = []

        emitted_text = ""
        latest_assistant_text = ""

        tools = self._build_turn_tools(
            project=turn.project, state=turn.state,
            default_selected_source_ids=turn.selected_source_ids,
            evidence_results=evidence_results, applied_state_updates=applied_state_updates,
            generated_artifacts=generated_artifacts, generated_versions=generated_versions,
            generated_image_tasks=generated_image_tasks, wiki_reads=wiki_reads,
        )

        agent = create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=self._system_prompt(),
        )

        yield ("assistant_status", {"phase": "agent_started", "label": "已接收问题，正在启动分析"})

        prompt_text = self._build_loop_prompt(turn)
        image_blocks = self._user_image_blocks(turn.user_image_refs)
        if image_blocks:
            content = [{"type": "image", "source": b} for b in image_blocks] + [{"type": "text", "text": prompt_text}]
            input_messages: Any = [HumanMessage(content=content)]
        else:
            input_messages = prompt_text

        seen_tool_running: set[str] = set()
        try:
            async for mode, chunk in agent.astream(
                {"messages": input_messages},
                stream_mode=["messages", "updates"],
                config={"recursion_limit": max(self.settings.claude_max_turns * 4, 40)},
            ):
                if mode == "messages":
                    try:
                        msg, _meta = chunk  # type: ignore[misc]
                    except Exception:
                        continue
                    ctype = type(msg).__name__
                    if ctype not in ("AIMessageChunk", "AIMessage"):
                        continue
                    txt = _extract_text(getattr(msg, "content", None))
                    if txt:
                        emitted_text += txt
                        yield ("message_chunk", {"text": txt})
                    for tc in (getattr(msg, "tool_call_chunks", None) or []):
                        name = tc.get("name") if isinstance(tc, dict) else None
                        if name and name not in seen_tool_running:
                            seen_tool_running.add(name)
                            phase = _TOOL_PHASES.get(name)
                            if phase:
                                yield ("assistant_status", {"phase": phase, "label": f"正在执行 {name}"})
                elif mode == "updates":
                    for _node, upd in (chunk or {}).items():
                        for m in (upd or {}).get("messages", []):
                            if isinstance(m, AIMessage):
                                full = _extract_text(getattr(m, "content", ""))
                                if full.strip():
                                    latest_assistant_text = full.strip()
        except Exception as exc:
            raise ProviderIssue(provider=PROVIDER, message=f"Deep Agents 运行失败：{exc}") from exc

        final_assistant_message = latest_assistant_text or emitted_text.strip()

        latest_evidence = evidence_results[-1] if evidence_results else None
        citations = latest_evidence.get("citations", []) if latest_evidence else []
        if latest_evidence:
            yield ("assistant_status", {"phase": "tool_completed:query_project_evidence", "label": "已拿到资料证据"})
        if citations:
            yield ("citations", {"items": citations})

        if applied_state_updates:
            yield ("assistant_status", {"phase": "tool_completed:update_project_state", "label": "已写入本轮沉淀"})
            for category, items in applied_state_updates.items():
                if not items:
                    continue
                yield (f"{category}_patch", {"op": "upsert", "items": [item.model_dump() for item in items]})

        explicit_versions = [v for v in generated_versions if v.title != "artifact_generated"]
        if explicit_versions:
            yield ("assistant_status", {"phase": "tool_completed:create_version_snapshot", "label": "已生成版本快照"})
        if generated_versions:
            yield ("version_patch", {"op": "upsert", "items": [v.model_dump() for v in generated_versions]})

        if wiki_reads:
            yield ("wiki_reads", {"items": list(wiki_reads)})

        if generated_artifacts:
            yield ("assistant_status", {"phase": "tool_completed:generate_artifact", "label": "已生成交付物预览"})
            yield ("artifact_patch", {"op": "upsert", "items": [a.model_dump() for a in generated_artifacts]})

        if generated_image_tasks:
            yield ("assistant_status", {"phase": "tool_running:generate_visual_mockup", "label": "正在生成视觉稿"})
            try:
                generated_images = await asyncio.wait_for(
                    asyncio.gather(*generated_image_tasks),
                    timeout=self.settings.image_generation_timeout_seconds + 15,
                )
            except Exception as exc:
                raise ProviderIssue(provider="APIMART_IMAGE", message=str(exc) or "视觉稿生成失败。") from exc
            yield ("assistant_status", {"phase": "tool_completed:generate_visual_mockup", "label": "视觉稿已生成"})
            for image in generated_images:
                yield ("image_result", image)

        yield ("final_message", {"text": final_assistant_message, "citations": citations})
        yield ("assistant_status", {"phase": "agent_completed", "label": "本轮分析已完成"})

    # ------------------------------------------------------------------ #
    # Artifact generation (Pydantic AI via FunctionModel bridge)         #
    # ------------------------------------------------------------------ #
    async def generate_artifact(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        additional_instruction: str | None = None,
    ) -> GeneratedArtifactOutput:
        self.ensure_available()
        model = self._get_model()
        prompt = self._artifact_prompt(project=project, state=state, artifact_type=artifact_type, additional_instruction=additional_instruction)

        try:
            if artifact_type == "document":
                # Structured artifact via Pydantic AI Agent (output_type pipeline) bridged
                # to the LangChain chat model through a FunctionModel.
                result_obj = await self._pydantic_ai_structured_artifact(prompt)
                return GeneratedArtifactOutput.model_validate(_normalize_generated_artifact_output_payload(result_obj))

            # HTML artifacts: up to 2 attempts, parse text output.
            max_attempts = 2
            parse_error: Exception | None = None
            for attempt in range(max_attempts):
                attempt_prompt = prompt
                if attempt > 0:
                    attempt_prompt = (
                        f"{prompt}\n\n补充要求：你上一轮没有按指定格式输出。"
                        "这一轮必须严格返回 TITLE、SUMMARY、HTML 三段，除此之外不要输出任何其他文字。"
                    )
                raw_text = await self._invoke_text(model, attempt_prompt)
                try:
                    return GeneratedArtifactOutput.model_validate(_coerce_html_artifact_payload(raw_text))
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    parse_error = exc
            raise parse_error or ProviderIssue(provider=PROVIDER, message="未能解析 HTML artifact 输出。")
        except ProviderIssue:
            raise
        except Exception as exc:
            raise ProviderIssue(provider=PROVIDER, message=f"交付物生成失败：{exc}") from exc

    async def _invoke_text(self, model: ChatAnthropic, prompt: str) -> str:
        resp = await model.ainvoke(prompt)
        return _extract_text(getattr(resp, "content", ""))


    async def _pydantic_ai_structured_artifact(self, prompt: str) -> dict:
        """Generate a structured artifact via a Pydantic AI Agent bridged to LangChain.

        Uses Pydantic AI's Agent + output_type pipeline; the model call goes through
        LangChain ChatAnthropic via a FunctionModel, avoiding the anthropic SDK version
        conflict that blocks pydantic-ai's native AnthropicModel. Handles the gateway
        returning None from with_structured_output by falling back to text + JSON.
        """
        import json as _json
        from pydantic_ai import Agent
        from pydantic_ai.models.function import FunctionModel
        from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
        from langchain_core.messages import SystemMessage

        lc_model = self._get_model()

        async def bridge_function(messages, info):  # type: ignore[no-untyped-def]
            lc_messages: list[Any] = []
            for m in messages:
                if getattr(m, "kind", None) == "request":
                    for part in getattr(m, "parts", []):
                        pkind = getattr(part, "part_kind", None)
                        if pkind == "system-prompt":
                            lc_messages.append(SystemMessage(content=part.content))
                        elif pkind == "user-prompt":
                            lc_messages.append(HumanMessage(content=part.content))
            out_tools = getattr(info, "output_tools", []) or []
            if out_tools:
                tool = out_tools[0]
                data = None
                try:
                    data = await lc_model.with_structured_output(GeneratedArtifactOutput).ainvoke(lc_messages)
                except Exception:
                    data = None
                if data is None:
                    raw = await lc_model.ainvoke(lc_messages)
                    text = _extract_text(getattr(raw, "content", ""))
                    try:
                        payload = _coerce_json_payload(text)
                    except Exception:
                        payload = {"title": "未解析的交付物", "body": text[:500]}
                else:
                    payload = data.model_dump() if hasattr(data, "model_dump") else dict(data)
                return ModelResponse(parts=[ToolCallPart(tool_name=tool.name, args=payload, tool_call_id="deepagents-bridge")])
            raw = await lc_model.ainvoke(lc_messages)
            return ModelResponse(parts=[TextPart(content=_extract_text(getattr(raw, "content", "")))])

        model_name = self._resolve_model_config()[2] or "deepagents-bridge"
        agent = Agent(
            model=FunctionModel(function=bridge_function, model_name=model_name),
            system_prompt="你是客户需求转译台的交付物生成智能体。只输出结构化内容。",
            retries=1,
        )
        result = await agent.run(prompt, output_type=GeneratedArtifactOutput)
        data = result.output
        if isinstance(data, GeneratedArtifactOutput):
            return data.model_dump()
        if isinstance(data, dict):
            return data
        return {"content": str(data)}
