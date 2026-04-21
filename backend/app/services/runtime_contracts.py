from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator, Protocol

from ..models import (
    AgentTurnInput,
    ArtifactRecord,
    ArtifactType,
    EvidenceResult,
    GeneratedArtifactOutput,
    ProjectState,
    ProjectSummary,
    StateItem,
)


class AgentRuntime(Protocol):
    def ensure_available(self) -> None: ...

    def run_streaming_turn(
        self,
        turn: AgentTurnInput,
    ) -> AsyncIterator[tuple[str, Any]]: ...

    async def generate_artifact(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        additional_instruction: str | None = None,
    ) -> GeneratedArtifactOutput: ...

    async def commit_artifacts(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_types: list[ArtifactType],
        assistant_message: str | None = None,
    ) -> tuple[list[ArtifactRecord], list[StateItem]]: ...


class EvidenceRuntime(Protocol):
    def ensure_available(self) -> Path: ...

    def query(
        self,
        project_id: str,
        question: str,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult: ...
