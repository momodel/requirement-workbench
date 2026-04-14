from pydantic import BaseModel


class ProjectSummary(BaseModel):
    id: str
    name: str
    scenario_type: str
    summary: str
    status: str
    created_at: str
    updated_at: str
    seed_key: str | None = None


class SourceRecord(BaseModel):
    id: str
    project_id: str
    name: str
    source_kind: str
    upload_kind: str
    parse_status: str
    parse_summary: str | None = None
    sync_status: str = "pending"


class StateItem(BaseModel):
    id: str
    title: str
    body: str


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
