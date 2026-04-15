from dataclasses import dataclass, field
from typing import Protocol

from .project_state import CATEGORY_KEYS


@dataclass
class AgentResponse:
    message: str
    citations: list[dict[str, str]]
    state_patches: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    version_summary: str | None = None
    artifact_requests: list[str] = field(default_factory=list)


class AgentRuntime(Protocol):
    def respond(
        self,
        *,
        project_summary: str,
        message: str,
        evidence_summary: str,
        citations: list[dict[str, str]],
        current_state_counts: dict[str, int],
        request_artifact_types: list[str] | None = None,
    ) -> AgentResponse: ...


class ClaudeAgentRuntime:
    def respond(
        self,
        *,
        project_summary: str,
        message: str,
        evidence_summary: str,
        citations: list[dict[str, str]],
        current_state_counts: dict[str, int],
        request_artifact_types: list[str] | None = None,
    ) -> AgentResponse:
        focus = "逐笔差异识别"
        if "退款" in message or "冲销" in message:
            focus = "退款与冲销口径"
        elif "科目" in message:
            focus = "业务字段到财务科目的映射"

        state_patches: dict[str, list[dict[str, str]]] = {key: [] for key in CATEGORY_KEYS}
        state_patches["current_understanding"].append(
            {
                "title": f"当前焦点收敛到{focus}",
                "body": f"{project_summary}。结合资料可先把问题定义为：{focus}，并保留人工复核闭环。",
            }
        )
        state_patches["pending_items"].append(
            {
                "title": "待确认特殊交易处理范围",
                "body": "需要继续确认退款、冲销、作废单是否纳入一期，以及是否允许只提示不自动归因。",
            }
        )
        if "不自动改账" in message:
            state_patches["confirmed_items"].append(
                {
                    "title": "一期不自动改账",
                    "body": "系统先输出差异识别和归因建议，最终处理动作仍由财务或对账专员确认。",
                }
            )
            state_patches["mvp_items"].append(
                {
                    "title": "MVP 保留人工复核",
                    "body": "一期能力包围绕差异发现、规则映射、异常归类和人工确认，不直接改账。",
                }
            )

        citation_hint = f"本轮引用了 {len(citations)} 份资料。" if citations else "当前没有直接引用到资料，建议补充来源。"
        message_lines = [
            f"我先把这一轮收敛为“{focus}”。",
            evidence_summary,
            citation_hint,
            "下一步建议继续确认特殊交易规则和人工处理边界。",
        ]

        filtered_patches = {
            key: items
            for key, items in state_patches.items()
            if items
        }
        version_summary = (
            f"完成一轮需求分析，新增 {sum(len(items) for items in filtered_patches.values())} 条项目状态沉淀。"
        )

        return AgentResponse(
            message=" ".join(message_lines),
            citations=citations,
            state_patches=filtered_patches,
            version_summary=version_summary,
            artifact_requests=request_artifact_types or [],
        )

MockClaudeAgentRuntime = ClaudeAgentRuntime
runtime = ClaudeAgentRuntime()
