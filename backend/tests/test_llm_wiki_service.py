from pathlib import Path

from app.config import AppSettings
from app.models import ProjectState, ProjectSummary, SourceRecord, StateItem
from app.services.llm_wiki_service import LLMWikiService


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
    )


def make_project() -> ProjectSummary:
    return ProjectSummary(
        id="project-wiki-001",
        name="集团业财逐笔对账需求分析",
        scenario_type="业财对账",
        summary="围绕订单系统与财务系统的逐笔对账做需求分析。",
        status="active",
        created_at="2026-04-25T10:00:00+08:00",
        updated_at="2026-04-25T10:00:00+08:00",
    )


def make_source() -> SourceRecord:
    return SourceRecord(
        id="src-field-map",
        project_id="project-wiki-001",
        name="字段映射说明",
        source_kind="text",
        upload_kind="text",
        storage_path=None,
        normalized_path=None,
        source_import_mode="direct_text",
        parse_status="parsed",
        parse_summary="订单字段与财务科目映射口径存在不一致。",
        sync_status="synced",
        sync_error=None,
        created_at="2026-04-25T10:00:00+08:00",
    )


def test_initialize_project_wiki_creates_project_local_files(tmp_path: Path) -> None:
    service = LLMWikiService(make_settings(tmp_path))

    context = service.initialize_project(make_project())

    wiki_dir = tmp_path / "data" / "projects" / "project-wiki-001" / "wiki"
    assert (wiki_dir / "index.md").exists()
    assert (wiki_dir / "log.md").exists()
    assert "集团业财逐笔对账需求分析" in (wiki_dir / "project-overview.md").read_text(encoding="utf-8")
    assert "LLM Wiki 当前只有初始化骨架" in context.summary
    assert str(wiki_dir) in context.detail


def test_record_source_intake_updates_wiki_without_creating_citations(tmp_path: Path) -> None:
    service = LLMWikiService(make_settings(tmp_path))
    project = make_project()
    service.initialize_project(project)

    context = service.record_source_intake(project, [make_source()])

    source_index = tmp_path / "data" / "projects" / "project-wiki-001" / "wiki" / "source-intake.md"
    content = source_index.read_text(encoding="utf-8")
    assert "字段映射说明" in content
    assert "src-field-map" in content
    assert "订单字段与财务科目映射口径存在不一致" in content
    assert context.citations == []
    assert "LLM Wiki 是当前项目的知识库" in context.summary


def test_record_source_intake_does_not_append_log_when_content_is_unchanged(tmp_path: Path) -> None:
    service = LLMWikiService(make_settings(tmp_path))
    project = make_project()
    service.initialize_project(project)
    service.record_source_intake(project, [make_source()])
    log_path = tmp_path / "data" / "projects" / "project-wiki-001" / "wiki" / "log.md"
    before = log_path.read_text(encoding="utf-8")

    service.record_source_intake(project, [make_source()])

    assert log_path.read_text(encoding="utf-8") == before


def test_build_context_marks_wiki_as_project_knowledge_base(tmp_path: Path) -> None:
    service = LLMWikiService(make_settings(tmp_path))
    project = make_project()
    service.initialize_project(project)
    service.record_source_intake(project, [make_source()])

    context = service.build_context(project.id)

    assert "LLM Wiki 是当前项目的知识库" in context.summary
    assert "字段映射说明" in context.summary
    assert context.citations == []


def test_record_state_checkpoint_updates_state_and_conflict_pages_once(tmp_path: Path) -> None:
    service = LLMWikiService(make_settings(tmp_path))
    project = make_project()
    service.initialize_project(project)
    state = ProjectState(
        current_understanding=[
            StateItem(
                id="cu-1",
                title="逐笔对账目标",
                body="订单与财务科目金额需要逐笔校验。",
                source_ids=["src-field-map"],
            )
        ],
        pending_items=[],
        confirmed_items=[],
        conflict_items=[
            StateItem(
                id="conflict-1",
                title="字段映射口径冲突",
                body="订单字段和财务科目映射表口径不一致。",
                source_ids=["src-field-map"],
            )
        ],
        mvp_items=[],
        versions=[],
        artifacts=[],
    )

    context = service.record_state_checkpoint(
        project,
        state,
        trigger_kind="analysis_checkpoint",
        summary="形成字段映射冲突判断。",
    )

    wiki_dir = tmp_path / "data" / "projects" / "project-wiki-001" / "wiki"
    state_summary = (wiki_dir / "state-summary.md").read_text(encoding="utf-8")
    conflict_page = (wiki_dir / "rules-and-conflicts.md").read_text(encoding="utf-8")
    before_log = (wiki_dir / "log.md").read_text(encoding="utf-8")
    assert "逐笔对账目标" in state_summary
    assert "字段映射口径冲突" in conflict_page
    assert context.citations == []
    assert "阶段性沉淀" in context.summary

    service.record_state_checkpoint(
        project,
        state,
        trigger_kind="analysis_checkpoint",
        summary="形成字段映射冲突判断。",
    )

    assert (wiki_dir / "log.md").read_text(encoding="utf-8") == before_log
