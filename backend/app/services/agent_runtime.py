from dataclasses import dataclass
from typing import Protocol


@dataclass
class AgentResponse:
    message: str
    citations: list[str]


class AgentRuntime(Protocol):
    def respond(self, message: str) -> AgentResponse: ...


class MockClaudeAgentRuntime:
    def respond(self, message: str) -> AgentResponse:
        return AgentResponse(
            message=f"已收到输入：{message}。当前是一期骨架阶段，后续会替换成 Claude Agent SDK 的真实实现。",
            citations=[]
        )
