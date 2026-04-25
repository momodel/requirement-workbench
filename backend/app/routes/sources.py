from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

router = APIRouter(prefix="/api/projects/{project_id}/sources", tags=["sources"])


def _resolve_sync_status(services, project_id: str) -> tuple[str, str]:
    return "indexed", "资料已入库，并已纳入 LLM Wiki 知识库上下文。"


def _create_source_record(services, project_id: str, upload_kind: str, name: str, storage_path, normalized):
    sync_status, sync_error = _resolve_sync_status(services, project_id)
    source_record = services.catalog.create_source(
        project_id=project_id,
        name=name,
        source_kind=normalized.source_kind,
        upload_kind=upload_kind,
        storage_path=storage_path,
        normalized_path=normalized.normalized_path,
        source_import_mode=normalized.source_import_mode,
        parse_status=normalized.parse_status,
        parse_summary=normalized.parse_summary,
        sync_status=sync_status,
        sync_error=sync_error,
    )
    project = services.catalog.get_project(project_id)
    if project and services.knowledge_wiki:
        services.knowledge_wiki.record_source_intake(project, services.catalog.list_sources(project_id))
    return source_record


@router.get("")
def list_sources(project_id: str, request: Request):
    project = request.app.state.services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return request.app.state.services.catalog.list_sources(project_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_source(
    project_id: str,
    request: Request,
    upload_kind: str = Form(...),
    name: str = Form(...),
    text_content: str | None = Form(None),
    source_url: str | None = Form(None),
    file: UploadFile | None = File(None),
    files: list[UploadFile] | None = File(None),
):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    source_ingestion = services.source_ingestion

    if upload_kind == "text":
        if not text_content:
            raise HTTPException(status_code=400, detail="text_content is required for text upload")
        storage_path, normalized = source_ingestion.ingest_text(project_id, name, text_content)
        return _create_source_record(services, project_id, upload_kind, name, storage_path, normalized)
    elif upload_kind == "url":
        if not source_url:
            raise HTTPException(status_code=400, detail="source_url is required for url upload")
        storage_path, normalized = source_ingestion.ingest_url(project_id, name, source_url)
        return _create_source_record(services, project_id, upload_kind, name, storage_path, normalized)
    elif upload_kind == "file":
        upload_files = files or ([file] if file is not None else [])
        if not upload_files:
            raise HTTPException(status_code=400, detail="file or files is required for file upload")

        created_sources = []
        for upload in upload_files:
            safe_name = Path(upload.filename or name).name
            storage_path, normalized = source_ingestion.ingest_file(
                project_id,
                safe_name,
                await upload.read(),
            )
            created_sources.append(
                _create_source_record(services, project_id, upload_kind, safe_name, storage_path, normalized)
            )
        return created_sources if len(created_sources) > 1 or files else created_sources[0]
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported upload_kind: {upload_kind}")


@router.delete("/{source_id}", status_code=status.HTTP_200_OK)
def delete_source(project_id: str, source_id: str, request: Request):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    source = services.catalog.get_source(source_id)
    if not source or source.project_id != project_id:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        deleted = services.catalog.delete_source(source_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    services.knowledge_wiki.record_source_intake(project, services.catalog.list_sources(project_id))

    return {
        "id": deleted.id,
        "project_id": deleted.project_id,
        "name": deleted.name,
        "deleted": True,
    }


@router.post("/{source_id}/retry-sync", status_code=status.HTTP_200_OK)
def retry_source_sync(project_id: str, source_id: str, request: Request):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    source = services.catalog.get_source(source_id)
    if not source or source.project_id != project_id:
        raise HTTPException(status_code=404, detail="Source not found")

    services.knowledge_wiki.record_source_intake(project, services.catalog.list_sources(project_id))
    return services.catalog.update_source_sync_status(
        source_id=source_id,
        sync_status="indexed",
        sync_error="资料已重新纳入 LLM Wiki 知识库上下文。",
    )
