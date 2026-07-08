from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from app.config import AppSettings
from app.db import init_db
from app.models import (
    CreateProjectRequest,
    EvidenceResult,
    ChatCitation,
    ProviderIssue,
    SourceRecord,
)
from app.services.project_catalog import ProjectCatalog, now_iso
from app.services.wiki_maintenance import (
    HEALTH_PROBE_TIMEOUT_SECONDS,
    WikiMaintainer,
)
from app.services.wiki_store import WikiStore


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        llm_cli_path=str(tmp_path / "fake-claude"),
    )


def make_setup(tmp_path: Path):
    settings = make_settings(tmp_path)
    init_db(settings)
    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        CreateProjectRequest(
            name="测试项目",
            scenario_type="业财对账",
            summary="testing wiki maintenance.",
        )
    )
    store = WikiStore(settings)
    store.ensure_skeleton(project)
    return settings, catalog, store, project


def insert_source(catalog: ProjectCatalog, project_id: str, *, source_id: str, name: str, summary: str) -> SourceRecord:
    return catalog.create_source(
        project_id=project_id,
        name=name,
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        index_input_mode=None,
        normalize_status="parsed",
        normalize_summary=summary,
        index_status="indexed",
        index_error=None,
    )


# ---------- prompt ----------


def test_prompt_includes_focus_source_and_allowed_source_ids(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)
    src1 = insert_source(catalog, project.id, source_id="s1", name="字段映射说明", summary="订单字段与财务科目映射。")
    src2 = insert_source(catalog, project.id, source_id="s2", name="对账规则", summary="差异容忍度阈值定义。")

    maintainer = WikiMaintainer(settings, store=store, catalog=catalog)
    sources = catalog.list_sources(project.id)
    focus = next(s for s in sources if s.id == src1.id)
    prompt = maintainer._build_prompt(
        project=project,
        sources=sources,
        trigger_kind="source_ingested",
        focus_source=focus,
        version_summary=None,
    )

    assert "source_ingested" in prompt
    assert project.id in prompt
    assert focus.id in prompt
    assert "字段映射说明" in prompt
    assert "白名单" in prompt
    # allowed source IDs whitelist contains both ids
    allowed_block_idx = prompt.find("白名单")
    after = prompt[allowed_block_idx:]
    assert src1.id in after
    assert src2.id in after
    # hard-rule block present
    assert "硬规则" in prompt
    assert "不许伪造 source_id" in prompt
    # page index lines are JSON, do NOT contain page bodies
    assert "正文用 read_file 自取" in prompt
    assert "_骨架页" not in prompt  # body sentinel from skeleton not embedded


def test_prompt_includes_version_summary_for_checkpoint(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)
    insert_source(catalog, project.id, source_id="s1", name="资料 A", summary="测试摘要")

    maintainer = WikiMaintainer(settings, store=store, catalog=catalog)
    sources = catalog.list_sources(project.id)
    prompt = maintainer._build_prompt(
        project=project,
        sources=sources,
        trigger_kind="version_checkpoint",
        focus_source=None,
        version_summary="阶段性结论：MVP 包括逐笔差异列表。",
    )
    assert "version_checkpoint" in prompt
    assert "阶段性结论：MVP 包括逐笔差异列表。" in prompt


def test_system_prompt_embeds_skill_text(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)
    skill_path = tmp_path / "fake_skill.md"
    skill_path.write_text("# fake skill marker", encoding="utf-8")

    maintainer = WikiMaintainer(
        settings,
        store=store,
        catalog=catalog,
        skill_path=skill_path,
    )
    text = maintainer._system_prompt()
    assert "fake skill marker" in text
    assert "read_file / write_file / edit_file / ls / glob" in text
    assert "wiki" in text


# ---------- run() with mocked SDK ----------


class _FakeAsyncIterator:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


def _patch_run_query(write_fn):
    """Patch WikiMaintainer._run_query to invoke write_fn(prompt) instead of the real agent."""
    async def fake_run_query(self, *, prompt, cwd, system_prompt, allowed_tools, max_turns):
        write_fn(prompt)
    return patch.object(WikiMaintainer, "_run_query", fake_run_query)


def test_run_marks_maintained_when_sdk_writes_valid_page(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)
    src = insert_source(catalog, project.id, source_id="s-real", name="资料", summary="规则要点")

    maintainer = WikiMaintainer(settings, store=store, catalog=catalog)

    def write_fn(prompt: str):
        # Simulate a real subagent: write a new entity page directly to disk.
        wiki_dir = store.project_wiki_dir(project.id)
        page_text = (
            "---\n"
            + json.dumps(
                {
                    "title": "Entity: 订单",
                    "kind": "entity",
                    "source_ids": [src.id],
                    "last_maintained_at": now_iso(settings),
                    "last_maintained_by": "subagent",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n---\n\n# 订单\n\n订单实体的工作理解。[src: " + src.id + "]\n"
        )
        (wiki_dir / "pages" / "entity-order.md").write_text(page_text, encoding="utf-8")

    with _patch_run_query(write_fn):
        result = asyncio.run(
            maintainer.run(project.id, trigger_kind="source_ingested", source_id=src.id)
        )

    assert result.status == "maintained", result.error
    assert "pages/entity-order.md" in result.pages_changed
    log_text = store.read_log(project.id)
    assert "source_ingested" in log_text
    assert src.id in log_text


def test_run_fails_when_sdk_writes_unknown_source_id(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)
    src = insert_source(catalog, project.id, source_id="s-real", name="资料", summary="规则要点")

    maintainer = WikiMaintainer(settings, store=store, catalog=catalog)

    def write_fn(prompt: str):
        wiki_dir = store.project_wiki_dir(project.id)
        page_text = (
            "---\n"
            + json.dumps(
                {
                    "title": "Entity: 不存在",
                    "kind": "entity",
                    "source_ids": ["s-fabricated"],
                    "last_maintained_at": now_iso(settings),
                    "last_maintained_by": "subagent",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n---\n\nbody\n"
        )
        (wiki_dir / "pages" / "entity-fake.md").write_text(page_text, encoding="utf-8")

    with _patch_run_query(write_fn):
        result = asyncio.run(
            maintainer.run(project.id, trigger_kind="source_ingested", source_id=src.id)
        )

    assert result.status == "failed"
    assert "s-fabricated" in (result.error or "")


def test_run_fails_when_sdk_writes_outside_pages_dir(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)
    src = insert_source(catalog, project.id, source_id="s1", name="资料", summary="x")

    maintainer = WikiMaintainer(settings, store=store, catalog=catalog)

    def write_fn(prompt: str):
        wiki_dir = store.project_wiki_dir(project.id)
        # Write a markdown file in wiki root (not under pages/), which is forbidden.
        (wiki_dir / "rogue.md").write_text("# rogue\n", encoding="utf-8")

    with _patch_run_query(write_fn):
        result = asyncio.run(
            maintainer.run(project.id, trigger_kind="source_ingested", source_id=src.id)
        )

    assert result.status == "failed"
    assert "非法路径" in (result.error or "")


def test_run_health_probe_passes_when_marker_written(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)

    captured_prompt: dict[str, Any] = {}
    maintainer = WikiMaintainer(settings, store=store, catalog=catalog)

    def write_fn(prompt: str):
        captured_prompt["text"] = prompt
        # extract marker the subagent was told to write
        wiki_dir = store.project_wiki_dir(project.id)
        # find the marker in the prompt: it appears between backticks after "包含一行："
        marker = prompt.split("`")[3]
        (wiki_dir / ".health").write_text(marker, encoding="utf-8")

    with _patch_run_query(write_fn):
        result = asyncio.run(maintainer.run_health_probe(project.id))

    assert result.status == "maintained"
    assert ".health" in result.pages_changed
    assert "probe-" in (captured_prompt["text"] or "")


def test_run_health_probe_fails_when_marker_missing(tmp_path: Path):
    settings, catalog, store, project = make_setup(tmp_path)

    maintainer = WikiMaintainer(settings, store=store, catalog=catalog)

    def write_fn(prompt: str):
        # subagent does nothing (marker missing on purpose)
        pass

    with _patch_run_query(write_fn):
        with pytest.raises(ProviderIssue) as info:
            asyncio.run(maintainer.run_health_probe(project.id))

    assert "标记" in info.value.message or "marker" in info.value.message.lower()
