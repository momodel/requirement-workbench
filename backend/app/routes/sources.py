import base64

from fastapi import APIRouter, HTTPException

from ..models import SourceRecord
from ..services.notebooklm_service import import_source
from ..services.project_catalog import get_source, list_sources
from ..services.source_ingestion import ingest_file_source, ingest_text_source, ingest_url_source


router = APIRouter(prefix="/api/projects/{project_id}/sources", tags=["sources"])


@router.get("", response_model=list[SourceRecord])
def list_sources_route(project_id: str) -> list[SourceRecord]:
    return list_sources(project_id)


@router.post("", response_model=SourceRecord)
def create_source_route(project_id: str, payload: dict) -> SourceRecord:
    upload_kind = payload.get("upload_kind")
    name = payload.get("name") or "未命名资料"
    record: SourceRecord | None = None

    if upload_kind == "text":
        text = payload.get("text", "")
        record = ingest_text_source(project_id=project_id, name=name, text=text)

    elif upload_kind == "url":
        url = payload.get("url", "")
        record = ingest_url_source(project_id=project_id, name=name, url=url)

    elif upload_kind == "file":
        content_base64 = payload.get("content_base64")
        if not content_base64:
            raise HTTPException(status_code=400, detail="Missing content_base64")

        try:
            content = base64.b64decode(content_base64)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid file payload") from exc

        record = ingest_file_source(
            project_id=project_id,
            name=name,
            content=content,
            source_kind=payload.get("source_kind"),
            mime_type=payload.get("mime_type"),
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported upload_kind")

    try:
        if record.normalized_path:
            import_source(
                project_id=project_id,
                source_id=record.id,
                normalized_path=record.normalized_path,
                source_name=record.name,
            )
    except FileNotFoundError:
        pass

    return get_source(project_id, record.id) or record
