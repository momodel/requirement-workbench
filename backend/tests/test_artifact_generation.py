import json
import sqlite3
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import CreateProjectRequest, GeneratedArtifactOutput, ProjectState, StateItem
from app.services.artifact_generation import ArtifactGenerationService
from app.services.project_catalog import ProjectCatalog


class FakeAgentRuntime:
    def __init__(self, output: GeneratedArtifactOutput):
        self.output = output
        self.call_count = 0

    async def generate_artifact(self, *, project, state, artifact_type):
        self.call_count += 1
        return self.output


def test_validate_html_rejects_empty_output() -> None:
    service = ArtifactGenerationService()

    try:
        service.validate_html_output("页面方案", "   ")
    except ValueError as exc:
        assert "HTML 不能为空" in str(exc)
    else:
        raise AssertionError("Expected empty HTML to be rejected")


def test_validate_html_rejects_missing_title_and_external_script() -> None:
    service = ArtifactGenerationService()

    bad_html = """
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="UTF-8" />
        <script src="https://cdn.example.com/app.js"></script>
      </head>
      <body>
        <main><h1>页面方案</h1></main>
      </body>
    </html>
    """

    try:
        service.validate_html_output("页面方案", bad_html)
    except ValueError as exc:
        message = str(exc)
        assert "title" in message or "外链脚本" in message
    else:
        raise AssertionError("Expected invalid HTML to be rejected")


def test_validate_html_accepts_complete_local_document() -> None:
    service = ArtifactGenerationService()

    html = """
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="UTF-8" />
        <title>页面方案</title>
      </head>
      <body>
        <main>
          <h1>页面方案</h1>
          <section>总览</section>
        </main>
      </body>
    </html>
    """

    assert service.validate_html_output("页面方案", html) == html.strip()


def test_generate_from_model_reuses_latest_artifact_when_state_has_not_changed(tmp_path: Path) -> None:
    settings = AppSettings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        sqlite_dir=tmp_path / "data" / "sqlite",
        sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
        projects_dir=tmp_path / "data" / "projects",
        claude_artifact_timeout_seconds=5.0,
    )
    init_db(settings)

    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        payload=CreateProjectRequest(
            name="集团业财逐笔对账需求分析",
            scenario_type="reconciliation",
            summary="分析业财逐笔对账需求。",
        )
    )
    state = ProjectState(
        current_understanding=[
            StateItem(
                id="cu-1",
                title="核心目标",
                body="把逐笔对账需求收敛成可交付方案。",
                status="active",
                category="current_understanding",
                updated_at="2026-04-20T10:00:00+08:00",
                source_ids=["src-1"],
            )
        ],
        pending_items=[
            StateItem(
                id="pending-1",
                title="异常处理边界",
                body="退款和冲销是否纳入一期待确认。",
                status="active",
                category="pending_items",
                updated_at="2026-04-20T10:00:00+08:00",
                source_ids=[],
            )
        ],
        confirmed_items=[],
        conflict_items=[],
        mvp_items=[],
        versions=[],
        artifacts=[],
    )
    runtime = FakeAgentRuntime(
        GeneratedArtifactOutput(
            title="逐笔对账交互稿",
            summary="覆盖差异查看和处理闭环。",
            html="<!doctype html><html><head><title>逐笔对账交互稿</title></head><body><main>ok</main></body></html>",
        )
    )
    service = ArtifactGenerationService(settings)

    import asyncio

    first = asyncio.run(
        service.generate_from_model(
            project=project,
            state=state,
            artifact_type="interaction_flow",
            agent_runtime=runtime,
        )
    )

    state_with_saved_artifact = state.model_copy(
        update={
            "artifacts": [
                StateItem(
                    id=first.id,
                    title=first.title,
                    body=first.summary,
                    status="generated",
                    category="artifacts",
                    updated_at=first.updated_at,
                    source_ids=[],
                )
            ]
        }
    )

    second = asyncio.run(
        service.generate_from_model(
            project=project,
            state=state_with_saved_artifact,
            artifact_type="interaction_flow",
            agent_runtime=runtime,
        )
    )

    assert runtime.call_count == 1
    assert second.id == first.id
    assert second.preview_url == first.preview_url
    versions = catalog.list_state_items(project.id)["versions"]
    assert len(versions) == 1
    assert "交付物" in versions[0].title
    assert "逐笔对账交互稿" in versions[0].body


def test_generate_from_model_creates_version_snapshot_for_new_artifact(tmp_path: Path) -> None:
    settings = AppSettings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        sqlite_dir=tmp_path / "data" / "sqlite",
        sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
        projects_dir=tmp_path / "data" / "projects",
        claude_artifact_timeout_seconds=5.0,
    )
    init_db(settings)

    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        payload=CreateProjectRequest(
            name="集团业财逐笔对账需求分析",
            scenario_type="reconciliation",
            summary="分析业财逐笔对账需求。",
        )
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
    runtime = FakeAgentRuntime(
        GeneratedArtifactOutput(
            title="逐笔对账页面方案",
            summary="覆盖总览、差异明细和异常处理。",
            html="<!doctype html><html><head><title>逐笔对账页面方案</title></head><body><main>ok</main></body></html>",
        )
    )
    service = ArtifactGenerationService(settings)

    import asyncio

    artifact = asyncio.run(
        service.generate_from_model(
            project=project,
            state=state,
            artifact_type="page_solution",
            agent_runtime=runtime,
        )
    )

    versions = catalog.list_state_items(project.id)["versions"]

    assert artifact.title == "逐笔对账页面方案"
    assert len(versions) == 1
    assert versions[0].title == "交付物生成"
    assert "页面方案" in versions[0].body
    assert "逐笔对账页面方案" in versions[0].body

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        snapshot_row = connection.execute(
            "SELECT state_json FROM version_snapshots WHERE id = ?",
            (versions[0].id,),
        ).fetchone()
    finally:
        connection.close()

    assert snapshot_row is not None
    snapshot = json.loads(snapshot_row[0])
    assert len(snapshot["artifacts"]) == 1
    assert snapshot["artifacts"][0]["title"] == "逐笔对账页面方案"


def test_generate_from_model_uses_persisted_state_for_sequential_artifact_snapshots(
    tmp_path: Path,
) -> None:
    settings = AppSettings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        sqlite_dir=tmp_path / "data" / "sqlite",
        sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
        projects_dir=tmp_path / "data" / "projects",
        claude_artifact_timeout_seconds=5.0,
    )
    init_db(settings)

    catalog = ProjectCatalog(settings)
    project = catalog.create_project(
        payload=CreateProjectRequest(
            name="集团业财逐笔对账需求分析",
            scenario_type="reconciliation",
            summary="分析业财逐笔对账需求。",
        )
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
    service = ArtifactGenerationService(settings)

    import asyncio

    first_runtime = FakeAgentRuntime(
        GeneratedArtifactOutput(
            title="逐笔对账页面方案",
            summary="覆盖总览、差异明细和异常处理。",
            html="<!doctype html><html><head><title>逐笔对账页面方案</title></head><body><main>ok</main></body></html>",
        )
    )
    second_runtime = FakeAgentRuntime(
        GeneratedArtifactOutput(
            title="逐笔对账交互稿",
            summary="覆盖差异确认和处理闭环。",
            html="<!doctype html><html><head><title>逐笔对账交互稿</title></head><body><main>ok</main></body></html>",
        )
    )

    asyncio.run(
        service.generate_from_model(
            project=project,
            state=state,
            artifact_type="page_solution",
            agent_runtime=first_runtime,
        )
    )
    asyncio.run(
        service.generate_from_model(
            project=project,
            state=state,
            artifact_type="interaction_flow",
            agent_runtime=second_runtime,
        )
    )

    connection = sqlite3.connect(settings.sqlite_path)
    try:
        snapshot_rows = connection.execute(
            "SELECT state_json FROM version_snapshots WHERE project_id = ? ORDER BY created_at ASC",
            (project.id,),
        ).fetchall()
    finally:
        connection.close()

    assert len(snapshot_rows) == 2
    first_snapshot = json.loads(snapshot_rows[0][0])
    second_snapshot = json.loads(snapshot_rows[1][0])
    assert [item["title"] for item in first_snapshot["artifacts"]] == ["逐笔对账页面方案"]
    assert [item["title"] for item in second_snapshot["artifacts"]] == [
        "逐笔对账页面方案",
        "逐笔对账交互稿",
    ]
