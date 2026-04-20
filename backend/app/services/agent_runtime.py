from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    CLINotFoundError,
    ClaudeAgentOptions,
    ResultMessage,
    StreamEvent,
    TextBlock,
    query,
)
from pydantic import ValidationError

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    AgentStructuredOutput,
    ArtifactType,
    AgentTurnInput,
    AgentTurnResult,
    ChatCitation,
    GeneratedArtifactOutput,
    ProjectState,
    ProjectSummary,
    ProviderReadiness,
    ProviderIssue,
    SourceUpsert,
)


def _read_skill(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _output_schema() -> dict:
    item_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"},
            "source_ids": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string"},
        },
        "required": ["title", "body"],
        "additionalProperties": False,
    }
    citation_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "snippet": {"type": ["string", "null"]},
            "source_id": {"type": ["string", "null"]},
        },
        "required": ["title", "snippet", "source_id"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "assistant_message": {"type": "string"},
            "citations": {"type": "array", "items": citation_schema},
            "current_understanding": {"type": "array", "items": item_schema},
            "pending_items": {"type": "array", "items": item_schema},
            "confirmed_items": {"type": "array", "items": item_schema},
            "conflict_items": {"type": "array", "items": item_schema},
            "mvp_items": {"type": "array", "items": item_schema},
            "version_summary": {"type": ["string", "null"]},
            "request_artifacts": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["document", "page_solution", "interaction_flow"],
                },
            },
        },
        "required": [
            "assistant_message",
            "citations",
            "current_understanding",
            "pending_items",
            "confirmed_items",
            "conflict_items",
            "mvp_items",
            "version_summary",
            "request_artifacts",
        ],
        "additionalProperties": False,
    }


def _artifact_output_schema(artifact_type: ArtifactType) -> dict:
    properties: dict[str, dict] = {
        "title": {"type": "string"},
        "summary": {"type": "string"},
    }
    required = ["title", "summary"]

    if artifact_type == "document":
        properties["body"] = {"type": "string"}
        required.append("body")
    else:
        properties["html"] = {"type": "string"}
        required.append("html")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _coerce_json_payload(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
        return json.loads(text)

    fenced_match = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.I)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    json_match = re.search(r"(\{[\s\S]*\})", text)
    if json_match:
        return json.loads(json_match.group(1))

    return json.loads(text)


def _coerce_request_artifacts(value) -> list[str]:
    if value in (None, False, ""):
        return []
    if value is True:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return []


def _coerce_citations(value) -> list[dict]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        return []

    normalized: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(
                {
                    "title": str(item.get("title") or item.get("source") or "引用"),
                    "snippet": item.get("snippet") or item.get("quote") or item.get("cited_text"),
                    "source_id": item.get("source_id"),
                }
            )
        elif isinstance(item, str):
            normalized.append({"title": item, "snippet": None, "source_id": None})
    return normalized


def _split_title_body(text: str, fallback_title: str) -> tuple[str, str]:
    cleaned = " ".join(text.split()).strip()
    for separator in ("：", ":"):
        if separator in cleaned:
            title, body = cleaned.split(separator, 1)
            if title.strip() and body.strip():
                return title.strip(), body.strip()
    return fallback_title, cleaned


def _coerce_state_items(value, fallback_title: str) -> list[dict]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        value = [value]

    normalized: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            raw_title = (
                item.get("title")
                or item.get("question")
                or item.get("item")
                or item.get("content")
                or item.get("description")
                or item.get("name")
                or item.get("summary")
                or item.get("id")
                or fallback_title
            )
            body = item.get("body") or item.get("detail") or item.get("answer")
            title = str(raw_title)
            derived_body = None
            if not body:
                split_title, split_body = _split_title_body(title, title)
                if split_title != title or split_body != title:
                    title = split_title
                    derived_body = split_body
            if not body:
                fragments = []
                for key in (
                    "description",
                    "item",
                    "content",
                    "question",
                    "source",
                    "reason",
                    "impact",
                    "answer_needed",
                    "notes",
                    "evidence",
                    "confidence",
                    "resolution",
                ):
                    fragment = item.get(key)
                    if fragment and fragment != title:
                        fragments.append(f"{key}: {fragment}")
                body = "；".join(
                    [part for part in [derived_body, *fragments] if part]
                ) or str(title)

            source_ids = item.get("source_ids") or item.get("related_sources") or []
            if not isinstance(source_ids, list):
                source_ids = [str(source_ids)]
            normalized.append(
                {
                    "title": str(title),
                    "body": str(body),
                    "source_ids": [str(source_id) for source_id in source_ids if source_id],
                    "status": str(item.get("status") or "active"),
                }
            )
            continue

        raw_text = str(item)
        title, body = _split_title_body(raw_text, raw_text)
        normalized.append(
            {
                "title": title,
                "body": body,
                "source_ids": [],
                "status": "active",
            }
        )

    return normalized


def _clean_artifact_body(text: str, max_length: int = 140) -> str:
    cleaned = " ".join(str(text).split()).strip()
    cleaned = re.sub(
        r"\b(content|impact|source|reason|notes|evidence|confidence|resolution|answer_needed)\s*:\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"(；\s*){2,}", "；", cleaned).strip("； ").strip()
    if len(cleaned) > max_length:
        cleaned = f"{cleaned[:max_length].rstrip()}..."
    return cleaned


def _format_artifact_items(label: str, items: list[dict], limit: int = 4) -> str:
    if not items:
        return ""

    lines = [f"{label}："]
    for item in items[:limit]:
        payload = item.model_dump() if hasattr(item, "model_dump") else item
        title = " ".join(str(payload.get("title", "")).split()).strip() or label
        body = _clean_artifact_body(payload.get("body", ""))
        lines.append(f"- {title}：{body}" if body and body != title else f"- {title}")
    return "\n".join(lines)


def _normalize_structured_output_payload(raw) -> dict:
    if not isinstance(raw, dict):
        return raw

    normalized = dict(raw)
    state_patch = raw.get("state_patch") if isinstance(raw.get("state_patch"), dict) else {}

    def state_value(key: str):
        if key in raw and raw.get(key) not in (None, ""):
            return raw.get(key)
        return state_patch.get(key)

    normalized["citations"] = _coerce_citations(raw.get("citations"))
    normalized["current_understanding"] = _coerce_state_items(
        state_value("current_understanding"),
        "当前理解",
    )
    normalized["pending_items"] = _coerce_state_items(state_value("pending_items"), "待确认项")
    if not normalized["pending_items"]:
        normalized["pending_items"] = _coerce_state_items(
            raw.get("follow_up_questions"),
            "待确认项",
        )
    normalized["confirmed_items"] = _coerce_state_items(state_value("confirmed_items"), "已确认项")
    normalized["conflict_items"] = _coerce_state_items(state_value("conflict_items"), "冲突项")
    normalized["mvp_items"] = _coerce_state_items(state_value("mvp_items"), "MVP 项")
    normalized["request_artifacts"] = _coerce_request_artifacts(raw.get("request_artifacts"))
    return normalized


def _normalize_generated_artifact_output_payload(raw) -> dict:
    if not isinstance(raw, dict):
        return raw

    normalized = dict(raw)
    for key in ("content", "data", "result", "artifact"):
        nested = normalized.get(key)
        if isinstance(nested, dict):
            merged = dict(nested)
            for outer_key, outer_value in normalized.items():
                if outer_key not in {"content", "data", "result", "artifact"} and outer_key not in merged:
                    merged[outer_key] = outer_value
            normalized = merged
            break

    if "html" not in normalized and isinstance(normalized.get("content"), str):
        normalized["html"] = normalized["content"]
    if "body" not in normalized and isinstance(normalized.get("markdown"), str):
        normalized["body"] = normalized["markdown"]

    return normalized


def _coerce_html_artifact_payload(raw: str) -> dict:
    text = raw.strip()
    marker_match = re.search(
        r"TITLE:\s*(?P<title>[^\n]+)\nSUMMARY:\s*(?P<summary>[^\n]+)\nHTML:\s*\n(?P<html>[\s\S]+)",
        text,
        re.I,
    )
    if marker_match:
        return {
            "title": marker_match.group("title").strip(),
            "summary": marker_match.group("summary").strip(),
            "html": marker_match.group("html").strip(),
        }

    def extract_loose_string_field(names: tuple[str, ...]) -> str | None:
        for name in names:
            match = re.search(rf'["\']?{re.escape(name)}["\']?\s*:\s*', text, re.I)
            if not match:
                continue

            idx = match.end()
            while idx < len(text) and text[idx].isspace():
                idx += 1
            if idx >= len(text) or text[idx] not in {'"', "'"}:
                continue

            quote = text[idx]
            idx += 1
            parts: list[str] = []
            escaped = False
            while idx < len(text):
                char = text[idx]
                if escaped:
                    if char == "n":
                        parts.append("\n")
                    elif char == "t":
                        parts.append("\t")
                    else:
                        parts.append(char)
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    return "".join(parts)
                else:
                    parts.append(char)
                idx += 1
        return None

    loose_title = extract_loose_string_field(("title",))
    loose_summary = extract_loose_string_field(("summary",))
    loose_html = extract_loose_string_field(("html", "content"))
    if loose_title and loose_summary and loose_html:
        return {
            "title": loose_title.strip(),
            "summary": loose_summary.strip(),
            "html": loose_html.strip(),
        }

    parsed = _normalize_generated_artifact_output_payload(_coerce_json_payload(text))
    if "html" not in parsed and isinstance(parsed.get("content"), str):
        parsed["html"] = parsed["content"]
    return parsed


class ClaudeAgentRuntime:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings
        root = settings.root_dir
        self.methodology_skill = _read_skill(
            root / "backend" / ".claude" / "skills" / "requirement-analysis-methodology" / "SKILL.md"
        )
        self.evidence_skill = _read_skill(
            root / "backend" / ".claude" / "skills" / "notebooklm-evidence-workflow" / "SKILL.md"
        )

    def _methodology_execution_notes(self) -> str:
        return """
方法论执行提醒：
1. 可以在内部使用 BABOK、JTBD、Event Storming 三种镜头，但不要把 BABOK、JTBD、Event Storming 这些术语直接写给用户。
2. 如果当前主要任务是 intake 或澄清，优先按 BABOK 视角抽取目标、干系人、范围、约束、风险，优先写入 current_understanding 或 pending_items。
3. 如果当前主要任务是判断真实需求，优先按 JTBD 视角抽取用户角色、任务、期望结果、当前阻力，不要把页面诉求直接当成 job。
4. 如果当前主要任务是还原流程和系统边界，优先按 Event Storming 视角抽取关键事件、参与对象、系统边界、异常分支，优先写入 current_understanding、conflict_items 或 mvp_items。
5. 如果三种镜头得出的结论互相冲突，先保留冲突或待确认项，不要抢着塞进 confirmed_items。
        """.strip()

    def _artifact_generation_notes(self) -> str:
        return """
交付物生成提醒：
1. 只基于当前已沉淀的项目理解生成，不要把状态对象原样搬进结果。
2. 优先把目标、范围、关键对象、核心流程和待确认边界翻译成用户能直接看的交付物。
3. 信息不够时可以明确写“待确认”或“暂定”，不要用空壳页面或空洞流程凑数。
4. 页面方案强调信息结构和页面分工，交互稿强调步骤、动作和页面衔接。
5. 不要输出内部状态桶名，不要把方法论术语直接写进交付物。
        """.strip()

    def _artifact_state_summary(self, state: ProjectState) -> str:
        sections = [
            _format_artifact_items("当前理解", state.current_understanding, limit=6),
            _format_artifact_items("待确认项", state.pending_items, limit=5),
            _format_artifact_items("已确认项", state.confirmed_items, limit=4),
            _format_artifact_items("冲突项", state.conflict_items, limit=4),
            _format_artifact_items("MVP 方向", state.mvp_items, limit=4),
        ]
        artifact_count = len(state.artifacts)
        version_count = len(state.versions)
        meta_lines: list[str] = []
        if artifact_count:
            meta_lines.append(f"已有历史交付物：{artifact_count} 份")
        if version_count:
            meta_lines.append(f"已有版本快照：{version_count} 个")

        summary_parts = [section for section in sections if section]
        if meta_lines:
            summary_parts.append("\n".join(meta_lines))
        return "\n\n".join(summary_parts) if summary_parts else "当前还没有可用沉淀，请基于项目摘要给出最小可用交付物。"

    def ensure_available(self) -> None:
        cli_path = self.settings.claude_cli_path
        if cli_path and not Path(cli_path).exists():
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=f"CLAUDE_CODE_CLI_PATH 指向的可执行文件不存在：{cli_path}",
            )
        if not cli_path and shutil.which("claude") is None:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message="未找到 Claude Code CLI。请安装 claude 或配置 CLAUDE_CODE_CLI_PATH。",
            )

    def resolved_cli_path(self) -> str:
        cli_path = self.settings.claude_cli_path
        if cli_path:
            return cli_path

        found = shutil.which("claude")
        if not found:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message="未找到 Claude Code CLI。请安装 claude 或配置 CLAUDE_CODE_CLI_PATH。",
            )
        return found

    def get_readiness(self) -> ProviderReadiness:
        try:
            self.ensure_available()
            cli_path = self.resolved_cli_path()
        except ProviderIssue as exc:
            return ProviderReadiness(
                provider="CLAUDE_AGENT_SDK",
                status="not_configured",
                summary="Claude Agent SDK 还没有准备好。",
                detail=exc.message,
                action_label="检查 Claude CLI",
            )

        try:
            completed = subprocess.run(
                [cli_path, "auth", "status"],
                capture_output=True,
                text=True,
                check=True,
            )
        except FileNotFoundError as exc:
            return ProviderReadiness(
                provider="CLAUDE_AGENT_SDK",
                status="not_configured",
                summary="Claude Agent SDK 还没有准备好。",
                detail=f"Claude CLI 不可执行：{exc}",
                action_label="检查 Claude CLI",
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            return ProviderReadiness(
                provider="CLAUDE_AGENT_SDK",
                status="error",
                summary="Claude Agent SDK 状态检查失败。",
                detail=detail or "无法读取 Claude 登录状态。",
                action_label="检查 Claude 登录态",
            )

        try:
            auth_status = json.loads((completed.stdout or "").strip() or "{}")
        except json.JSONDecodeError:
            return ProviderReadiness(
                provider="CLAUDE_AGENT_SDK",
                status="error",
                summary="Claude Agent SDK 状态检查失败。",
                detail=f"无法解析 Claude 登录状态输出：{completed.stdout.strip()}",
                action_label="检查 Claude CLI 输出",
            )

        if not auth_status.get("loggedIn"):
            return ProviderReadiness(
                provider="CLAUDE_AGENT_SDK",
                status="auth_required",
                summary="Claude Agent SDK 还没有登录。",
                detail="Claude CLI 当前未登录，先完成 Claude 登录。",
                action_label="完成 Claude 登录",
            )

        if self.settings.claude_model:
            return ProviderReadiness(
                provider="CLAUDE_AGENT_SDK",
                status="ready",
                summary="Claude Agent SDK 已就绪，且已锁定模型配置。",
                detail=f"当前模型：{self.settings.claude_model}",
            )

        return ProviderReadiness(
            provider="CLAUDE_AGENT_SDK",
            status="ready_default_model",
            summary="Claude Agent SDK 已可用，但当前走 Claude CLI 默认模型。",
            detail="建议补充 CLAUDE_MODEL，把部署环境模型锁定下来。",
            action_label="锁定 Claude 模型",
        )

    def _build_prompt(self, turn: AgentTurnInput) -> str:
        return self._build_structured_prompt(turn)

    @staticmethod
    def _format_recent_messages(turn: AgentTurnInput) -> str:
        if not turn.recent_messages:
            return "当前没有历史对话记录。"

        role_label = {
            "user": "用户",
            "assistant": "助手",
            "system": "系统",
        }
        lines: list[str] = []
        for message in turn.recent_messages[-12:]:
            label = role_label.get(message.role, message.role)
            content = " ".join(message.content.split()).strip()
            if len(content) > 300:
                content = f"{content[:300]}..."
            lines.append(f"- {label}: {content}")
        return "\n".join(lines)

    def _build_streaming_prompt(self, turn: AgentTurnInput) -> str:
        citations_json = json.dumps(
            [citation.model_dump() for citation in turn.evidence_citations],
            ensure_ascii=False,
            indent=2,
        )
        source_json = json.dumps(turn.source_summaries, ensure_ascii=False, indent=2)
        history_text = self._format_recent_messages(turn)
        return f"""
你在客户需求转译台的一期正式运行时里工作。

项目：
- 名称：{turn.project.name}
- 场景：{turn.project.scenario_type}
- 摘要：{turn.project.summary}

当前用户消息：
{turn.user_message}

最近对话记录：
{history_text}

本轮用户选中的 source IDs：
{json.dumps(turn.selected_source_ids, ensure_ascii=False)}

本轮 source 摘要：
{source_json}

NotebookLM grounding：
{turn.evidence_summary}

NotebookLM citations：
{citations_json}

需求分析方法参考：
{self.methodology_skill}

方法论执行提醒：
{self._methodology_execution_notes()}

资料理解工作流参考：
{self.evidence_skill}

请直接输出面向用户的自然中文回复，不要输出 JSON，不要输出 markdown 标题。
要求：
1. 先回应用户当前问题，再推进真实需求理解。
2. 语言自然、专业、直接，不要说空话，不要炫耀方法论术语。
3. 如果证据不足，要明确指出还需要确认什么。
4. 尽量把回复控制在 2 到 4 段，便于前端流式展示。
5. 不要生成交付物，不要描述内部状态桶名字。
        """.strip()

    def _build_structured_prompt(
        self,
        turn: AgentTurnInput,
        assistant_message: str | None = None,
    ) -> str:
        state_json = json.dumps(turn.state.model_dump(mode="json"), ensure_ascii=False, indent=2)
        citations_json = json.dumps(
            [citation.model_dump() for citation in turn.evidence_citations],
            ensure_ascii=False,
            indent=2,
        )
        source_json = json.dumps(turn.source_summaries, ensure_ascii=False, indent=2)
        history_text = self._format_recent_messages(turn)
        return f"""
你在客户需求转译台的一期正式运行时里工作。

项目：
- 名称：{turn.project.name}
- 场景：{turn.project.scenario_type}
- 摘要：{turn.project.summary}

当前用户消息：
{turn.user_message}

最近对话记录：
{history_text}

本轮用户选中的 source IDs：
{json.dumps(turn.selected_source_ids, ensure_ascii=False)}

当前项目状态：
{state_json}

本轮 source 摘要：
{source_json}

NotebookLM grounding：
{turn.evidence_summary}

NotebookLM citations：
{citations_json}

刚刚已经流式发送给用户的助手回复：
{assistant_message or "当前没有已发送正文，你需要在 assistant_message 里补出完整回复。"}

需求分析方法参考：
{self.methodology_skill}

方法论执行提醒：
{self._methodology_execution_notes()}

资料理解工作流参考：
{self.evidence_skill}

请输出结构化 JSON，不要输出额外解释。
要求：
1. assistant_message 用自然中文，简洁但完整。
1a. 如果上面已经提供了“刚刚已经流式发送给用户的助手回复”，assistant_message 必须与那段正文保持一致，不要改写。
2. 优先推进真实需求理解，不要空泛鼓励。
3. 每个状态桶只放当前轮最值得沉淀的内容。
4. 如果证据不足，不要把内容塞进 confirmed_items。
5. request_artifacts 仅在用户本轮明确要求交付物时再填。
6. citations 只整理当前 grounding 已提供的内容，不要编造。
7. 不要向用户炫耀方法论名词，要把分析结果翻译成自然业务语言。
        """.strip()

    @staticmethod
    def _assistant_text_from_message(message: AssistantMessage) -> str:
        parts: list[str] = []
        for block in message.content:
            if isinstance(block, TextBlock):
                parts.append(block.text)
        return "".join(parts)

    @staticmethod
    def _stream_event_text_delta(message: StreamEvent) -> str | None:
        event = message.event if isinstance(message.event, dict) else None
        if not event or event.get("type") != "content_block_delta":
            return None

        delta = event.get("delta")
        if not isinstance(delta, dict) or delta.get("type") != "text_delta":
            return None

        text = delta.get("text")
        return text if isinstance(text, str) and text else None

    async def stream_assistant_text(self, turn: AgentTurnInput) -> AsyncIterator[str]:
        self.ensure_available()

        options = ClaudeAgentOptions(
            system_prompt="你是客户需求转译台的一期正式分析智能体。",
            allowed_tools=[],
            tools=[],
            model=self.settings.claude_model,
            max_turns=self.settings.claude_max_turns,
            cwd=str(self.settings.root_dir),
            cli_path=self.settings.claude_cli_path,
            include_partial_messages=True,
        )

        emitted_text = ""
        final_text = ""

        try:
            async for message in query(prompt=self._build_streaming_prompt(turn), options=options):
                if isinstance(message, StreamEvent):
                    delta_text = self._stream_event_text_delta(message)
                    if delta_text:
                        emitted_text = f"{emitted_text}{delta_text}"
                        yield delta_text
                    continue

                if isinstance(message, AssistantMessage):
                    full_text = self._assistant_text_from_message(message)
                    if not full_text:
                        continue

                    delta = full_text
                    if full_text.startswith(emitted_text):
                        delta = full_text[len(emitted_text):]

                    if delta:
                        emitted_text = full_text
                        yield delta
                    continue

                if isinstance(message, ResultMessage):
                    if message.is_error:
                        errors = ", ".join(message.errors or [])
                        raise ProviderIssue(
                            provider="CLAUDE_AGENT_SDK",
                            message=errors or message.result or "Claude Agent SDK 返回错误。",
                        )

                    final_text = (message.result or "").strip()
                    continue

            if final_text:
                if final_text.startswith(emitted_text):
                    trailing = final_text[len(emitted_text):]
                    if trailing:
                        yield trailing
                elif final_text != emitted_text:
                    yield final_text
        except CLINotFoundError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=f"未找到 Claude Code CLI：{exc}",
            ) from exc
        except FileNotFoundError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=f"Claude Agent SDK 运行失败：{exc}",
            ) from exc
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=(
                    "Claude Agent SDK 返回了无法解析的结构化结果。"
                    f"错误：{exc}"
                ),
            ) from exc

    def _artifact_prompt(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
    ) -> str:
        state_summary = self._artifact_state_summary(state)
        if artifact_type == "document":
            output_instruction = (
                "输出文档稿。body 用 markdown 正文，至少包含：项目目标、真实需求、范围边界、"
                "主要冲突、MVP 能力包、验收指标。"
            )
        elif artifact_type == "page_solution":
            output_instruction = (
                "输出单页 HTML 页面方案。必须包含 <!doctype html>、<title>、<main>、3 到 5 个页面/模块区块，"
                "说明文字简短直接，整体尽量控制在 220 行内，不允许外链脚本，不允许引用外部样式资源。"
            )
        else:
            output_instruction = (
                "输出单页 HTML 交互稿。必须包含 <!doctype html>、<title>、<main>、4 到 6 个主流程步骤、"
                "关键交互约束和页面衔接说明，说明文字简短直接，整体尽量控制在 220 行内，"
                "不允许外链脚本，不允许引用外部样式资源。"
            )
        output_contract = (
            "只输出结构化 JSON，不要输出额外解释。"
            if artifact_type == "document"
            else (
                "严格按下面格式输出，不要加 ```json 或 ```html 代码块：\n"
                "TITLE: <标题>\n"
                "SUMMARY: <摘要>\n"
                "HTML:\n"
                "<!doctype html>..."
            )
        )

        return f"""
你在客户需求转译台的一期正式运行时里工作，当前任务是生成 artifact。

项目：
- 名称：{project.name}
- 场景：{project.scenario_type}
- 摘要：{project.summary}

当前项目沉淀摘要：
{state_summary}

{self._artifact_generation_notes()}

任务类型：{artifact_type}
要求：
1. {output_instruction}
2. title 和 summary 用自然中文。
3. 内容必须基于当前项目状态，不要编造未出现的业务主体。
4. 如果状态信息不足，也要明确写出待确认边界，不能用空壳内容搪塞。
5. {output_contract}
6. 不要把方法论名词硬写进最终交付物，除非用户明确要求展示分析方法。
        """.strip()

    async def run_turn(
        self,
        turn: AgentTurnInput,
        assistant_message: str | None = None,
    ) -> AsyncIterator[tuple[str, str | AgentTurnResult]]:
        self.ensure_available()

        options = ClaudeAgentOptions(
            system_prompt="你是客户需求转译台的一期正式分析智能体。",
            allowed_tools=[],
            tools=[],
            model=self.settings.claude_model,
            max_turns=self.settings.claude_max_turns,
            cwd=str(self.settings.root_dir),
            cli_path=self.settings.claude_cli_path,
            include_partial_messages=True,
            output_format=_output_schema(),
        )

        try:
            async for message in query(
                prompt=self._build_structured_prompt(turn, assistant_message=assistant_message),
                options=options,
            ):
                if isinstance(message, AssistantMessage):
                    # 结构化输出模式下，partial message 通常是中间 JSON 草稿，
                    # 直接流给前端会污染聊天界面，所以这里主动忽略。
                    continue
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        errors = ", ".join(message.errors or [])
                        raise ProviderIssue(
                            provider="CLAUDE_AGENT_SDK",
                            message=errors or message.result or "Claude Agent SDK 返回错误。",
                        )

                    raw = message.structured_output
                    if not raw and message.result:
                        raw = _coerce_json_payload(message.result)
                    output = AgentStructuredOutput.model_validate(
                        _normalize_structured_output_payload(raw)
                    )
                    state_updates = {
                        "current_understanding": output.current_understanding,
                        "pending_items": output.pending_items,
                        "confirmed_items": output.confirmed_items,
                        "conflict_items": output.conflict_items,
                        "mvp_items": output.mvp_items,
                    }
                    yield (
                        "result",
                        AgentTurnResult(
                            assistant_message=assistant_message or output.assistant_message,
                            citations=output.citations,
                            state_updates=state_updates,
                            version_summary=output.version_summary,
                            request_artifacts=output.request_artifacts,
                            raw_result=raw if isinstance(raw, dict) else None,
                        ),
                    )
                elif isinstance(message, StreamEvent):
                    # 暂时不把 SDK 的内部事件直接暴露给前端，避免泄漏无关细节。
                    continue
        except CLINotFoundError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=f"未找到 Claude Code CLI：{exc}",
            ) from exc
        except FileNotFoundError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=f"Claude Agent SDK 运行失败：{exc}",
            ) from exc
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=(
                    "Claude Agent SDK 返回了无法解析的结构化结果。"
                    f"错误：{exc}"
                ),
            ) from exc

    async def generate_artifact(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
    ) -> GeneratedArtifactOutput:
        self.ensure_available()

        output_format = _artifact_output_schema(artifact_type) if artifact_type == "document" else None
        max_attempts = 1 if artifact_type == "document" else 2

        try:
            for attempt in range(max_attempts):
                options = ClaudeAgentOptions(
                    system_prompt="你是客户需求转译台的一期正式交付物生成智能体。",
                    allowed_tools=[],
                    tools=[],
                    model=self.settings.claude_model,
                    max_turns=self.settings.claude_max_turns,
                    cwd=str(self.settings.root_dir),
                    cli_path=self.settings.claude_cli_path,
                    include_partial_messages=False,
                    output_format=output_format,
                )
                parse_error: Exception | None = None
                prompt = self._artifact_prompt(project=project, state=state, artifact_type=artifact_type)
                if artifact_type != "document" and attempt > 0:
                    prompt = (
                        f"{prompt}\n\n补充要求：你上一轮没有按指定格式输出。"
                        "这一轮必须严格返回 TITLE、SUMMARY、HTML 三段，除此之外不要输出任何其他文字。"
                    )

                async for message in query(prompt=prompt, options=options):
                    if not isinstance(message, ResultMessage):
                        continue

                    if message.is_error:
                        errors = ", ".join(message.errors or [])
                        raise ProviderIssue(
                            provider="CLAUDE_AGENT_SDK",
                            message=errors or message.result or "Claude Agent SDK 返回错误。",
                        )

                    raw = message.structured_output
                    try:
                        if artifact_type == "document":
                            if not raw and message.result:
                                raw = _coerce_json_payload(message.result)
                            return GeneratedArtifactOutput.model_validate(
                                _normalize_generated_artifact_output_payload(raw)
                            )

                        if raw:
                            return GeneratedArtifactOutput.model_validate(
                                _normalize_generated_artifact_output_payload(raw)
                            )
                        if message.result:
                            return GeneratedArtifactOutput.model_validate(
                                _coerce_html_artifact_payload(message.result)
                            )
                    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                        parse_error = exc
                        break

                if parse_error and attempt < max_attempts - 1:
                    continue
                if parse_error:
                    raise parse_error
        except CLINotFoundError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=f"未找到 Claude Code CLI：{exc}",
            ) from exc
        except FileNotFoundError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=f"Claude Agent SDK 运行失败：{exc}",
            ) from exc
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message=(
                    "Claude Agent SDK 返回了无法解析的结构化结果。"
                    f"错误：{exc}"
                ),
            ) from exc

        raise ProviderIssue(
            provider="CLAUDE_AGENT_SDK",
            message="Claude Agent SDK 未返回可用的 artifact 结果。",
        )
