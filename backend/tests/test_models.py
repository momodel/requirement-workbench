from app.models import AgentStructuredOutput, GeneratedArtifactOutput


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
