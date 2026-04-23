from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from ..models import ProviderIssue

router = APIRouter(prefix="/api/projects/{project_id}/sources", tags=["sources"])


def _resolve_index_outcome(services, project_id: str, normalized_source) -> tuple[str, str | None]:
    if normalized_source.normalize_status == "pending":
        detail = normalized_source.normalize_summary or "资料已记录，但还没有完成文本标准化。"
        return "normalization_pending", detail

    if normalized_source.normalize_status != "parsed":
        detail = normalized_source.normalize_summary or "资料标准化失败。"
        return "normalization_failed", f"资料标准化失败，尚未进入项目知识库。{detail}"

    try:
        evidence = services.evidence_runtime.get_global_readiness()
    except ProviderIssue as exc:
        return "error", exc.message

    if evidence.status != "ready":
        return evidence.status, evidence.detail or evidence.summary

    knowledge_base = services.catalog.get_knowledge_base(
        project_id=project_id,
        provider=evidence.provider,
    )
    if knowledge_base is None:
        return "knowledge_base_missing", "资料已标准化，但当前项目还没有初始化项目内知识库。"

    return "pending", "资料已标准化，正在写入项目知识库。"


def _create_source_record(
    services,
    project_id: str,
    upload_kind: str,
    name: str,
    storage_path,
    normalized_source,
):
    index_status, index_error = _resolve_index_outcome(services, project_id, normalized_source)
    source_record = services.catalog.create_source(
        project_id=project_id,
        name=name,
        source_kind=normalized_source.source_kind,
        upload_kind=upload_kind,
        storage_path=storage_path,
        normalized_path=normalized_source.normalized_path,
        notebook_import_mode=normalized_source.index_input_mode,
        parse_status=normalized_source.normalize_status,
        parse_summary=normalized_source.normalize_summary,
        sync_status=index_status,
        sync_error=index_error,
    )
    if index_status == "pending":
        source_record = _run_source_index_operation(
            services,
            project_id=project_id,
            source_id=source_record.id,
            operation="index",
            raise_on_error=False,
        )
    return source_record


def _run_source_index_operation(
    services,
    *,
    project_id: str,
    source_id: str,
    operation: str,
    raise_on_error: bool,
):
    source = services.catalog.get_source(source_id)
    if not source:
        raise LookupError("Source not found")

    services.catalog.update_source_sync_status(
        source_id=source_id,
        sync_status="indexing",
        sync_error=None,
    )
    try:
        if operation == "reindex":
            services.evidence_runtime.reindex_source(project_id, source_id)
        else:
            services.evidence_runtime.index_source(project_id, source_id)
    except ProviderIssue as exc:
        failed_source = services.catalog.update_source_sync_status(
            source_id=source_id,
            sync_status="index_failed",
            sync_error=exc.message,
        )
        if raise_on_error:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        return failed_source

    return services.catalog.update_source_sync_status(
        source_id=source_id,
        sync_status="indexed",
        sync_error=None,
    )


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
        storage_path, normalized_source = source_ingestion.ingest_text(project_id, name, text_content)
        return _create_source_record(
            services,
            project_id,
            upload_kind,
            name,
            storage_path,
            normalized_source,
        )
    elif upload_kind == "url":
        if not source_url:
            raise HTTPException(status_code=400, detail="source_url is required for url upload")
        storage_path, normalized_source = source_ingestion.ingest_url(project_id, name, source_url)
        return _create_source_record(
            services,
            project_id,
            upload_kind,
            name,
            storage_path,
            normalized_source,
        )
    elif upload_kind == "file":
        upload_files = files or ([file] if file is not None else [])
        if not upload_files:
            raise HTTPException(status_code=400, detail="file or files is required for file upload")

        created_sources = []
        for upload in upload_files:
            safe_name = Path(upload.filename or name).name
            storage_path, normalized_source = source_ingestion.ingest_file(
                project_id,
                safe_name,
                await upload.read(),
            )
            created_sources.append(
                _create_source_record(
                    services,
                    project_id,
                    upload_kind,
                    safe_name,
                    storage_path,
                    normalized_source,
                )
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
        services.evidence_runtime.delete_source(project_id, source_id)
    except (ProviderIssue, LookupError, ValueError):
        # 当前主链路不能因为 provider 清理失败而阻断本地删除。
        pass

    try:
        services.catalog.replace_source_chunks(
            project_id=project_id,
            source_id=source_id,
            chunks=[],
        )
    except (LookupError, ValueError):
        pass

    try:
        deleted = services.catalog.delete_source(source_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "id": deleted.id,
        "project_id": deleted.project_id,
        "name": deleted.name,
        "deleted": True,
    }


@router.post("/{source_id}/reindex", status_code=status.HTTP_200_OK)
def reindex_source(project_id: str, source_id: str, request: Request):
    services = request.app.state.services
    project = services.catalog.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    source = services.catalog.get_source(source_id)
    if not source or source.project_id != project_id:
        raise HTTPException(status_code=404, detail="Source not found")

    try:
        return _run_source_index_operation(
            services,
            project_id=project_id,
            source_id=source_id,
            operation="reindex",
            raise_on_error=True,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
