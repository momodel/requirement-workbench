"""轻量的剧本化 AgentRuntime，用于本地 demo 和前端联调。

切换：在环境里设 `USE_MOCK_AGENT_RUNTIME=1` 重启后端即可生效。
触发剧本：发送包含「继续分析」的消息；其它消息走通用兜底回复。

剧本流程：
    前文 → ask_user_question(Q1) → 用户选择 → ask_user_question(Q2) → 用户选择 → 结论
两个问题对齐 docs/客户需求转译台-原始材料/ 里背景说明 + 0328 会议纪要中没定的口径。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import (
    AgentTurnInput,
    AgentTurnResult,
    ArtifactType,
    GeneratedArtifactOutput,
    ProjectState,
    ProjectSummary,
    ProviderReadiness,
)
from .agent_runtime import RuntimeQuestionRegistry


class MockAgentRuntime:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS) -> None:
        self.settings = settings
        self.question_registry = RuntimeQuestionRegistry()
        self._wiki_runtime = None

    # --- 协议兼容 ---

    def attach_wiki_runtime(self, wiki_runtime) -> None:
        self._wiki_runtime = wiki_runtime

    def ensure_available(self) -> None:
        return None

    def get_readiness(self) -> ProviderReadiness:
        return ProviderReadiness(
            provider="MOCK_AGENT",
            status="ready",
            summary="mock 智能体已就绪。发「继续分析」走剧本，其它走兜底回复。",
            detail="去掉环境变量 USE_MOCK_AGENT_RUNTIME 并重启即可切回真实模型。",
            action_label=None,
        )

    async def generate_artifact(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        additional_instruction: str | None = None,
    ) -> GeneratedArtifactOutput:
        return GeneratedArtifactOutput(
            title=f"Mock {artifact_type} 占位",
            summary="mock runtime 生成的占位 artifact，用于 UI 联调。",
            body=(
                "# Mock 文档稿\n\n这是 mock runtime 占位，真实交付物请切回 real runtime 后再生成。"
            )
            if artifact_type == "document"
            else None,
            html=None
            if artifact_type == "document"
            else (
                "<html><body style='font-family:sans-serif;padding:24px'>"
                "<h1>Mock 占位</h1><p>切回真实 runtime 后再生成正式产物。</p>"
                "</body></html>"
            ),
        )

    async def run_turn(
        self,
        turn: AgentTurnInput,
        assistant_message: str | None = None,
    ) -> AsyncIterator[tuple[str, str | AgentTurnResult]]:
        if False:
            yield ("status", "")  # noqa: SIM910 — 维持 async generator 类型

    async def stream_assistant_text(self, turn: AgentTurnInput) -> AsyncIterator[str]:
        if False:
            yield ""

    # --- 主链路 ---

    async def run_streaming_turn(
        self,
        turn: AgentTurnInput,
    ) -> AsyncIterator[tuple[str, dict]]:
        message = (turn.user_message or "").strip()
        if "继续分析" in message:
            async for event in self._scripted_continue_analysis(turn):
                yield event
        else:
            async for event in self._generic_response(turn):
                yield event

    async def _scripted_continue_analysis(
        self,
        turn: AgentTurnInput,
    ) -> AsyncIterator[tuple[str, dict]]:
        project_id = turn.project.id
        full_text = ""

        yield (
            "assistant_status",
            {"phase": "agent_started", "label": "已接收问题，正在启动分析"},
        )
        await asyncio.sleep(0.2)

        async for ev in self._stream_thinking(seconds=1.8):
            yield ev

        # ---------- 前文 ----------
        intro = (
            "我把背景说明、补充说明、群聊整理、3 月 28 日会议纪要这几份材料先过了一遍。"
            "整体方向是想做一个**前期需求分析工作台**，帮售前 / 咨询 / 产品在客户原话和零散材料里"
            "把背景、目标、问题、边界先拎出来，再继续往下沉淀。\n\n"
            "在我把本轮理解写进沉淀之前，有两点想先和你对齐——这两点都是 0328 会议里没定、"
            "但会直接影响后面页面方案怎么拍的。\n\n"
        )
        async for ev in self._stream_text(intro):
            yield ev
        full_text += intro

        # ---------- Question 1 ----------
        q1_id = f"q-{uuid.uuid4().hex[:10]}"
        loop = asyncio.get_running_loop()
        future1: asyncio.Future = loop.create_future()
        self.question_registry.register(project_id, q1_id, future1)
        try:
            yield (
                "ask_user_question",
                {
                    "project_id": project_id,
                    "question_id": q1_id,
                    "question": "第一版工作台的输出物，你想先做到哪一档？",
                    "header": "输出口径",
                    "options": [
                        {
                            "label": "需求结论 + 待确认问题清单",
                            "description": "纯文本沉淀，方便内部继续讨论；最轻量",
                        },
                        {
                            "label": "再加 MVP 方向 + 页面结构草图",
                            "description": "形成比较完整的初步方案，但不出 PRD",
                        },
                        {
                            "label": "完整 PRD 文档",
                            "description": "接近正式交付物，本期投入会比较重",
                        },
                    ],
                    "multi_select": False,
                },
            )
            answer1 = await asyncio.wait_for(
                future1,
                timeout=self.settings.ask_user_question_timeout_seconds,
            )
        finally:
            self.question_registry.unregister(project_id, q1_id)

        labels1 = list(answer1.get("selected_labels") or [])
        free1 = answer1.get("free_text")
        yield (
            "ask_user_question_answered",
            {
                "project_id": project_id,
                "question_id": q1_id,
                "selected_labels": labels1,
                "free_text": free1,
                "timed_out": False,
            },
        )

        async for ev in self._stream_thinking(seconds=1.2):
            yield ev

        # ---------- Question 2 ----------
        q2_id = f"q-{uuid.uuid4().hex[:10]}"
        future2: asyncio.Future = loop.create_future()
        self.question_registry.register(project_id, q2_id, future2)
        try:
            yield (
                "ask_user_question",
                {
                    "project_id": project_id,
                    "question_id": q2_id,
                    "question": "第一版要支持哪些类型的输入材料？",
                    "header": "材料范围",
                    "options": [
                        {
                            "label": "纯文本（聊天记录、会议纪要、Word/Markdown）",
                            "description": "最少口径，先把主链路跑通",
                        },
                        {
                            "label": "再加 截图 / 图片",
                            "description": "覆盖会议白板、产品截图等常见现场",
                        },
                        {
                            "label": "再加 音频",
                            "description": "把会议录音也接进来；本期投入会更大",
                        },
                    ],
                    "multi_select": True,
                },
            )
            answer2 = await asyncio.wait_for(
                future2,
                timeout=self.settings.ask_user_question_timeout_seconds,
            )
        finally:
            self.question_registry.unregister(project_id, q2_id)

        labels2 = list(answer2.get("selected_labels") or [])
        free2 = answer2.get("free_text")
        yield (
            "ask_user_question_answered",
            {
                "project_id": project_id,
                "question_id": q2_id,
                "selected_labels": labels2,
                "free_text": free2,
                "timed_out": False,
            },
        )

        async for ev in self._stream_thinking(seconds=1.5):
            yield ev

        # ---------- 结论 ----------
        conclusion = (
            f"\n\n本轮收敛：\n"
            f"- **输出物**：{self._format_choice(labels1, free1)}\n"
            f"- **材料范围**：{self._format_choice(labels2, free2)}\n"
            f"\n基于这两点，第一版可以这样切：\n\n"
            "1. **核心动作**：导入材料 → 自动按类型归档（聊天 / 会议 / 文档 / 截图 …） → "
            "抽取关键段落 → 在工作台里按维度（背景 / 目标 / 问题 / 边界 / 待确认）人工确认 → "
            "输出选定档位的交付物。\n"
            "2. **MVP 边界**：先不做权限、不做版本化、不做对外客户视图，集中验证「乱材料 → "
            "结构化结论」这条主链路。\n"
            "3. **下一步**：等你确认上面切法没问题，我把页面结构草图拟一版，"
            "然后把这两个口径写进本轮沉淀。\n"
        )
        async for ev in self._stream_text(conclusion):
            yield ev
        full_text += conclusion

        yield (
            "final_message",
            {"text": full_text, "citations": []},
        )
        yield (
            "assistant_status",
            {"phase": "agent_completed", "label": "本轮分析已完成"},
        )

    async def _generic_response(
        self,
        turn: AgentTurnInput,
    ) -> AsyncIterator[tuple[str, dict]]:
        yield (
            "assistant_status",
            {"phase": "agent_started", "label": "已接收问题，正在启动分析"},
        )
        text = (
            "（mock 模式）当前后端走的是剧本化 mock runtime。"
            "发送包含「继续分析」的消息可以触发完整的两轮提问 + 结论剧本；"
            "其它消息只会得到这条占位回复。\n\n"
            "去掉环境变量 `USE_MOCK_AGENT_RUNTIME` 再重启后端可以切回真实模型。"
        )
        async for ev in self._stream_text(text):
            yield ev
        yield (
            "final_message",
            {"text": text, "citations": []},
        )
        yield (
            "assistant_status",
            {"phase": "agent_completed", "label": "本轮分析已完成"},
        )

    # --- helpers ---

    async def _stream_text(
        self,
        text: str,
        chunk_size: int = 6,
        delay: float = 0.03,
    ) -> AsyncIterator[tuple[str, dict]]:
        i = 0
        while i < len(text):
            piece = text[i : i + chunk_size]
            yield ("message_chunk", {"text": piece})
            await asyncio.sleep(delay)
            i += chunk_size

    async def _stream_thinking(
        self,
        seconds: float = 1.5,
        beat_interval: float = 0.5,
    ) -> AsyncIterator[tuple[str, dict]]:
        """模拟"AI 正在思考"——按 beat_interval 节拍刷 assistant_status，
        总时长约 seconds。前端会持续显示思考态状态条。"""
        elapsed = 0.0
        while elapsed < seconds:
            yield (
                "assistant_status",
                {"phase": "model_thinking", "label": "AI 正在思考"},
            )
            await asyncio.sleep(beat_interval)
            elapsed += beat_interval

    @staticmethod
    def _format_choice(labels: list[str], free_text: str | None) -> str:
        pieces = []
        if labels:
            pieces.append("、".join(str(label) for label in labels))
        if free_text:
            pieces.append(free_text)
        if not pieces:
            return "未选 / 跳过"
        return " + ".join(pieces)
