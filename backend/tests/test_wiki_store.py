from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import AppSettings
from app.models import ProjectSummary, WikiPage
from app.services.wiki_store import (
    WikiStore,
    WikiStoreError,
    parse_page,
    serialize_page,
    validate_slug,
)


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
    )


def make_project(project_id: str = "p-1") -> ProjectSummary:
    return ProjectSummary(
        id=project_id,
        name="测试项目",
        scenario_type="业财对账",
        summary="一个测试项目。",
        status="active",
        created_at="2026-04-25T10:00:00+08:00",
        updated_at="2026-04-25T10:00:00+08:00",
    )


def test_validate_slug_accepts_valid_slug():
    validate_slug("overview")
    validate_slug("entity-account-system")
    validate_slug("rule-1")


def test_validate_slug_rejects_invalid_slug():
    with pytest.raises(WikiStoreError):
        validate_slug("")
    with pytest.raises(WikiStoreError):
        validate_slug("Has-Caps")
    with pytest.raises(WikiStoreError):
        validate_slug("中文")
    with pytest.raises(WikiStoreError):
        validate_slug("-leading-dash")


def test_serialize_and_parse_roundtrip():
    page = WikiPage(
        slug="entity-order",
        title="Entity: Order",
        kind="entity",
        source_ids=["src-1", "src-2"],
        last_maintained_at="2026-04-25T10:00:00+08:00",
        last_maintained_by="subagent",
        body="# Order\n\n订单实体。\n",
    )
    text = serialize_page(page)
    assert text.startswith("---\n")
    front_block = text.split("---\n", 2)[1]
    payload = json.loads(front_block)
    assert payload["title"] == "Entity: Order"
    assert payload["source_ids"] == ["src-1", "src-2"]

    parsed = parse_page(text, slug="entity-order")
    assert parsed.title == page.title
    assert parsed.kind == page.kind
    assert parsed.source_ids == page.source_ids
    assert parsed.body.strip() == page.body.strip()


def test_parse_page_rejects_missing_front_matter():
    with pytest.raises(WikiStoreError):
        parse_page("# Just a body\n", slug="overview")


def test_parse_page_rejects_invalid_json_front_matter():
    bad = "---\nnot-json\n---\n\nbody\n"
    with pytest.raises(WikiStoreError):
        parse_page(bad, slug="overview")


def test_ensure_skeleton_creates_fixed_pages_idempotently(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    project = make_project()

    created_first = store.ensure_skeleton(project)
    assert created_first is True

    wiki_dir = tmp_path / "data" / "projects" / "p-1" / "wiki"
    assert (wiki_dir / "index.md").exists()
    assert (wiki_dir / "log.md").exists()
    assert (wiki_dir / "pages" / "overview.md").exists()
    assert (wiki_dir / "pages" / "source-intake.md").exists()
    assert (wiki_dir / "pages" / "glossary.md").exists()
    assert (wiki_dir / "pages" / "rules-and-conflicts.md").exists()
    assert (wiki_dir / "pages" / "open-questions.md").exists()

    overview = store.read_page("p-1", "overview")
    assert overview.kind == "overview"
    assert overview.last_maintained_by == "skeleton"
    assert "测试项目" in overview.body

    created_second = store.ensure_skeleton(project)
    assert created_second is False


def test_list_pages_returns_skeleton_metadata(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    store.ensure_skeleton(make_project())

    metas = store.list_pages("p-1")
    slugs = {meta.slug for meta in metas}
    assert slugs == {
        "overview",
        "source-intake",
        "glossary",
        "rules-and-conflicts",
        "open-questions",
    }


def test_list_pages_skips_body_for_cheap_listing(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    store.ensure_skeleton(make_project())

    # Inject a deliberately huge body to confirm list_pages does not load it.
    page = WikiPage(
        slug="entity-big",
        title="Big",
        kind="entity",
        source_ids=["src-1"],
        last_maintained_at=None,
        last_maintained_by="subagent",
        body="X" * 1_000_000,
    )
    store.write_page("p-1", page)

    metas = store.list_pages("p-1")
    big = next(m for m in metas if m.slug == "entity-big")
    # WikiPageMeta has no body attribute — the body must not have been loaded.
    assert not hasattr(big, "body")
    assert big.source_ids == ["src-1"]


def test_list_pages_rejects_unterminated_front_matter(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    store.ensure_skeleton(make_project())

    pages_dir = tmp_path / "data" / "projects" / "p-1" / "wiki" / "pages"
    (pages_dir / "broken.md").write_text(
        '---\n{"title": "Broken", "kind": "entity"\n# never closed\n',
        encoding="utf-8",
    )
    with pytest.raises(WikiStoreError):
        store.list_pages("p-1")


def test_write_page_rejects_expanded_kind_without_source_ids(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    store.ensure_skeleton(make_project())

    bad_page = WikiPage(
        slug="entity-order",
        title="Entity: Order",
        kind="entity",
        source_ids=[],
        last_maintained_at=None,
        last_maintained_by="subagent",
        body="body\n",
    )
    with pytest.raises(WikiStoreError):
        store.write_page("p-1", bad_page)


def test_write_page_atomic_overwrite(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    store.ensure_skeleton(make_project())

    page = WikiPage(
        slug="entity-order",
        title="Entity: Order",
        kind="entity",
        source_ids=["src-1"],
        last_maintained_at="2026-04-25T10:00:00+08:00",
        last_maintained_by="subagent",
        body="v1\n",
    )
    store.write_page("p-1", page)
    again = WikiPage(**{**page.model_dump(), "body": "v2\n"})
    store.write_page("p-1", again)

    fetched = store.read_page("p-1", "entity-order")
    assert fetched.body.strip() == "v2"

    # No leftover tmp files in pages dir.
    pages_dir = tmp_path / "data" / "projects" / "p-1" / "wiki" / "pages"
    leftovers = [p.name for p in pages_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_append_log_keeps_history(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    store.ensure_skeleton(make_project())

    store.append_log(
        "p-1",
        operation="source_ingested",
        summary="新增 source src-1",
        source_ids=["src-1"],
        pages_changed=["source-intake"],
    )
    store.append_log(
        "p-1",
        operation="version_checkpoint",
        summary="阶段性快照",
        pages_changed=["overview"],
    )

    log = store.read_log("p-1")
    assert log.count("## [") >= 2
    assert "src-1" in log
    assert "version_checkpoint" in log


def test_health_marker_roundtrip(tmp_path: Path):
    store = WikiStore(make_settings(tmp_path))
    store.ensure_skeleton(make_project())

    assert store.read_health("p-1") is None
    store.write_health("p-1", "ok-2026-04-25")
    assert store.read_health("p-1") == "ok-2026-04-25"
