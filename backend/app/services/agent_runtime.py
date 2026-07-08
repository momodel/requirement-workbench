from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from pathlib import Path
import re
import shutil
import struct
import subprocess
import uuid
from typing import Any, AsyncIterator
from urllib.parse import urlparse

try:
    from claude_agent_sdk import (
        AssistantMessage,
        CLINotFoundError,
        ClaudeAgentOptions,
        McpSdkServerConfig,
        ResultMessage,
        StreamEvent,
        TextBlock,
        create_sdk_mcp_server,
        query,
        tool,
    )

    _CLAUDE_AGENT_SDK_AVAILABLE = True
except ImportError:  # claude-agent-sdk is optional; the active runtime uses deepagents.
    _CLAUDE_AGENT_SDK_AVAILABLE = False
    AssistantMessage = None  # type: ignore[assignment]
    CLINotFoundError = None  # type: ignore[assignment]
    ClaudeAgentOptions = None  # type: ignore[assignment]
    McpSdkServerConfig = None  # type: ignore[assignment]
    ResultMessage = None  # type: ignore[assignment]
    StreamEvent = None  # type: ignore[assignment]
    TextBlock = None  # type: ignore[assignment]
    create_sdk_mcp_server = None  # type: ignore[assignment]
    query = None  # type: ignore[assignment]
    tool = None  # type: ignore[assignment]
from pydantic import ValidationError

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    STATE_CATEGORIES,
    AgentStructuredOutput,
    ArtifactType,
    AgentTurnInput,
    AgentTurnResult,
    ArtifactRecord,
    ChatCitation,
    GeneratedArtifactOutput,
    ProjectState,
    ProjectSummary,
    ProviderReadiness,
    ProviderIssue,
    StateCategory,
    StateItem,
    SourceUpsert,
)
from .artifact_generation import ArtifactGenerationService
from .image_generation import ApimartImageGenerationService
from .evidence_runtime import QdrantLlamaIndexEvidenceRuntime
from .project_catalog import ProjectCatalog
from .project_state import ProjectStateService
from .runtime_contracts import EvidenceRuntime

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


def _state_item_tool_schema() -> dict:
    return {
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


def _state_tool_categories() -> tuple[StateCategory, ...]:
    return tuple(
        category
        for category in STATE_CATEGORIES
        if category not in {"versions", "artifacts"}
    )


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
            if idx >= len(text) or text[idx] not in {'"', "'", "`"}:
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

    def extract_unquoted_html_field(names: tuple[str, ...]) -> str | None:
        for name in names:
            match = re.search(rf'["\']?{re.escape(name)}["\']?\s*:\s*', text, re.I)
            if not match:
                continue

            html_start = text.find("<!doctype", match.end())
            if html_start < 0:
                html_start = text.find("<html", match.end())
            if html_start < 0:
                continue

            tail = text[html_start:].strip()
            closing_match = re.search(r"</html\s*>", tail, re.I)
            if closing_match:
                return tail[: closing_match.end()].strip()
            return tail.rstrip("} \n\r\t,").strip()
        return None

    loose_title = extract_loose_string_field(("title",))
    loose_summary = extract_loose_string_field(("summary",))
    loose_html = extract_loose_string_field(("html", "content")) or extract_unquoted_html_field(
        ("html", "content")
    )
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
    def __init__(
        self,
        settings: AppSettings = DEFAULT_SETTINGS,
        evidence_runtime: EvidenceRuntime | None = None,
    ):
        self.settings = settings
        cas_project_dir = settings.cas_project_dir
        self.runtime_config_dir = cas_project_dir / ".claude-runtime"
        self.catalog = ProjectCatalog(settings)
        self.project_state_service = ProjectStateService(self.catalog)
        self.artifact_generation_service = ArtifactGenerationService(settings)
        self.image_generation_service = ApimartImageGenerationService(settings)
        self._background_artifact_tasks: set[asyncio.Task] = set()
        self.evidence_runtime = evidence_runtime or QdrantLlamaIndexEvidenceRuntime(settings, catalog=self.catalog)
        self.wiki_runtime = None  # set via attach_wiki_runtime to avoid construction-order coupling

    def attach_wiki_runtime(self, wiki_runtime) -> None:
        self.wiki_runtime = wiki_runtime

    def _build_options(
        self,
        *,
        system_prompt: str,
        include_partial_messages: bool,
        output_format: dict | None = None,
        mcp_servers: dict[str, McpSdkServerConfig] | None = None,
        allowed_tools: list[str] | None = None,
    ) -> ClaudeAgentOptions:
        # Claude CLI 默认会读取 ~/.claude 下的用户级设置、插件和历史。
        # 这里把 CAS 的项目上下文收口到 backend/，并显式禁用 user setting source，
        # 避免用户机器上的全局配置或仓库根目录的其他上下文污染后端运行时行为。
        self.runtime_config_dir.mkdir(parents=True, exist_ok=True)
        return ClaudeAgentOptions(
            system_prompt=system_prompt,
            allowed_tools=allowed_tools or [],
            tools=[],
            model=self.settings.claude_model,
            permission_mode="bypassPermissions" if mcp_servers else None,
            max_turns=self.settings.claude_max_turns,
            cwd=str(self.settings.cas_project_dir),
            cli_path=self.settings.claude_cli_path,
            include_partial_messages=include_partial_messages,
            output_format=output_format,
            mcp_servers=mcp_servers,
            setting_sources=["project", "local"],
            plugins=[],
            env={
                "CLAUDE_CONFIG_DIR": str(self.runtime_config_dir),
            },
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "你是客户需求转译台的主分析智能体，不是普通聊天助手。"
            "先理解真实需求，再决定是否写沉淀、打快照、生成交付物。"
            "讨论态不等于确认态；没有足够证据，不要写 confirmed。"
            "不要把页面建议或实现建议直接当成正式需求结论。"
            "不要伪造 citations。"
            "不要把内部桶名、tool_call、方法论术语、内部路径暴露给用户。"
            "只有真实工具执行成功，才算状态写入、快照生成、artifact 生成成功。"
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
4. 页面方案、交互稿、视觉方案在探索阶段默认先做图片视觉稿；HTML 只用于用户明确要求可点击、可运行、导出 HTML 或保存成正式交付物。
5. 生成 HTML 时，页面方案强调信息结构和页面分工；交互稿必须是可点击的界面原型，至少要看得见操作入口、界面区块、状态反馈或流程切换。
6. 不要输出内部状态桶名，不要把方法论术语直接写进交付物。
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
            status="not_configured",
            summary="Claude Agent SDK 未配置模型。",
            detail="请设置 CLAUDE_MODEL，避免主链路依赖 Claude CLI 默认模型。",
            action_label="配置 CLAUDE_MODEL",
        )

    def _build_prompt(self, turn: AgentTurnInput) -> str:
        return self._build_structured_prompt(turn)

    def _build_loop_prompt(self, turn: AgentTurnInput) -> str:
        state_summary = self._artifact_state_summary(turn.state)
        source_json = json.dumps(turn.source_summaries, ensure_ascii=False, indent=2)
        history_text = self._format_recent_messages(turn)
        selected_source_ids = json.dumps(turn.selected_source_ids, ensure_ascii=False)
        wiki_status = self._wiki_status_line(turn.project.id)
        return f"""
你在客户需求转译台的一期正式运行时里工作。

项目：
- 名称：{turn.project.name}
- 场景：{turn.project.scenario_type}
- 摘要：{turn.project.summary}

项目 wiki 状态：
{wiki_status}

当前用户消息：
{turn.user_message}

最近对话记录：
{history_text}

当前项目沉淀摘要：
{state_summary}

当前可用资料摘要：
{source_json}

本轮用户显式选中的 source IDs：
{selected_source_ids}

本轮前端显式请求生成的交付物类型：
{json.dumps(turn.request_artifact_types, ensure_ascii=False)}

可用工具：
1. `query_project_evidence`
   - 需要 source-grounded 证据、引用或核对资料说法时再调用
   - 不要用它代替最终项目裁决
2. `update_project_state`
   - 只写本轮新增的 current_understanding / pending_items / confirmed_items / conflict_items / mvp_items
   - 讨论、计划、评审意见不要为了凑动作硬写入
3. `create_version_snapshot`
   - 只在明确形成问题定义、范围边界、冲突结论、MVP 方向，或用户明确要求留痕时调用
4. `generate_artifact`
   - 只在用户明确要求 HTML、可点击原型、可运行原型、导出 HTML，或要求把某版内容保存为正式交付物时调用
   - 不要因为用户只是说“页面方案 / 交互稿 / 看看效果 / 改上一版”就调用
5. `generate_visual_mockup`
   - 用户要求视觉稿、页面效果图、生图、页面方案、交互稿、图片版原型、看看效果、改上一版时优先调用
   - size、resolution、n、quality、style、reference_image_urls 等参数由工具调用显式填写；不要假装来自环境默认值
6. `wiki_list_pages` / `wiki_read_page`
   - 用于读项目 wiki 综合层（实体、术语、规则、冲突、待确认问题等长期工作理解）
   - 仅作为"补充上下文"，不能拿 wiki 段落当 citation；citation 必须走 `query_project_evidence`
   - 适合在你不确定项目背景或某实体怎么定义时先 list 再 read 一两页

方法论执行提醒：
{self._methodology_execution_notes()}

交付物生成提醒：
{self._artifact_generation_notes()}

输出与动作要求：
1. 正文只输出面向用户的自然中文，不要输出 JSON、HTML、Markdown 标题、工具痕迹、内部状态桶名字。
2. 如果只是讨论、评审、头脑风暴、要计划、要求“不要直接开始改”，通常只聊天，不写沉淀、不打快照、不生成交付物。
3. 如果需要 grounded 证据，请先调用 `query_project_evidence`，再基于结果回答。
4. 如果本轮确实形成了新增理解、待确认项、已确认事实、冲突或 MVP，再调用 `update_project_state`，只写本轮增量。
5. 只有命中关键里程碑时才调用 `create_version_snapshot`。
6. 页面方案 / 交互稿 / 视觉方案默认优先调用 `generate_visual_mockup`，图片直接出现在聊天里；不要因为正文提到页面方案或交互稿就自动调用 `generate_artifact`。
7. 只有用户明确要求 HTML、可点击原型、可运行原型、导出 HTML 或保存成交付物时，才调用 `generate_artifact`；如果“本轮前端显式请求生成的交付物类型”不是空数组，也必须调用 `generate_artifact`。
8. 多轮修改视觉方案时，优先使用最近历史图片作为 `generate_visual_mockup.reference_image_urls`。
9. 可以先说话，再调工具；也可以先查证据再回答。顺序由你自己判断。
10. 如果工具失败，要诚实告诉用户当前哪一步失败了，以及还能继续做什么。
11. 不要为了显得积极而调用无关工具。
12. confirmed_items 与最终 citation 必须来自 `query_project_evidence` 的真实返回。wiki 是综合层，不是 citation 源；不允许把 wiki 段落写进 citation 或 source_refs。
        """.strip()

    def _wiki_status_line(self, project_id: str) -> str:
        if self.wiki_runtime is None:
            return "wiki: not_configured（wiki_runtime 未注入）"
        try:
            record = self.wiki_runtime.get_record(project_id)
        except Exception:  # noqa: BLE001 — best-effort context
            return "wiki: 状态读取失败"
        last = record.last_maintained_at or "尚未维护"
        pending = len(record.pending_source_ids)
        suffix = f", pending={pending}" if pending else ""
        return f"wiki: pages={record.page_count}, last_maintained={last}{suffix}"

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
            for image in message.image_results:
                if not isinstance(image, dict):
                    continue
                reference_url = str(image.get("url") or image.get("provider_url") or "").strip()
                if not reference_url:
                    continue
                title = str(image.get("title") or image.get("id") or "历史图片").strip()
                lines.append(
                    f"  - 历史图片：{title}；可作为 generate_visual_mockup.reference_image_urls 的输入：{reference_url}"
                )
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

项目知识库 grounding：
{turn.evidence_summary}

项目知识库 citations：
{citations_json}

方法论执行提醒：
{self._methodology_execution_notes()}

请直接输出面向用户的自然中文回复，不要输出 JSON，不要输出 markdown 标题。
要求：
1. 先回应用户当前问题，再推进真实需求理解。
2. 语言自然、专业、直接，不要说空话，不要炫耀方法论术语。
3. 先说清楚为什么现在要问这个或判断这个，让用户看得见你是在推进分析，不是在直接吐结论。
4. 如果本轮已经足够形成沉淀，要顺手说明你准备写入什么，但不要直接说内部状态桶名字。
5. 如果证据不足，要明确指出还需要确认什么。
6. 尽量把回复控制在 2 到 4 段，便于前端流式展示。
7. 页面方案、交互稿、视觉方案默认表达为图片视觉稿；只有用户明确要 HTML、可点击、可运行、导出或保存为正式交付物时，才承诺整理到交付物区。
8. 一旦正文里承诺会整理成正式文档稿 / HTML 页面方案 / HTML 交互稿，后续结构化结果必须填对应的 request_artifacts，不能只说不做。
9. 如果本轮是要生成正式交付物，正文只需要简短说明“现在开始整理什么、会写到哪里、用户稍后怎么看”，不要在聊天区提前展开完整文档、完整页面方案、完整交互稿或大段结构化清单。
10. 严禁在聊天正文里直接输出 HTML、Markdown 文档正文、伪 JSON、伪 YAML、request_artifacts 列表或状态桶明细。
11. 严禁输出 <think>、tool_call、TodoWrite、文件写入步骤、目录操作或任何工具调用痕迹。
        """.strip()

    def _build_structured_prompt(
        self,
        turn: AgentTurnInput,
        assistant_message: str | None = None,
    ) -> str:
        state_summary = self._artifact_state_summary(turn.state)
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

项目知识库 grounding：
{turn.evidence_summary}

项目知识库 citations：
{citations_json}

刚刚已经流式发送给用户的助手回复：
{assistant_message or "当前没有已发送正文，你需要在 assistant_message 里补出完整回复。"}

当前项目沉淀摘要：
{state_summary}

方法论执行提醒：
{self._methodology_execution_notes()}

你现在处于“状态提交 pass”。
这一轮不是继续聊天，也不是再写一份 JSON，而是根据上面的用户消息、证据和已发送正文，判断应该调用哪些工具，把本轮结论落成真实动作。

要求：
1. 如果上面已经提供了“刚刚已经流式发送给用户的助手回复”，把它当作已经发出去的正文，不要再改写聊天内容。
2. 先判断有没有本轮新增沉淀；有的话立刻调用 `update_project_state`，只提交本轮真正形成的结论。
3. 如果本轮形成了一个值得记录的阶段性结论，调用 `create_version_snapshot`。
4. 页面方案 / 交互稿 / 视觉方案默认优先调用 `generate_visual_mockup`；不要因为正文提到页面方案或交互稿就自动调用 `generate_artifact`。
5. 只有用户明确要求 HTML、可点击原型、可运行原型、导出 HTML 或保存成交付物时，才调用 `generate_artifact`。
6. `generate_artifact` 是异步任务登记工具，只传 artifact_type、title、summary 和可选 focus；不要先生成完整文档正文或 HTML 再调用。
7. HTML 交互稿对应 `interaction_flow`，HTML 页面方案对应 `page_solution`，文档稿对应 `document`。
8. 如果当前证据不足，不要把内容塞进 confirmed_items。
9. citations 只整理当前 grounding 已提供的内容，不要编造。
10. 优先顺序是：先调用需要的工具，再结束这一轮。
11. 最终文本只允许一句简短中文，可留空；不要输出 JSON、状态桶明细、工具调用痕迹或交付物正文。
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

    @staticmethod
    def _stream_event_tool_status(message: StreamEvent) -> dict[str, str] | None:
        event = message.event if isinstance(message.event, dict) else None
        if not event or event.get("type") != "content_block_start":
            return None

        content_block = event.get("content_block")
        if not isinstance(content_block, dict) or content_block.get("type") != "tool_use":
            return None

        tool_name = str(content_block.get("name") or "").strip()
        if tool_name.endswith("query_project_evidence"):
            return {
                "phase": "tool_running:query_project_evidence",
                "label": "正在检索资料证据",
            }
        if tool_name.endswith("update_project_state"):
            return {
                "phase": "tool_running:update_project_state",
                "label": "正在写入本轮沉淀",
            }
        if tool_name.endswith("create_version_snapshot"):
            return {
                "phase": "tool_running:create_version_snapshot",
                "label": "正在生成版本快照",
            }
        if tool_name.endswith("generate_artifact"):
            return {
                "phase": "tool_running:generate_artifact",
                "label": "正在生成交付物预览",
            }
        if tool_name.endswith("wiki_list_pages"):
            return {
                "phase": "tool_running:wiki_list_pages",
                "label": "正在读取项目 wiki 页面索引",
            }
        if tool_name.endswith("wiki_read_page"):
            return {
                "phase": "tool_running:wiki_read_page",
                "label": "正在读取 wiki 页面",
            }

        return None

    @staticmethod
    def _full_text_delta(full_text: str, emitted_text: str) -> str:
        if not full_text:
            return ""
        if not emitted_text:
            return full_text
        if full_text == emitted_text:
            return ""
        if full_text.startswith(emitted_text):
            return full_text[len(emitted_text):]
        if full_text in emitted_text:
            return ""

        max_overlap = min(len(full_text), len(emitted_text))
        for overlap in range(max_overlap, 0, -1):
            if emitted_text[-overlap:] == full_text[:overlap]:
                return full_text[overlap:]

        return full_text

    async def stream_assistant_text(self, turn: AgentTurnInput) -> AsyncIterator[str]:
        # 兼容旧测试和手工调试路径。
        # 当前正式工作台主链路已经切到 run_streaming_turn，不再走这条双段式流程。
        self.ensure_available()

        options = self._build_options(
            system_prompt="你是客户需求转译台的一期正式分析智能体。",
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

                    delta = self._full_text_delta(full_text, emitted_text)
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
        additional_instruction: str | None = None,
    ) -> str:
        state_summary = self._artifact_state_summary(state)
        if artifact_type == "document":
            output_instruction = (
                "输出文档稿。body 用 markdown 正文，至少包含：项目目标、真实需求、范围边界、"
                "主要冲突、MVP 能力包、验收指标。"
            )
        elif artifact_type == "page_solution":
            output_instruction = (
                "输出单页 HTML 页面方案原型。标题用自然中文，能反映页面场景或页面任务，"
                "不要写成泛化的“设计稿”。必须包含 <!doctype html>、<title>、<main>，"
                "并覆盖主流程所需的关键页面区块、信息结构和页面分工。说明文字简短直接，整体尽量保持紧凑，"
                "不允许外链脚本，不允许引用外部样式资源。"
            )
        else:
            output_instruction = (
                "输出单页 HTML 交互稿原型。标题用自然中文，能反映当前交互场景或任务，"
                "不要写成“流程说明”或“说明文档”。必须包含 <!doctype html>、<title>、<main>、可见的操作区和结果区，"
                "并覆盖主流程所需的关键交互入口、状态反馈和流程推进。"
                "不要写成整页大段说明文档，也不要只列流程步骤。说明文字简短直接，整体尽量保持紧凑，"
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

本轮额外整理重点：
{additional_instruction or "无，按当前项目沉淀直接整理。"}

{self._artifact_generation_notes()}

任务类型：{artifact_type}
要求：
1. {output_instruction}
2. title 和 summary 用自然中文。
3. 内容必须基于当前项目状态，不要编造未出现的业务主体。
4. 如果状态信息不足，也要明确写出待确认边界，不能用空壳内容搪塞。
5. {output_contract}
6. 不要把方法论名词硬写进最终交付物，除非用户明确要求展示分析方法。
7. 如果任务类型是 `interaction_flow`，正文必须以界面和交互为主，要表现出操作入口、界面区块、状态变化和流程推进，不要生成整页说明文。
        """.strip()

    @staticmethod
    def _normalize_artifact_type(raw_type: str | None) -> ArtifactType:
        allowed: tuple[ArtifactType, ...] = ("document", "page_solution", "interaction_flow")
        if raw_type in allowed:
            return raw_type
        raise ValueError(f"不支持的 artifact_type：{raw_type}")

    @staticmethod
    def _infer_artifact_types_from_assistant_message(message: str | None) -> list[ArtifactType]:
        if not message:
            return []

        normalized = message.replace(" ", "")
        inferred: list[ArtifactType] = []
        if "交互稿" in normalized:
            inferred.append("interaction_flow")
        if "页面方案" in normalized:
            inferred.append("page_solution")
        if "文档稿" in normalized or "需求文档" in normalized:
            inferred.append("document")
        return list(dict.fromkeys(inferred))

    def _make_update_project_state_tool(
        self,
        *,
        project_id: str,
        applied_state_updates: dict[StateCategory, list[StateItem]],
    ):
        item_schema = _state_item_tool_schema()
        properties = {
            category: {"type": "array", "items": item_schema}
            for category in _state_tool_categories()
        }

        @tool(
            "update_project_state",
            "把本轮确认过的项目沉淀真实写入项目状态。",
            {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            },
        )
        async def update_project_state_tool(args: dict) -> dict:
            try:
                allowed_source_ids = {s.id for s in self.catalog.list_sources(project_id)}
                applied_categories: dict[str, int] = {}
                for category in _state_tool_categories():
                    raw_items = args.get(category)
                    if not isinstance(raw_items, list) or not raw_items:
                        continue

                    normalized_items = [
                        SourceUpsert.model_validate(item)
                        for item in raw_items
                    ]

                    if category == "confirmed_items":
                        for item in normalized_items:
                            if not item.source_ids:
                                raise ValueError(
                                    "confirmed_items 必须带 source_ids；"
                                    "citation 只能来自 query_project_evidence 真实返回的 source。"
                                )
                            unknown = [
                                sid for sid in item.source_ids if sid not in allowed_source_ids
                            ]
                            if unknown:
                                raise ValueError(
                                    f"confirmed_items 中包含未知 source_id={unknown}；"
                                    "wiki slug 不是 source 引用，请通过 query_project_evidence 重新核实。"
                                )

                    state_items = [
                        StateItem(
                            id=f"{category}-{uuid.uuid4().hex[:10]}",
                            title=item.title,
                            body=item.body,
                            status=item.status,
                            category=category,
                            source_ids=item.source_ids,
                        )
                        for item in normalized_items
                    ]
                    self.project_state_service.append_category(
                        project_id=project_id,
                        category=category,
                        items=state_items,
                    )
                    applied_state_updates[category] = state_items
                    applied_categories[category] = len(state_items)

                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "project_id": project_id,
                                    "applied_categories": applied_categories,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ]
                }
            except Exception as exc:
                return {
                    "content": [{"type": "text", "text": str(exc)}],
                    "is_error": True,
                }

        return update_project_state_tool

    def _make_query_project_evidence_tool(
        self,
        *,
        project_id: str,
        default_selected_source_ids: list[str],
        evidence_results: list[dict],
    ):
        @tool(
            "query_project_evidence",
            "基于当前项目知识库查询 grounded 证据和 citations。",
            {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "selected_source_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
        )
        async def query_project_evidence_tool(args: dict) -> dict:
            try:
                question = str(args.get("question") or "").strip()
                if not question:
                    raise ValueError("question 不能为空。")

                raw_selected_source_ids = args.get("selected_source_ids")
                selected_source_ids = (
                    [str(item) for item in raw_selected_source_ids if item]
                    if isinstance(raw_selected_source_ids, list)
                    else default_selected_source_ids
                )
                try:
                    evidence = await asyncio.wait_for(
                        asyncio.to_thread(
                            self.evidence_runtime.query,
                            project_id,
                            question,
                            selected_source_ids=selected_source_ids or None,
                        ),
                        timeout=self.settings.evidence_query_timeout_seconds,
                    )
                except asyncio.TimeoutError as exc:
                    raise ProviderIssue(
                        provider="QDRANT_LLAMAINDEX",
                        message="项目知识库检索超时，当前证据工具暂不可用。",
                    ) from exc
                evidence_payload = {
                    "summary": evidence.summary,
                    "citations": [citation.model_dump() for citation in evidence.citations],
                    "source_refs": [citation.source_id for citation in evidence.citations if citation.source_id],
                    "coverage_hint": "grounded" if evidence.citations else "ungrounded",
                }
                evidence_results.append(evidence_payload)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(evidence_payload, ensure_ascii=False),
                        }
                    ]
                }
            except Exception as exc:
                message = exc.message if isinstance(exc, ProviderIssue) else str(exc)
                return {
                    "content": [{"type": "text", "text": message}],
                    "is_error": True,
                }

        return query_project_evidence_tool

    def _make_wiki_list_pages_tool(
        self,
        *,
        project_id: str,
        wiki_reads: list[dict],
    ):
        @tool(
            "wiki_list_pages",
            "列出当前项目 LLM Wiki 中所有页面的元信息（不含正文）。",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        )
        async def wiki_list_pages_tool(args: dict) -> dict:
            if self.wiki_runtime is None:
                return {
                    "content": [{"type": "text", "text": "wiki_runtime 未注入。"}],
                    "is_error": True,
                }
            try:
                pages = await asyncio.to_thread(self.wiki_runtime.list_pages, project_id)
            except Exception as exc:  # noqa: BLE001
                return {
                    "content": [{"type": "text", "text": str(exc)}],
                    "is_error": True,
                }
            payload = {"pages": [page.model_dump() for page in pages]}
            wiki_reads.append({"op": "list", "page_count": len(pages)})
            return {
                "content": [
                    {"type": "text", "text": json.dumps(payload, ensure_ascii=False)}
                ]
            }

        return wiki_list_pages_tool

    def _make_wiki_read_page_tool(
        self,
        *,
        project_id: str,
        wiki_reads: list[dict],
    ):
        @tool(
            "wiki_read_page",
            "读取当前项目 LLM Wiki 中某个页面的正文（用于补充上下文，不可作为 citation）。",
            {
                "type": "object",
                "properties": {
                    "slug": {"type": "string"},
                },
                "required": ["slug"],
                "additionalProperties": False,
            },
        )
        async def wiki_read_page_tool(args: dict) -> dict:
            if self.wiki_runtime is None:
                return {
                    "content": [{"type": "text", "text": "wiki_runtime 未注入。"}],
                    "is_error": True,
                }
            slug = str(args.get("slug") or "").strip()
            if not slug:
                return {
                    "content": [{"type": "text", "text": "slug 不能为空。"}],
                    "is_error": True,
                }
            try:
                page = await asyncio.to_thread(self.wiki_runtime.read_page, project_id, slug)
            except ProviderIssue as exc:
                return {
                    "content": [{"type": "text", "text": exc.message}],
                    "is_error": True,
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "content": [{"type": "text", "text": str(exc)}],
                    "is_error": True,
                }
            wiki_reads.append({"op": "read", "slug": slug, "title": page.title})
            return {
                "content": [
                    {"type": "text", "text": json.dumps(page.model_dump(), ensure_ascii=False)}
                ]
            }

        return wiki_read_page_tool

    def _make_create_version_snapshot_tool(
        self,
        *,
        project_id: str,
        generated_versions: list[StateItem],
    ):
        @tool(
            "create_version_snapshot",
            "在关键轮次生成一个项目版本快照。",
            {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "trigger_kind": {"type": "string"},
                },
                "required": ["summary"],
                "additionalProperties": False,
            },
        )
        async def create_version_snapshot_tool(args: dict) -> dict:
            try:
                version = self.project_state_service.create_version(
                    project_id=project_id,
                    trigger_kind=str(args.get("trigger_kind") or "analysis_checkpoint"),
                    summary=str(args.get("summary") or "").strip(),
                )
                generated_versions.append(version)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "project_id": project_id,
                                    "version_id": version.id,
                                    "title": version.title,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ]
                }
            except Exception as exc:
                return {
                    "content": [{"type": "text", "text": str(exc)}],
                    "is_error": True,
                }

        return create_version_snapshot_tool

    async def _complete_artifact_generation_job(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        artifact_id: str,
        title: str,
        summary: str,
        additional_instruction: str | None = None,
    ) -> None:
        try:
            generated = await self.generate_artifact(
                project=project,
                state=state,
                artifact_type=artifact_type,
                additional_instruction=additional_instruction,
            )
            artifact = self.artifact_generation_service.save_generated_output(
                project_id=project.id,
                artifact_type=artifact_type,
                generated=generated,
                metadata={
                    "generator": "claude-agent-sdk-async-job",
                    "requested_title": title,
                    "requested_summary": summary,
                },
                artifact_id=artifact_id,
            )
            self.project_state_service.create_artifact_version(
                project_id=project.id,
                artifact_title=artifact.title,
                artifact_type=artifact.artifact_type,
            )
        except Exception as exc:
            self.artifact_generation_service.catalog.save_artifact(
                project_id=project.id,
                artifact_type=artifact_type,
                title=title,
                summary=str(exc) or "交付物生成失败。",
                status="failed",
                content_format="html" if artifact_type != "document" else "markdown",
                storage_path=None,
                body=None,
                metadata={
                    "generator": "claude-agent-sdk-async-job",
                    "error": str(exc),
                },
                artifact_id=artifact_id,
            )

    def _schedule_artifact_generation_job(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        artifact_id: str,
        title: str,
        summary: str,
        additional_instruction: str | None = None,
    ) -> None:
        task = asyncio.create_task(
            self._complete_artifact_generation_job(
                project=project,
                state=state,
                artifact_type=artifact_type,
                artifact_id=artifact_id,
                title=title,
                summary=summary,
                additional_instruction=additional_instruction,
            )
        )
        self._background_artifact_tasks.add(task)
        task.add_done_callback(self._background_artifact_tasks.discard)

    def _normalize_reference_image_urls(self, urls: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_url in urls:
            url = str(raw_url or "").strip()
            if not url:
                continue
            local_data_url = self._chat_image_data_url(url)
            normalized.append(local_data_url or url)
        return normalized

    def _chat_image_data_url(self, url: str) -> str | None:
        path = url
        if url.startswith("http://") or url.startswith("https://"):
            parsed = urlparse(url)
            public_base = self.settings.public_api_base_url.rstrip("/")
            parsed_public_base = urlparse(public_base)
            if (
                parsed.scheme != parsed_public_base.scheme
                or parsed.netloc != parsed_public_base.netloc
            ):
                return None
            path = parsed.path

        parts = [part for part in path.split("/") if part]
        if len(parts) != 5 or parts[:2] != ["api", "projects"] or parts[3] != "chat-images":
            return None

        project_id = parts[2]
        image_id = parts[4]
        image_dir = self.settings.projects_dir / project_id / "chat-images" / image_id
        if not image_dir.exists() or not image_dir.is_dir():
            return None

        candidates = sorted(
            path for path in image_dir.iterdir()
            if path.is_file() and path.name.startswith("image.")
        )
        if not candidates:
            return None

        image_path = candidates[0]
        content_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{content_type};base64,{encoded}"

    @staticmethod
    def _png_too_small(raw: bytes, min_side: int = 14) -> bool:
        if len(raw) < 24 or raw[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        try:
            width, height = struct.unpack(">II", raw[16:24])
        except struct.error:
            return False
        return width < min_side or height < min_side

    def _chat_image_content_block(self, url: str) -> dict | None:
        data_url = self._chat_image_data_url(url)
        if not data_url:
            return None
        header, _, b64 = data_url.partition(",")
        if not b64 or "base64" not in header:
            return None
        media_type = header[len("data:"):].split(";", 1)[0] or "image/png"
        if media_type not in {"image/png", "image/jpeg", "image/gif", "image/webp"}:
            media_type = "image/png"
        if media_type == "image/png":
            try:
                raw = base64.b64decode(b64, validate=False)
            except Exception:
                return None
            if self._png_too_small(raw):
                return None
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64},
        }

    def _user_image_blocks(self, refs: list[dict]) -> list[dict]:
        blocks: list[dict] = []
        for ref in refs or []:
            if not isinstance(ref, dict):
                continue
            url = str(ref.get("url") or "").strip()
            if not url:
                continue
            block = self._chat_image_content_block(url)
            if block:
                blocks.append(block)
        return blocks

    def _make_generate_visual_mockup_tool(
        self,
        *,
        project: ProjectSummary,
        generated_image_tasks: list[asyncio.Task],
    ):
        @tool(
            "generate_visual_mockup",
            "调用图像模型生成页面/交互视觉稿。尺寸、分辨率、数量、风格等参数必须由本次工具调用显式传入，不从环境写死。",
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "prompt": {"type": "string"},
                    "size": {"type": "string", "description": "例如 16:9、1:1、9:16，按 provider 支持填写。"},
                    "resolution": {"type": "string", "description": "例如 1k、2k、4k，按 provider 支持填写。"},
                    "n": {"type": "integer", "minimum": 1, "maximum": 4},
                    "quality": {"type": "string"},
                    "style": {"type": "string"},
                    "reference_image_urls": {"type": "array", "items": {"type": "string"}},
                    "extra_parameters": {"type": "object", "additionalProperties": True},
                },
                "required": ["title", "summary", "prompt"],
                "additionalProperties": False,
            },
        )
        async def generate_visual_mockup_tool(args: dict) -> dict:
            image_id = f"image-{uuid.uuid4().hex[:10]}"
            title = str(args.get("title") or "交互视觉稿").strip()
            summary = str(args.get("summary") or "视觉稿正在生成中。").strip()

            async def complete_image_job() -> dict:
                result = await self.image_generation_service.generate(
                    project_id=project.id,
                    artifact_id=image_id,
                    title=title,
                    summary=summary,
                    prompt=str(args.get("prompt") or ""),
                    size=str(args.get("size") or "").strip() or None,
                    resolution=str(args.get("resolution") or "").strip() or None,
                    n=int(args["n"]) if args.get("n") is not None else None,
                    quality=str(args.get("quality") or "").strip() or None,
                    style=str(args.get("style") or "").strip() or None,
                    reference_image_urls=self._normalize_reference_image_urls([str(item) for item in args.get("reference_image_urls") or []]),
                    extra_parameters=args.get("extra_parameters") if isinstance(args.get("extra_parameters"), dict) else None,
                    output_dir=self.settings.projects_dir / project.id / "chat-images" / image_id,
                )
                return {
                    "id": image_id,
                    "title": result.title,
                    "summary": result.summary,
                    "url": f"/api/projects/{project.id}/chat-images/{image_id}",
                    "content_type": result.content_type,
                    "prompt": result.prompt,
                    "provider_url": result.provider_url,
                    "metadata": result.metadata,
                }

            try:
                task = asyncio.create_task(complete_image_job())
                generated_image_tasks.append(task)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "image_id": image_id,
                                    "title": title,
                                    "summary": summary,
                                    "status": "generating",
                                },
                                ensure_ascii=False,
                            ),
                        }
                    ]
                }
            except Exception as exc:
                return {"content": [{"type": "text", "text": str(exc)}], "is_error": True}

        return generate_visual_mockup_tool

    def _make_generate_artifact_tool(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        generated_artifacts: list[ArtifactRecord],
        generated_versions: list[StateItem],
    ):
        @tool(
            "generate_artifact",
            "登记一个后台交付物生成任务并立即返回生成中记录；不要在参数里生成完整正文或 HTML。",
            {
                "type": "object",
                "properties": {
                    "artifact_type": {
                        "type": "string",
                        "enum": ["document", "page_solution", "interaction_flow"],
                    },
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "focus": {"type": "string"},
                    "working_notes": {"type": "string"},
                },
                "required": ["artifact_type", "title", "summary"],
                "additionalProperties": False,
            },
        )
        async def generate_artifact_tool(args: dict) -> dict:
            try:
                artifact_type = self._normalize_artifact_type(args.get("artifact_type"))
                title = str(args.get("title") or "").strip() or {
                    "document": "需求文档稿",
                    "page_solution": "页面方案原型",
                    "interaction_flow": "交互稿原型",
                }[artifact_type]
                summary = str(args.get("summary") or "").strip() or "交付物正在生成中。"
                content_format = "markdown" if artifact_type == "document" else "html"
                artifact = self.artifact_generation_service.catalog.save_artifact(
                    project_id=project.id,
                    artifact_type=artifact_type,
                    title=title,
                    summary=summary,
                    status="generating",
                    content_format=content_format,
                    storage_path=None,
                    body=None,
                    metadata={
                        "generator": "claude-agent-sdk-async-job",
                        "focus": str(args.get("focus") or "").strip() or None,
                        "working_notes": str(args.get("working_notes") or "").strip() or None,
                    },
                )
                generated_artifacts.append(artifact)
                self._schedule_artifact_generation_job(
                    project=project,
                    state=state,
                    artifact_type=artifact_type,
                    artifact_id=artifact.id,
                    title=artifact.title,
                    summary=artifact.summary,
                    additional_instruction=str(args.get("focus") or args.get("working_notes") or "").strip() or None,
                )
                payload = json.dumps(
                    {
                        "artifact_id": artifact.id,
                        "artifact_type": artifact.artifact_type,
                        "title": artifact.title,
                        "summary": artifact.summary,
                        "status": artifact.status,
                    },
                    ensure_ascii=False,
                )
                return {"content": [{"type": "text", "text": payload}]}
            except Exception as exc:
                return {
                    "content": [{"type": "text", "text": str(exc)}],
                    "is_error": True,
                }

        return generate_artifact_tool

    def _artifact_mcp_servers(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        generated_artifacts: list[ArtifactRecord],
        generated_versions: list[StateItem],
    ) -> dict[str, McpSdkServerConfig]:
        artifact_tool = self._make_generate_artifact_tool(
            project=project,
            state=state,
            generated_artifacts=generated_artifacts,
            generated_versions=generated_versions,
        )
        return {
            "artifacts": create_sdk_mcp_server(
                name="project-artifacts",
                tools=[artifact_tool],
            )
        }

    def _turn_mcp_servers(
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
    ) -> dict[str, McpSdkServerConfig]:
        evidence_tool = self._make_query_project_evidence_tool(
            project_id=project.id,
            default_selected_source_ids=default_selected_source_ids,
            evidence_results=evidence_results,
        )
        state_tool = self._make_update_project_state_tool(
            project_id=project.id,
            applied_state_updates=applied_state_updates,
        )
        version_tool = self._make_create_version_snapshot_tool(
            project_id=project.id,
            generated_versions=generated_versions,
        )
        artifact_tool = self._make_generate_artifact_tool(
            project=project,
            state=state,
            generated_artifacts=generated_artifacts,
            generated_versions=generated_versions,
        )
        visual_tool = self._make_generate_visual_mockup_tool(
            project=project,
            generated_image_tasks=generated_image_tasks,
        )
        wiki_list_tool = self._make_wiki_list_pages_tool(
            project_id=project.id,
            wiki_reads=wiki_reads,
        )
        wiki_read_tool = self._make_wiki_read_page_tool(
            project_id=project.id,
            wiki_reads=wiki_reads,
        )
        return {
            "project-actions": create_sdk_mcp_server(
                name="project-actions",
                tools=[
                    evidence_tool,
                    state_tool,
                    version_tool,
                    artifact_tool,
                    visual_tool,
                    wiki_list_tool,
                    wiki_read_tool,
                ],
            )
        }

    def _artifact_commit_prompt(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_types: list[ArtifactType],
        assistant_message: str | None = None,
    ) -> str:
        state_summary = self._artifact_state_summary(state)
        return f"""
你现在只负责把已经承诺的交付物真实写入系统，不要再重复做大段分析。

项目：
- 名称：{project.name}
- 场景：{project.scenario_type}
- 摘要：{project.summary}

当前沉淀摘要：
{state_summary}

本轮已经发给用户的说明：
{assistant_message or "本轮没有额外说明。"}

待生成的 artifact 类型：
{json.dumps(artifact_types, ensure_ascii=False)}

要求：
1. 必须调用 generate_artifact 工具，为列表里的每个 artifact_type 各生成一次。
2. `document` 传 body；`page_solution` 和 `interaction_flow` 传 html。
3. title、summary 用自然中文，不要复用内部桶名。
4. `generate_artifact` 是异步任务登记工具，不要在调用前自行生成完整正文或 HTML。
5. 工具调用完成后，只用一句中文回复“已开始生成，完成后会出现在交付物区”。
6. 不要输出额外说明，不要在最终文本里重复 artifact 正文。
        """.strip()

    async def run_streaming_turn(
        self,
        turn: AgentTurnInput,
    ) -> AsyncIterator[tuple[str, dict]]:
        self.ensure_available()

        applied_state_updates: dict[StateCategory, list[StateItem]] = {}
        evidence_results: list[dict] = []
        generated_artifacts: list[ArtifactRecord] = []
        generated_versions: list[StateItem] = []
        generated_image_tasks: list[asyncio.Task] = []
        wiki_reads: list[dict] = []

        emitted_text = ""
        latest_assistant_text = ""
        final_result_text = ""
        emitted_wiki_read_count = 0

        options = self._build_options(
            system_prompt=self._system_prompt(),
            include_partial_messages=True,
            output_format=None,
            mcp_servers=self._turn_mcp_servers(
                project=turn.project,
                state=turn.state,
                default_selected_source_ids=turn.selected_source_ids,
                evidence_results=evidence_results,
                applied_state_updates=applied_state_updates,
                generated_artifacts=generated_artifacts,
                generated_versions=generated_versions,
                generated_image_tasks=generated_image_tasks,
                wiki_reads=wiki_reads,
            ),
            allowed_tools=[
                "query_project_evidence",
                "update_project_state",
                "create_version_snapshot",
                "generate_artifact",
                "generate_visual_mockup",
                "wiki_list_pages",
                "wiki_read_page",
            ],
        )

        yield (
            "assistant_status",
            {
                "phase": "agent_started",
                "label": "已接收问题，正在启动分析",
            },
        )

        prompt_text = self._build_loop_prompt(turn)
        image_blocks = self._user_image_blocks(turn.user_image_refs)
        if image_blocks:
            async def _user_message_stream():
                yield {
                    "type": "user",
                    "session_id": "",
                    "message": {
                        "role": "user",
                        "content": image_blocks + [{"type": "text", "text": prompt_text}],
                    },
                    "parent_tool_use_id": None,
                }

            prompt_arg: Any = _user_message_stream()
        else:
            prompt_arg = prompt_text

        try:
            async for message in query(
                prompt=prompt_arg,
                options=options,
            ):
                if isinstance(message, StreamEvent):
                    delta_text = self._stream_event_text_delta(message)
                    if delta_text:
                        emitted_text = f"{emitted_text}{delta_text}"
                        yield ("message_chunk", {"text": delta_text})
                        continue

                    tool_status = self._stream_event_tool_status(message)
                    if tool_status:
                        yield ("assistant_status", tool_status)
                    continue

                if isinstance(message, AssistantMessage):
                    full_text = self._assistant_text_from_message(message)
                    if not full_text:
                        continue

                    delta = self._full_text_delta(full_text, emitted_text)
                    if delta:
                        emitted_text = full_text
                        yield ("message_chunk", {"text": delta})
                    latest_assistant_text = full_text.strip()
                    continue

                if isinstance(message, ResultMessage):
                    if message.is_error:
                        errors = ", ".join(message.errors or [])
                        raise ProviderIssue(
                            provider="CLAUDE_AGENT_SDK",
                            message=errors or message.result or "Claude Agent SDK 返回错误。",
                        )

                    final_result_text = (message.result or "").strip()
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

        final_assistant_message = (
            latest_assistant_text
            or final_result_text
            or emitted_text.strip()
        )

        latest_evidence = evidence_results[-1] if evidence_results else None
        citations = latest_evidence.get("citations", []) if latest_evidence else []
        if latest_evidence:
            yield (
                "assistant_status",
                {
                    "phase": "tool_completed:query_project_evidence",
                    "label": "已拿到资料证据",
                },
            )
        if citations:
            yield ("citations", {"items": citations})

        if applied_state_updates:
            yield (
                "assistant_status",
                {
                    "phase": "tool_completed:update_project_state",
                    "label": "已写入本轮沉淀",
                },
            )
            for category, items in applied_state_updates.items():
                if not items:
                    continue
                yield (
                    f"{category}_patch",
                    {
                        "op": "upsert",
                        "items": [item.model_dump() for item in items],
                    },
                )

        explicit_versions = [
            version for version in generated_versions if version.title != "artifact_generated"
        ]
        if explicit_versions:
            yield (
                "assistant_status",
                {
                    "phase": "tool_completed:create_version_snapshot",
                    "label": "已生成版本快照",
                },
            )

        if generated_versions:
            yield (
                "version_patch",
                {
                    "op": "upsert",
                    "items": [version.model_dump() for version in generated_versions],
                },
            )

        if wiki_reads:
            yield (
                "wiki_reads",
                {"items": list(wiki_reads)},
            )

        if generated_artifacts:
            yield (
                "assistant_status",
                {
                    "phase": "tool_completed:generate_artifact",
                    "label": "已生成交付物预览",
                },
            )
            yield (
                "artifact_patch",
                {
                    "op": "upsert",
                    "items": [artifact.model_dump() for artifact in generated_artifacts],
                },
            )

        if generated_image_tasks:
            yield (
                "assistant_status",
                {
                    "phase": "tool_running:generate_visual_mockup",
                    "label": "正在生成视觉稿",
                },
            )
            try:
                generated_images = await asyncio.wait_for(
                    asyncio.gather(*generated_image_tasks),
                    timeout=self.settings.image_generation_timeout_seconds + 15,
                )
            except Exception as exc:
                raise ProviderIssue(
                    provider="APIMART_IMAGE",
                    message=str(exc) or "视觉稿生成失败。",
                ) from exc
            yield (
                "assistant_status",
                {
                    "phase": "tool_completed:generate_visual_mockup",
                    "label": "视觉稿已生成",
                },
            )
            for image in generated_images:
                yield ("image_result", image)

        yield (
            "final_message",
            {
                "text": final_assistant_message,
                "citations": citations,
            },
        )
        yield (
            "assistant_status",
            {
                "phase": "agent_completed",
                "label": "本轮分析已完成",
            },
        )

    async def run_turn(
        self,
        turn: AgentTurnInput,
        assistant_message: str | None = None,
    ) -> AsyncIterator[tuple[str, str | AgentTurnResult]]:
        # 兼容旧测试和手工调试路径。
        # 当前正式工作台主链路已经切到 run_streaming_turn，不再由 ChatService 调用这条双段式流程。
        self.ensure_available()

        applied_state_updates: dict[StateCategory, list[StateItem]] = {}
        generated_artifacts: list[ArtifactRecord] = []
        generated_versions: list[StateItem] = []
        parsed_output: AgentStructuredOutput | None = None
        raw_result_payload: dict | None = None
        latest_assistant_text = ""
        final_result_text = ""

        options = self._build_options(
            system_prompt="你是客户需求转译台的一期正式分析智能体。",
            include_partial_messages=False,
            output_format=None,
            mcp_servers=self._turn_mcp_servers(
                project=turn.project,
                state=turn.state,
                default_selected_source_ids=turn.selected_source_ids,
                evidence_results=[],
                applied_state_updates=applied_state_updates,
                generated_artifacts=generated_artifacts,
                generated_versions=generated_versions,
                generated_image_tasks=[],
                wiki_reads=[],
            ),
            allowed_tools=[
                "update_project_state",
                "create_version_snapshot",
                "generate_artifact",
            ],
        )

        try:
            async for message in query(
                prompt=self._build_structured_prompt(turn, assistant_message=assistant_message),
                options=options,
            ):
                if isinstance(message, AssistantMessage):
                    latest_assistant_text = self._assistant_text_from_message(message).strip()
                    continue
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        errors = ", ".join(message.errors or [])
                        raise ProviderIssue(
                            provider="CLAUDE_AGENT_SDK",
                            message=errors or message.result or "Claude Agent SDK 返回错误。",
                        )

                    final_result_text = (message.result or "").strip()
                    raw = message.structured_output
                    if raw:
                        parsed_output = AgentStructuredOutput.model_validate(
                            _normalize_structured_output_payload(raw)
                        )
                        raw_result_payload = raw if isinstance(raw, dict) else None
                        continue

                    if not final_result_text:
                        continue

                    try:
                        raw = _coerce_json_payload(final_result_text)
                        parsed_output = AgentStructuredOutput.model_validate(
                            _normalize_structured_output_payload(raw)
                        )
                        raw_result_payload = raw if isinstance(raw, dict) else None
                    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
                        # 工具优先模式下，最终文本不一定是结构化 JSON。
                        # 只要工具调用已经完成，就允许这一步保持为普通文本。
                        continue
                elif isinstance(message, StreamEvent):
                    tool_status = self._stream_event_tool_status(message)
                    if tool_status:
                        yield ("status", tool_status)
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

        fallback_state_updates: dict[StateCategory, list[SourceUpsert]] = {
            "current_understanding": [],
            "pending_items": [],
            "confirmed_items": [],
            "conflict_items": [],
            "mvp_items": [],
        }
        request_artifacts: list[ArtifactType] = []
        version_summary: str | None = None
        citations = turn.evidence_citations

        if parsed_output is not None:
            fallback_state_updates = {
                "current_understanding": parsed_output.current_understanding,
                "pending_items": parsed_output.pending_items,
                "confirmed_items": parsed_output.confirmed_items,
                "conflict_items": parsed_output.conflict_items,
                "mvp_items": parsed_output.mvp_items,
            }
            request_artifacts = parsed_output.request_artifacts
            version_summary = parsed_output.version_summary
            citations = parsed_output.citations or turn.evidence_citations

        final_assistant_message = (
            assistant_message
            or (parsed_output.assistant_message if parsed_output is not None else "")
            or latest_assistant_text
            or final_result_text
        ).strip()

        requested_artifact_types = list(dict.fromkeys(request_artifacts))
        inferred_artifact_types = self._infer_artifact_types_from_assistant_message(
            final_assistant_message
        )
        artifact_commit_types = requested_artifact_types or inferred_artifact_types
        if artifact_commit_types and not generated_artifacts:
            generated_versions = [
                version
                for version in generated_versions
                if version.title != "artifact_generated"
            ]
            committed_artifacts, committed_versions = await self.commit_artifacts(
                project=turn.project,
                state=self.project_state_service.get_project_state(turn.project.id),
                artifact_types=artifact_commit_types,
                assistant_message=final_assistant_message,
            )
            generated_artifacts.extend(committed_artifacts)
            generated_versions.extend(committed_versions)
            request_artifacts = []

        yield (
            "result",
            AgentTurnResult(
                assistant_message=final_assistant_message,
                citations=citations,
                state_updates=fallback_state_updates,
                version_summary=version_summary,
                request_artifacts=request_artifacts,
                persisted_state_updates=applied_state_updates,
                generated_artifacts=generated_artifacts,
                generated_versions=generated_versions,
                raw_result=raw_result_payload,
            ),
        )

    async def generate_artifact(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        additional_instruction: str | None = None,
    ) -> GeneratedArtifactOutput:
        self.ensure_available()

        output_format = _artifact_output_schema(artifact_type) if artifact_type == "document" else None
        max_attempts = 1 if artifact_type == "document" else 2

        try:
            for attempt in range(max_attempts):
                options = self._build_options(
                    system_prompt="你是客户需求转译台的一期正式交付物生成智能体。",
                    include_partial_messages=False,
                    output_format=output_format,
                )
                parse_error: Exception | None = None
                latest_assistant_text = ""
                prompt = self._artifact_prompt(
                    project=project,
                    state=state,
                    artifact_type=artifact_type,
                    additional_instruction=additional_instruction,
                )
                if artifact_type != "document" and attempt > 0:
                    prompt = (
                        f"{prompt}\n\n补充要求：你上一轮没有按指定格式输出。"
                        "这一轮必须严格返回 TITLE、SUMMARY、HTML 三段，除此之外不要输出任何其他文字。"
                    )

                async for message in query(prompt=prompt, options=options):
                    if isinstance(message, AssistantMessage):
                        latest_assistant_text = self._assistant_text_from_message(message).strip()
                        continue
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

                        candidates = [
                            candidate
                            for candidate in (message.result, latest_assistant_text)
                            if isinstance(candidate, str) and candidate.strip()
                        ]
                        for candidate in dict.fromkeys(candidates):
                            try:
                                return GeneratedArtifactOutput.model_validate(
                                    _coerce_html_artifact_payload(candidate)
                                )
                            except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
                                parse_error = exc
                        if parse_error:
                            break
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

    async def commit_artifacts(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_types: list[ArtifactType],
        assistant_message: str | None = None,
    ) -> tuple[list[ArtifactRecord], list[StateItem]]:
        self.ensure_available()
        deduped_types = list(dict.fromkeys(artifact_types))
        if not deduped_types:
            return [], []

        generated_artifacts: list[ArtifactRecord] = []
        generated_versions: list[StateItem] = []
        options = self._build_options(
            system_prompt="你是客户需求转译台的一期正式交付物落盘智能体。",
            include_partial_messages=True,
            mcp_servers=self._artifact_mcp_servers(
                project=project,
                state=state,
                generated_artifacts=generated_artifacts,
                generated_versions=generated_versions,
            ),
            allowed_tools=["generate_artifact"],
        )

        try:
            async for message in query(
                prompt=self._artifact_commit_prompt(
                    project=project,
                    state=state,
                    artifact_types=deduped_types,
                    assistant_message=assistant_message,
                ),
                options=options,
            ):
                if isinstance(message, ResultMessage):
                    if message.is_error:
                        errors = ", ".join(message.errors or [])
                        raise ProviderIssue(
                            provider="CLAUDE_AGENT_SDK",
                            message=errors or message.result or "Claude Agent SDK 返回错误。",
                        )
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

        if not generated_artifacts:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message="Claude Agent SDK 本轮没有真实生成交付物。",
            )

        return generated_artifacts, generated_versions
