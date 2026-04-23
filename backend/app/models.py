from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, model_serializer, model_validator


STATE_CATEGORIES = (
    "current_understanding",
    "pending_items",
    "confirmed_items",
    "conflict_items",
    "mvp_items",
    "versions",
    "artifacts",
)

StateCategory = Literal[
    "current_understanding",
    "pending_items",
    "confirmed_items",
    "conflict_items",
    "mvp_items",
    "versions",
    "artifacts",
]

ArtifactType = Literal["document", "page_solution", "interaction_flow"]
UploadKind = Literal["text", "file", "url", "seed"]


class ProjectSummary(BaseModel):
    id: str
    name: str
    scenario_type: str
    summary: str
    status: str
    created_at: str
    updated_at: str
    seed_key: str | None = None


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scenario_type: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=1000)


class KnowledgeBaseRecord(BaseModel):
    id: str
    project_id: str
    provider: str
    external_knowledge_base_id: str
    display_name: str | None = None
    description: str | None = None
    status: str
    status_error: str | None = None
    created_at: str
    updated_at: str


class SourceChunkRecord(BaseModel):
    id: str
    project_id: str
    source_id: str
    knowledge_base_id: str | None = None
    chunk_order: int
    modality: str
    content: str
    locator_json: str | None = None
    content_hash: str
    embedding_status: str = "pending"
    index_error: str | None = None
    indexed_at: str | None = None
    created_at: str
    updated_at: str


class EvidenceHit(BaseModel):
    source_id: str | None = None
    source_chunk_id: str | None = None
    citation_title: str | None = None
    snippet: str
    score: float | None = None


class ProviderReadiness(BaseModel):
    provider: str
    status: str
    summary: str
    detail: str | None = None
    action_label: str | None = None


class ProjectReadiness(BaseModel):
    project_id: str
    claude: ProviderReadiness
    evidence: ProviderReadiness
    knowledge_base: KnowledgeBaseRecord | None = None

class GlobalReadiness(BaseModel):
    claude: ProviderReadiness
    evidence: ProviderReadiness

class SourceRecord(BaseModel):
    id: str
    project_id: str
    name: str
    source_kind: str
    upload_kind: str
    storage_path: str | None = None
    normalized_path: str | None = None
    index_input_mode: str | None = None
    normalize_status: str
    normalize_summary: str | None = None
    index_status: str = "pending"
    index_error: str | None = None
    created_at: str

    @model_serializer(mode="wrap")
    def serialize_with_legacy_source_fields(self, serializer: Any) -> dict[str, Any]:
        payload = serializer(self)
        payload["notebook_import_mode"] = self.index_input_mode
        payload["parse_status"] = self.normalize_status
        payload["parse_summary"] = self.normalize_summary
        payload["sync_status"] = self.index_status
        payload["sync_error"] = self.index_error
        return payload

    def model_dump_neutral(self) -> dict[str, Any]:
        payload = self.model_dump()
        payload.pop("notebook_import_mode", None)
        payload.pop("parse_status", None)
        payload.pop("parse_summary", None)
        payload.pop("sync_status", None)
        payload.pop("sync_error", None)
        return payload

    def model_dump_legacy(self) -> dict[str, Any]:
        payload = self.model_dump()
        payload["notebook_import_mode"] = self.index_input_mode
        payload["parse_status"] = self.normalize_status
        payload["parse_summary"] = self.normalize_summary
        payload["sync_status"] = self.index_status
        payload["sync_error"] = self.index_error
        return payload


class MessageRecord(BaseModel):
    id: str
    role: str
    content: str
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    stream_group_id: str | None = None


class StateItem(BaseModel):
    id: str
    title: str
    body: str
    status: str = "active"
    category: str | None = None
    updated_at: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class ProjectState(BaseModel):
    current_understanding: list[StateItem]
    pending_items: list[StateItem]
    confirmed_items: list[StateItem]
    conflict_items: list[StateItem]
    mvp_items: list[StateItem]
    versions: list[StateItem]
    artifacts: list[StateItem]


class ArtifactRecord(BaseModel):
    id: str
    project_id: str
    artifact_type: str
    title: str
    summary: str
    status: str
    content_format: str
    storage_path: str | None = None
    preview_url: str | None = None
    body: str | None = None
    updated_at: str


class ChatCitation(BaseModel):
    title: str
    snippet: str | None = None
    source_id: str | None = None


class ChatStreamRequest(BaseModel):
    message: str = Field(min_length=1)
    selected_source_ids: list[str] = Field(default_factory=list)
    request_artifact_types: list[ArtifactType] = Field(default_factory=list)
    client_context: dict[str, Any] | None = None


class ArtifactGenerateRequest(BaseModel):
    artifact_type: ArtifactType


class GeneratedArtifactOutput(BaseModel):
    title: str
    summary: str
    body: str | None = None
    html: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_missing_summary(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        if normalized.get("summary"):
            return normalized

        body = normalized.get("body")
        html = normalized.get("html")
        fallback = body or html or ""
        fallback_text = " ".join(str(fallback).split())
        if fallback_text:
            normalized["summary"] = fallback_text[:120]
        return normalized


class SourceCreateInput(BaseModel):
    name: str
    upload_kind: UploadKind
    text_content: str | None = None
    source_url: str | None = None


class SourceUpsert(BaseModel):
    title: str
    body: str
    source_ids: list[str] = Field(default_factory=list)
    status: str = "active"


class AgentStructuredOutput(BaseModel):
    assistant_message: str
    citations: list[ChatCitation] = Field(default_factory=list)
    current_understanding: list[SourceUpsert] = Field(default_factory=list)
    pending_items: list[SourceUpsert] = Field(default_factory=list)
    confirmed_items: list[SourceUpsert] = Field(default_factory=list)
    conflict_items: list[SourceUpsert] = Field(default_factory=list)
    mvp_items: list[SourceUpsert] = Field(default_factory=list)
    version_summary: str | None = None
    request_artifacts: list[ArtifactType] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_nullable_lists(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        normalized = dict(value)
        for key in (
            "citations",
            "current_understanding",
            "pending_items",
            "confirmed_items",
            "conflict_items",
            "mvp_items",
        ):
            if normalized.get(key) is None:
                normalized[key] = []

        request_artifacts = normalized.get("request_artifacts")
        if request_artifacts is None or request_artifacts == "":
            normalized["request_artifacts"] = []
        return normalized


@dataclass(slots=True)
class ProviderIssue(Exception):
    provider: str
    message: str
    status_code: int = 503

    def __str__(self) -> str:
        return f"{self.provider}: {self.message}"


@dataclass(slots=True)
class EvidenceResult:
    summary: str
    citations: list[ChatCitation] = field(default_factory=list)
    sync_status: str = "synced"


@dataclass(slots=True)
class AgentTurnInput:
    project: ProjectSummary
    state: ProjectState
    user_message: str
    selected_source_ids: list[str]
    source_summaries: list[str]
    evidence_summary: str
    evidence_citations: list[ChatCitation]
    request_artifact_types: list[ArtifactType]
    recent_messages: list[MessageRecord] = field(default_factory=list)


@dataclass(slots=True)
class AgentTurnResult:
    assistant_message: str
    citations: list[ChatCitation]
    state_updates: dict[StateCategory, list[SourceUpsert]]
    version_summary: str | None
    request_artifacts: list[ArtifactType]
    raw_result: dict[str, Any] | None = None
