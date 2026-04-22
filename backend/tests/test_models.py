from app.models import AgentStructuredOutput, GeneratedArtifactOutput, SourceRecord


def test_agent_structured_output_normalizes_nullable_lists() -> None:
    output = AgentStructuredOutput.model_validate(
        {
            "assistant_message": "ok",
            "citations": None,
            "current_understanding": None,
            "pending_items": None,
            "confirmed_items": None,
            "conflict_items": None,
            "mvp_items": None,
            "version_summary": None,
            "request_artifacts": None,
        }
    )

    assert output.citations == []
    assert output.current_understanding == []
    assert output.pending_items == []
    assert output.confirmed_items == []
    assert output.conflict_items == []
    assert output.mvp_items == []
    assert output.request_artifacts == []


def test_agent_structured_output_normalizes_empty_request_artifacts_string() -> None:
    output = AgentStructuredOutput.model_validate(
        {
            "assistant_message": "ok",
            "citations": [],
            "current_understanding": [],
            "pending_items": [],
            "confirmed_items": [],
            "conflict_items": [],
            "mvp_items": [],
            "version_summary": None,
            "request_artifacts": "",
        }
    )

    assert output.request_artifacts == []


def test_generated_artifact_output_uses_body_as_summary_when_summary_missing() -> None:
    output = GeneratedArtifactOutput.model_validate(
        {
            "title": "需求分析文档",
            "body": "# 正文\n这里是详细内容。",
            "status": "active",
            "category": "artifacts",
        }
    )

    assert output.summary == "# 正文 这里是详细内容。"
    assert output.body == "# 正文\n这里是详细内容。"


def test_source_record_accepts_neutral_index_fields() -> None:
    record = SourceRecord(
        id="source-1",
        project_id="project-1",
        name="需求说明",
        source_kind="text",
        upload_kind="text",
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="摘要",
        index_status="synced",
        index_error=None,
        created_at="2026-04-22T00:00:00Z",
    )

    assert record.index_input_mode == "direct_text"
    assert record.normalize_status == "parsed"
    assert record.normalize_summary == "摘要"
    assert record.index_status == "synced"
    assert record.index_error is None


def test_source_record_serializes_neutral_index_fields() -> None:
    record = SourceRecord(
        id="source-2",
        project_id="project-1",
        name="流程图",
        source_kind="file",
        upload_kind="file",
        index_input_mode="normalized_markdown",
        normalize_status="parsed",
        normalize_summary="流程拆解完成",
        index_status="pending_sync",
        index_error="Notebook 未绑定",
        created_at="2026-04-22T00:00:00Z",
    )

    payload = record.model_dump()

    assert payload["index_input_mode"] == "normalized_markdown"
    assert payload["normalize_status"] == "parsed"
    assert payload["normalize_summary"] == "流程拆解完成"
    assert payload["index_status"] == "pending_sync"
    assert payload["index_error"] == "Notebook 未绑定"
