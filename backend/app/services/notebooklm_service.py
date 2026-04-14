from dataclasses import dataclass
from typing import Protocol


@dataclass
class EvidenceResult:
    summary: str
    citations: list[str]


class EvidenceRuntime(Protocol):
    def query(self, project_id: str, question: str) -> EvidenceResult: ...


class MockNotebookLMService:
    def query(self, project_id: str, question: str) -> EvidenceResult:
        return EvidenceResult(
            summary=f"{project_id} 的资料问答占位结果：{question}",
            citations=[]
        )
