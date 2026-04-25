from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.config import AppSettings
from app.db import init_db
from app.models import (
    AgentTurnInput,
    CreateProjectRequest,
    ProjectState,
    ProviderReadiness,
    SourceUpsert,
    StateItem,
    WikiPage,
    WikiPageMeta,
    WikiRecord,
)
from app.services.agent_runtime import ClaudeAgentRuntime
from app.services.project_catalog import ProjectCatalog


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "missing-claude"),
    )


class _FakeWikiRuntime:
    def __init__(self):
        self.pages = [
            WikiPageMeta(
                slug="overview", title="Project Overview", kind="overview",
                source_ids=[], last_maintained_at=None, last_maintained_by="skeleton",
            ),
            WikiPageMeta(
                slug="entity-order", title="Entity: 订单", kind="entity",
                source_ids=["src-1"], last_maintained_at="2026-04-25T10:00:00+08:00",
                last_maintained_by="subagent",
            ),
        ]

    def list_pages(self, project_id):
        return self.pages

    def read_page(self, project_id, slug):
        for meta in self.pages:
            if meta.slug == slug:
                return WikiPage(
                    **meta.model_dump(),
                    body=f"# {meta.title}\n\n这是 {meta.slug} 的页面正文。\n",
                )
        from app.models import ProviderIssue
        raise ProviderIssue(provider="LLM_WIKI", message=f"Wiki page not found: {slug}", status_code=404)

    def get_record(self, project_id):
        return WikiRecord(
            project_id=project_id,
            page_count=len(self.pages),
            last_maintained_at="2026-04-25T10:00:00+08:00",
            pending_source_ids=["src-2"],
        )


def _make_runtime(tmp_path: Path):
    settings = make_settings(tmp_path)
    init_db(settings)
    runtime = ClaudeAgentRuntime(settings)
    runtime.attach_wiki_runtime(_FakeWikiRuntime())
    return runtime


def test_wiki_list_pages_tool_returns_metas(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="x", scenario_type="t", summary="s")
    )
    wiki_reads: list[dict] = []
    tool_handle = runtime._make_wiki_list_pages_tool(
        project_id=project.id, wiki_reads=wiki_reads
    )
    raw = asyncio.run(tool_handle.handler({}))
    payload = json.loads(raw["content"][0]["text"])
    assert {p["slug"] for p in payload["pages"]} == {"overview", "entity-order"}
    assert wiki_reads == [{"op": "list", "page_count": 2}]


def test_wiki_read_page_tool_returns_body(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="x", scenario_type="t", summary="s")
    )
    wiki_reads: list[dict] = []
    tool_handle = runtime._make_wiki_read_page_tool(
        project_id=project.id, wiki_reads=wiki_reads
    )
    raw = asyncio.run(tool_handle.handler({"slug": "entity-order"}))
    payload = json.loads(raw["content"][0]["text"])
    assert payload["slug"] == "entity-order"
    assert "页面正文" in payload["body"]
    assert wiki_reads == [{"op": "read", "slug": "entity-order", "title": "Entity: 订单"}]


def test_wiki_read_page_tool_returns_error_for_unknown_slug(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="x", scenario_type="t", summary="s")
    )
    tool_handle = runtime._make_wiki_read_page_tool(
        project_id=project.id, wiki_reads=[]
    )
    result = asyncio.run(tool_handle.handler({"slug": "ghost"}))
    assert result.get("is_error") is True


def test_loop_prompt_includes_wiki_status_line(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="项目", scenario_type="对账", summary="测试")
    )
    state = ProjectState(
        current_understanding=[],
        pending_items=[],
        confirmed_items=[],
        conflict_items=[],
        mvp_items=[],
        versions=[],
        artifacts=[],
    )
    turn = AgentTurnInput(
        project=project,
        state=state,
        user_message="hi",
        selected_source_ids=[],
        source_summaries=[],
        evidence_summary="",
        evidence_citations=[],
        request_artifact_types=[],
    )
    prompt = runtime._build_loop_prompt(turn)
    assert "项目 wiki 状态" in prompt
    assert "pages=2" in prompt
    assert "pending=1" in prompt
    # wiki tool listing references both new tools
    assert "wiki_list_pages" in prompt
    assert "wiki_read_page" in prompt
    # citation discipline rule present
    assert "wiki 是综合层" in prompt or "citation 必须来自" in prompt


# ---------- update_project_state source_id validation ----------


def test_update_project_state_rejects_unknown_source_id_in_confirmed(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="项目", scenario_type="对账", summary="x")
    )
    real = runtime.catalog.create_source(
        project_id=project.id,
        name="资料",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        normalize_status="parsed",
        normalize_summary="x",
        index_status="indexed",
        index_error=None,
    )
    applied: dict = {}
    tool_handle = runtime._make_update_project_state_tool(
        project_id=project.id, applied_state_updates=applied
    )
    args = {
        "confirmed_items": [
            {
                "title": "fake confirmed",
                "body": "trying to inject wiki slug as source_id",
                "source_ids": ["overview"],
            }
        ]
    }
    result = asyncio.run(tool_handle.handler(args))
    assert result.get("is_error") is True
    assert "未知 source_id" in result["content"][0]["text"]
    # nothing got persisted
    assert applied == {}


def test_update_project_state_rejects_confirmed_without_source_ids(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="项目", scenario_type="对账", summary="x")
    )
    tool_handle = runtime._make_update_project_state_tool(
        project_id=project.id, applied_state_updates={}
    )
    args = {
        "confirmed_items": [{"title": "x", "body": "y", "source_ids": []}]
    }
    result = asyncio.run(tool_handle.handler(args))
    assert result.get("is_error") is True
    assert "必须带 source_ids" in result["content"][0]["text"]


def test_update_project_state_accepts_confirmed_with_real_source_id(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="项目", scenario_type="对账", summary="x")
    )
    real = runtime.catalog.create_source(
        project_id=project.id,
        name="资料",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        normalize_status="parsed",
        normalize_summary="x",
        index_status="indexed",
        index_error=None,
    )
    applied: dict = {}
    tool_handle = runtime._make_update_project_state_tool(
        project_id=project.id, applied_state_updates=applied
    )
    args = {
        "confirmed_items": [
            {"title": "ok", "body": "real evidence", "source_ids": [real.id]}
        ]
    }
    result = asyncio.run(tool_handle.handler(args))
    assert result.get("is_error") is None or result.get("is_error") is False
    assert "confirmed_items" in applied
    assert len(applied["confirmed_items"]) == 1


def test_update_project_state_does_not_validate_pending_items(tmp_path: Path):
    runtime = _make_runtime(tmp_path)
    project = runtime.catalog.create_project(
        CreateProjectRequest(name="项目", scenario_type="对账", summary="x")
    )
    applied: dict = {}
    tool_handle = runtime._make_update_project_state_tool(
        project_id=project.id, applied_state_updates=applied
    )
    args = {
        # pending items can have empty or unverified source_ids — these are working hypotheses
        "pending_items": [{"title": "p", "body": "待确认", "source_ids": []}]
    }
    result = asyncio.run(tool_handle.handler(args))
    assert result.get("is_error") is None or result.get("is_error") is False
    assert "pending_items" in applied
