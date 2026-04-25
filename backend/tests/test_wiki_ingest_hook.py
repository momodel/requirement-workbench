from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.config import AppSettings
from app.db import init_db
from app.models import (
    CreateProjectRequest,
    ProviderReadiness,
    SourceRecord,
    WikiMaintenanceResult,
)
from app.services.project_catalog import ProjectCatalog
from app.services.wiki_runtime import ClaudeWikiRuntime


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
    )


class _MaintainerStub:
    def __init__(self, *, result: WikiMaintenanceResult | None = None, raise_exc: Exception | None = None):
        self.result = result
        self.raise_exc = raise_exc
        self.calls: list[dict] = []

    async def run(self, project_id: str, *, trigger_kind: str, source_id=None, version_summary=None):
        self.calls.append(
            {
                "project_id": project_id,
                "trigger_kind": trigger_kind,
                "source_id": source_id,
                "version_summary": version_summary,
            }
        )
        if self.raise_exc:
            raise self.raise_exc
        return self.result or WikiMaintenanceResult(
            project_id=project_id,
            status="maintained",
            pages_changed=["pages/source-intake.md"],
            log_entry="ok",
            trigger_kind=trigger_kind,
        )

    async def run_health_probe(self, project_id: str):
        return WikiMaintenanceResult(
            project_id=project_id, status="maintained", trigger_kind="health_probe"
        )


def setup_runtime(tmp_path: Path, *, maintainer):
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="wiki ingest test", scenario_type="对账", summary="ingest hook"
        )
    )
    source = catalog.create_source(
        project_id=project.id,
        name="资料",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        normalize_status="parsed",
        normalize_summary="测试摘要",
        index_status="indexed",
        index_error=None,
    )
    runtime = ClaudeWikiRuntime(
        settings,
        catalog=catalog,
        sdk_readiness_probe=lambda: ProviderReadiness(
            provider="CLAUDE_AGENT_SDK", status="ready", summary="ok"
        ),
        maintainer=maintainer,
    )
    return runtime, catalog, project, source


async def _drive(runtime, project_id: str, source_id: str):
    # schedule must be invoked from inside a running loop so create_task succeeds
    runtime.schedule_maintain_after_ingest(project_id, source_id)
    # yield control until the scheduled task completes
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def test_schedule_marks_maintaining_then_maintained(tmp_path: Path):
    maintainer = _MaintainerStub()
    runtime, catalog, project, source = setup_runtime(tmp_path, maintainer=maintainer)

    asyncio.run(_drive(runtime, project.id, source.id))

    final = catalog.get_source(source.id)
    assert final is not None
    assert final.wiki_sync_status == "maintained"
    assert final.wiki_error is None
    assert final.wiki_maintained_at is not None
    # index_status untouched
    assert final.index_status == "indexed"
    # maintainer was called with right args
    assert maintainer.calls == [
        {
            "project_id": project.id,
            "trigger_kind": "source_ingested",
            "source_id": source.id,
            "version_summary": None,
        }
    ]


def test_maintainer_failure_does_not_flip_index_status(tmp_path: Path):
    maintainer = _MaintainerStub(
        result=WikiMaintenanceResult(
            project_id="ignored",
            status="failed",
            error="LLM 拒绝写文件",
            trigger_kind="source_ingested",
        )
    )
    runtime, catalog, project, source = setup_runtime(tmp_path, maintainer=maintainer)

    asyncio.run(_drive(runtime, project.id, source.id))

    final = catalog.get_source(source.id)
    assert final is not None
    assert final.index_status == "indexed"  # RAG state untouched
    assert final.wiki_sync_status == "failed"
    assert "LLM 拒绝" in (final.wiki_error or "")


def test_maintainer_exception_records_failed_state(tmp_path: Path):
    maintainer = _MaintainerStub(raise_exc=RuntimeError("SDK boom"))
    runtime, catalog, project, source = setup_runtime(tmp_path, maintainer=maintainer)

    asyncio.run(_drive(runtime, project.id, source.id))

    final = catalog.get_source(source.id)
    assert final is not None
    # Even with an exception inside maintainer.run, the runner catches it and records "failed"
    # via the wiki_runtime exception handler (status="failed", error contains exc message).
    # But maintain_after_ingest itself calls maintainer.run which raises; this propagates to
    # the runner's outer except. So status should be "failed" with error containing "SDK boom".
    assert final.index_status == "indexed"
    assert final.wiki_sync_status == "failed"
    assert "SDK boom" in (final.wiki_error or "")


def test_schedule_no_maintainer_records_skipped(tmp_path: Path):
    runtime, catalog, project, source = setup_runtime(tmp_path, maintainer=None)

    asyncio.run(_drive(runtime, project.id, source.id))

    final = catalog.get_source(source.id)
    assert final is not None
    assert final.wiki_sync_status == "skipped"
    assert "WikiMaintainer" in (final.wiki_error or "")
