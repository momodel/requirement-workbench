from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator, Protocol

from ..models import (
    AgentTurnInput,
    AgentTurnResult,
    ArtifactType,
    EvidenceResult,
    GeneratedArtifactOutput,
    KnowledgeBaseRecord,
    ProjectReadiness,
    ProjectState,
    ProjectSummary,
    ProviderReadiness,
    SourceChunkRecord,
    WikiMaintenanceResult,
    WikiPage,
    WikiPageMeta,
    WikiRecord,
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

    def get_global_readiness(self) -> ProviderReadiness: ...

    def get_project_readiness(
        self,
        project_id: str,
        claude: ProviderReadiness | None = None,
    ) -> ProviderReadiness | ProjectReadiness: ...

    def ensure_project_knowledge_base(self, project_id: str) -> KnowledgeBaseRecord: ...

    def index_source(
        self,
        project_id: str,
        source_id: str,
    ) -> list[SourceChunkRecord]: ...

    def delete_source(self, project_id: str, source_id: str) -> None: ...

    def delete_project(self, project_id: str) -> None: ...

    def reindex_source(
        self,
        project_id: str,
        source_id: str,
    ) -> list[SourceChunkRecord]: ...

    def query(
        self,
        project_id: str,
        question: str,
        *,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult: ...


class WikiRuntime(Protocol):
    def ensure_available(self) -> Path: ...

    def get_global_readiness(self) -> ProviderReadiness: ...

    def get_project_readiness(
        self,
        project_id: str,
        claude: ProviderReadiness | None = None,
    ) -> ProviderReadiness: ...

    def ensure_project_wiki(self, project_id: str) -> WikiRecord: ...

    def list_pages(self, project_id: str) -> list[WikiPageMeta]: ...

    def read_page(self, project_id: str, slug: str) -> WikiPage: ...

    async def maintain_after_ingest(
        self,
        project_id: str,
        source_id: str,
    ) -> WikiMaintenanceResult: ...

    async def maintain_after_checkpoint(
        self,
        project_id: str,
        version_summary: str | None = None,
    ) -> WikiMaintenanceResult: ...
