try:
    from pydantic import BaseModel
except ModuleNotFoundError:
    class BaseModel:
        def __init__(self, **kwargs):
            annotations = getattr(self, "__annotations__", {})

            for field_name in annotations:
                if field_name in kwargs:
                    value = kwargs[field_name]
                elif hasattr(type(self), field_name):
                    value = getattr(type(self), field_name)
                else:
                    raise TypeError(f"Missing required field: {field_name}")

                setattr(self, field_name, value)

        def model_dump(self) -> dict:
            return {
                field_name: getattr(self, field_name)
                for field_name in getattr(self, "__annotations__", {})
            }


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
    storage_path: str | None = None
    normalized_path: str | None = None
    parse_status: str
    parse_summary: str | None = None
    sync_status: str = "pending"


class CitationRecord(BaseModel):
    source_id: str
    source_name: str
    excerpt: str
    quote: str | None = None


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
    storage_path: str | None = None
