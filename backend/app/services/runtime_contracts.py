from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Protocol

from ..models import (
    AgentTurnInput,
    AgentTurnResult,
    ArtifactType,
    EvidenceResult,
    GeneratedArtifactOutput,
    ProjectState,
    ProjectSummary,
)


class AgentRuntime(Protocol):
    def ensure_available(self) -> None: ...

    def stream_assistant_text(
        self,
        turn: AgentTurnInput,
    ) -> AsyncIterator[str]: ...

    def run_turn(
        self,
        turn: AgentTurnInput,
        assistant_message: str | None = None,
    ) -> AsyncIterator[tuple[str, str | AgentTurnResult]]: ...

    async def generate_artifact(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
    ) -> GeneratedArtifactOutput: ...


class EvidenceRuntime(Protocol):
    def ensure_available(self) -> Path: ...

    def query(self, project_id: str, question: str) -> EvidenceResult: ...
