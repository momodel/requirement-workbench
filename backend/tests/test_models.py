import pytest
from pydantic import ValidationError

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
    assert "notebook_import_mode" not in payload
    assert "parse_status" not in payload
    assert "parse_summary" not in payload
    assert "sync_status" not in payload
    assert "sync_error" not in payload


def test_source_record_rejects_legacy_only_input_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SourceRecord.model_validate(
            {
                "id": "source-3",
                "project_id": "project-1",
                "name": "历史资料",
                "source_kind": "text",
                "upload_kind": "text",
                "normalize_status": "parsed",
                "notebook_import_mode": "direct_text",
                "parse_status": "parsed",
                "parse_summary": "旧字段摘要",
                "sync_status": "synced",
                "sync_error": None,
                "created_at": "2026-04-22T00:00:00Z",
            }
        )

    errors = exc_info.value.errors()
    rejected_fields = {error["loc"][0] for error in errors}

    assert rejected_fields == {
        "notebook_import_mode",
        "parse_status",
        "parse_summary",
        "sync_status",
        "sync_error",
    }
    assert all(error["type"] == "extra_forbidden" for error in errors)


def test_source_record_neutral_dump_excludes_legacy_keys() -> None:
    record = SourceRecord(
        id="source-4",
        project_id="project-1",
        name="中性输出",
        source_kind="text",
        upload_kind="text",
        index_input_mode="direct_text",
        normalize_status="parsed",
        normalize_summary="neutral only",
        index_status="synced",
        index_error=None,
        created_at="2026-04-22T00:00:00Z",
    )

    neutral_payload = record.model_dump_neutral()

    assert not hasattr(record, "model_dump_legacy")
    assert neutral_payload == record.model_dump()
    assert neutral_payload["index_input_mode"] == "direct_text"
    assert neutral_payload["normalize_status"] == "parsed"
    assert neutral_payload["normalize_summary"] == "neutral only"
    assert neutral_payload["index_status"] == "synced"
    assert neutral_payload["index_error"] is None
    assert "notebook_import_mode" not in neutral_payload
    assert "parse_status" not in neutral_payload
    assert "parse_summary" not in neutral_payload
    assert "sync_status" not in neutral_payload
    assert "sync_error" not in neutral_payload
