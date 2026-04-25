from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from app.config import AppSettings
from app.db import init_db
from app.models import (
    CreateProjectRequest,
    ProviderIssue,
    ProviderReadiness,
)
from app.services.project_catalog import ProjectCatalog
from app.services.wiki_runtime import WIKI_PROVIDER, ClaudeWikiRuntime


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
    )


class _FakeMaintainer:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run(self, project_id: str, *, trigger_kind: str, source_id=None, version_summary=None):
        from app.models import WikiMaintenanceResult

        self.calls.append(
            {
                "project_id": project_id,
                "trigger_kind": trigger_kind,
                "source_id": source_id,
                "version_summary": version_summary,
            }
        )
        return WikiMaintenanceResult(
            project_id=project_id,
            status="maintained",
            pages_changed=["pages/overview.md"],
            log_entry=f"fake {trigger_kind}",
            trigger_kind=trigger_kind,
        )

    async def run_health_probe(self, project_id: str):
        from app.models import WikiMaintenanceResult

        return WikiMaintenanceResult(
            project_id=project_id,
            status="maintained",
            pages_changed=[".health"],
            log_entry="fake probe ok",
            trigger_kind="health_probe",
        )


def make_runtime(
    tmp_path: Path,
    *,
    sdk_status: str = "ready",
    maintainer=None,
) -> tuple[ClaudeWikiRuntime, ProjectCatalog]:
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)

    def fake_probe() -> ProviderReadiness:
        return ProviderReadiness(
            provider="CLAUDE_AGENT_SDK",
            status=sdk_status,
            summary="fake claude readiness",
        )

    runtime = ClaudeWikiRuntime(
        settings,
        catalog=catalog,
        sdk_readiness_probe=fake_probe,
        maintainer=maintainer,
    )
    return runtime, catalog


def make_project(catalog: ProjectCatalog):
    return catalog.create_project(
        CreateProjectRequest(
            name="测试项目",
            scenario_type="业财对账",
            summary="测试 wiki readiness。",
        )
    )


def test_global_readiness_not_configured_when_maintainer_missing(tmp_path: Path):
    runtime, _ = make_runtime(tmp_path, sdk_status="ready", maintainer=None)

    readiness = runtime.get_global_readiness()
    assert readiness.provider == WIKI_PROVIDER
    assert readiness.status == "not_configured"
    assert "WikiMaintainer" in (readiness.detail or "") or "维护" in (readiness.detail or "")


def test_global_readiness_ready_when_maintainer_and_sdk_ready(tmp_path: Path):
    runtime, _ = make_runtime(
        tmp_path, sdk_status="ready", maintainer=_FakeMaintainer()
    )

    readiness = runtime.get_global_readiness()
    assert readiness.status == "ready"


def test_global_readiness_reports_degraded_when_sdk_not_configured(tmp_path: Path):
    runtime, _ = make_runtime(
        tmp_path, sdk_status="not_configured", maintainer=_FakeMaintainer()
    )

    readiness = runtime.get_global_readiness()
    assert readiness.status == "degraded_readonly"
    assert (
        "Claude" in (readiness.detail or "")
        or "维护" in (readiness.detail or "")
    )


def test_global_readiness_reports_error_when_dir_unwritable(tmp_path: Path):
    runtime, _ = make_runtime(tmp_path)
    projects_dir = runtime.settings.projects_dir
    projects_dir.mkdir(parents=True, exist_ok=True)

    original_mode = projects_dir.stat().st_mode
    os.chmod(projects_dir, 0o500)
    try:
        readiness = runtime.get_global_readiness()
        if os.access(projects_dir, os.W_OK):
            pytest.skip("filesystem treats this dir as writable; skip on this platform")
        assert readiness.status == "error"
        assert "不可写" in (readiness.detail or "")
    finally:
        os.chmod(projects_dir, original_mode)


def test_project_readiness_pending_init_until_skeleton_created(tmp_path: Path):
    runtime, catalog = make_runtime(tmp_path)
    project = make_project(catalog)

    readiness = runtime.get_project_readiness(project.id)
    assert readiness.status == "pending_init"

    runtime.ensure_project_wiki(project.id)

    readiness_after = runtime.get_project_readiness(project.id)
    # Without maintainer wired, mirrors global "not_configured".
    assert readiness_after.status in {"not_configured", "degraded_readonly", "ready"}
    assert "5 页" in readiness_after.summary


def test_project_readiness_missing_for_unknown_project(tmp_path: Path):
    runtime, _ = make_runtime(tmp_path)
    readiness = runtime.get_project_readiness("does-not-exist")
    assert readiness.status == "missing"


def test_ensure_project_wiki_returns_wiki_record(tmp_path: Path):
    runtime, catalog = make_runtime(tmp_path)
    project = make_project(catalog)

    record = runtime.ensure_project_wiki(project.id)
    assert record.project_id == project.id
    assert record.page_count == 5
    assert record.last_maintained_at is not None


def test_ensure_project_wiki_unknown_project_raises(tmp_path: Path):
    runtime, _ = make_runtime(tmp_path)
    with pytest.raises(ProviderIssue) as info:
        runtime.ensure_project_wiki("missing-project")
    assert info.value.status_code == 404


def test_read_page_404_for_unknown_slug(tmp_path: Path):
    runtime, catalog = make_runtime(tmp_path)
    project = make_project(catalog)
    runtime.ensure_project_wiki(project.id)

    with pytest.raises(ProviderIssue) as info:
        runtime.read_page(project.id, "not-a-real-page")
    assert info.value.status_code == 404


def test_maintain_after_ingest_skipped_without_maintainer(tmp_path: Path):
    runtime, catalog = make_runtime(tmp_path, maintainer=None)
    project = make_project(catalog)
    result = asyncio.run(runtime.maintain_after_ingest(project.id, "src-x"))
    assert result.status == "skipped"
    assert "WikiMaintainer" in (result.error or "")


def test_maintain_after_checkpoint_skipped_when_sdk_not_configured(tmp_path: Path):
    runtime, catalog = make_runtime(
        tmp_path, sdk_status="not_configured", maintainer=_FakeMaintainer()
    )
    project = make_project(catalog)
    result = asyncio.run(runtime.maintain_after_checkpoint(project.id, "v-1"))
    assert result.status == "skipped"
    assert "claude_sdk_unavailable" in (result.error or "")


def test_maintain_after_ingest_delegates_to_maintainer(tmp_path: Path):
    fake = _FakeMaintainer()
    runtime, catalog = make_runtime(tmp_path, sdk_status="ready", maintainer=fake)
    project = make_project(catalog)
    result = asyncio.run(runtime.maintain_after_ingest(project.id, "src-1"))
    assert result.status == "maintained"
    assert fake.calls == [
        {
            "project_id": project.id,
            "trigger_kind": "source_ingested",
            "source_id": "src-1",
            "version_summary": None,
        }
    ]


def test_maintain_after_checkpoint_delegates_to_maintainer(tmp_path: Path):
    fake = _FakeMaintainer()
    runtime, catalog = make_runtime(tmp_path, sdk_status="ready", maintainer=fake)
    project = make_project(catalog)
    result = asyncio.run(runtime.maintain_after_checkpoint(project.id, "summary-x"))
    assert result.status == "maintained"
    assert fake.calls[0]["trigger_kind"] == "version_checkpoint"
    assert fake.calls[0]["version_summary"] == "summary-x"
