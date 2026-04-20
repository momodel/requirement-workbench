import asyncio
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.config import AppSettings
from app.services import agent_runtime as agent_runtime_module
from app.models import AgentStructuredOutput, AgentTurnInput, MessageRecord, ProjectState, ProjectSummary, ProviderIssue
from app.services.agent_runtime import (
    ClaudeAgentRuntime,
    _coerce_json_payload,
    _normalize_structured_output_payload,
)


def test_coerce_json_payload_extracts_json_from_wrapped_text() -> None:
    wrapped = """
这是生成结果：

```json
{
  "title": "需求分析文档",
  "summary": "摘要",
  "body": "# 正文"
}
```

请继续。
"""

    payload = _coerce_json_payload(wrapped)

    assert payload["title"] == "需求分析文档"
    assert payload["body"] == "# 正文"


def test_normalize_structured_output_payload_accepts_model_variant_shapes() -> None:
    raw = {
        "assistant_message": "已整理当前真实需求。",
        "citations": None,
        "current_understanding": [
            "业务目标：实现订单与财务科目金额的逐笔对账",
            "核心矛盾：业务字段与财务科目映射口径不一致",
            {
                "item": "订单与财务入账记录需要逐笔对齐",
                "evidence": "项目摘要",
                "confidence": "high",
            },
            {
                "content": "业务字段与财务科目映射口径存在不一致",
                "source": "NotebookLM grounding",
            },
        ],
        "pending_items": [
            {
                "id": "P001",
                "question": "退款和冲销是否都纳入一期？",
                "source": "NotebookLM grounding",
            }
        ],
        "confirmed_items": None,
        "conflict_items": [
            {
                "id": "C001",
                "description": "退款负单与冲销凭证对象模型不一致",
                "related_sources": ["财务科目口径说明"],
            }
        ],
        "mvp_items": None,
        "version_summary": None,
        "request_artifacts": False,
    }

    normalized = _normalize_structured_output_payload(raw)
    output = AgentStructuredOutput.model_validate(normalized)

    assert output.current_understanding[0].title == "业务目标"
    assert output.current_understanding[0].body == "实现订单与财务科目金额的逐笔对账"
    assert output.current_understanding[2].title == "订单与财务入账记录需要逐笔对齐"
    assert "项目摘要" in output.current_understanding[2].body
    assert output.current_understanding[3].title == "业务字段与财务科目映射口径存在不一致"
    assert "NotebookLM grounding" in output.current_understanding[3].body
    assert output.pending_items[0].title == "退款和冲销是否都纳入一期？"
    assert "NotebookLM grounding" in output.pending_items[0].body
    assert output.conflict_items[0].title == "退款负单与冲销凭证对象模型不一致"
    assert output.request_artifacts == []


def test_normalize_structured_output_payload_flattens_state_patch_shape() -> None:
    raw = {
        "assistant_message": "已整理当前真实需求。",
        "state_patch": {
            "current_understanding": [
                {
                    "id": "cu-001",
                    "content": "项目核心目标：实现订单与财务系统之间的逐笔一致性校验",
                    "evidence": "项目摘要",
                }
            ],
            "pending_items": [],
            "confirmed_items": [],
            "conflict_items": [],
            "mvp_items": [],
        },
        "follow_up_questions": [
            "退款和冲销是否纳入一期范围？",
            "业务字段到财务科目的映射关系是否已有标准表？",
        ],
        "request_artifacts": [],
        "citations": [],
    }

    normalized = _normalize_structured_output_payload(raw)
    output = AgentStructuredOutput.model_validate(normalized)

    assert output.current_understanding[0].title == "项目核心目标"
    assert "逐笔一致性校验" in output.current_understanding[0].body
    assert len(output.pending_items) == 2
    assert output.pending_items[0].title == "退款和冲销是否纳入一期范围？"


def test_claude_readiness_uses_default_model_when_model_env_missing(monkeypatch) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=Path("/tmp/project"),
            data_dir=Path("/tmp/project/data"),
            sqlite_dir=Path("/tmp/project/data/sqlite"),
            sqlite_path=Path("/tmp/project/data/sqlite/test.db"),
            projects_dir=Path("/tmp/project/data/projects"),
            notebooklm_home_dir=Path("/tmp/project/data/notebooklm"),
            claude_cli_path="/usr/local/bin/claude",
            claude_model=None,
        )
    )

    monkeypatch.setattr(agent_runtime_module.Path, "exists", lambda self: True)

    def fake_run(command, **kwargs):
        assert command == ["/usr/local/bin/claude", "auth", "status"]
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"loggedIn": true, "authMethod": "oauth_token", "apiProvider": "firstParty"}',
            stderr="",
        )

    monkeypatch.setattr(agent_runtime_module.subprocess, "run", fake_run)

    readiness = runtime.get_readiness()

    assert readiness.status == "ready_default_model"
    assert "默认模型" in readiness.summary


def test_claude_readiness_reports_auth_required(monkeypatch) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=Path("/tmp/project"),
            data_dir=Path("/tmp/project/data"),
            sqlite_dir=Path("/tmp/project/data/sqlite"),
            sqlite_path=Path("/tmp/project/data/sqlite/test.db"),
            projects_dir=Path("/tmp/project/data/projects"),
            notebooklm_home_dir=Path("/tmp/project/data/notebooklm"),
            claude_cli_path="/usr/local/bin/claude",
            claude_model="sonnet",
        )
    )

    monkeypatch.setattr(agent_runtime_module.Path, "exists", lambda self: True)

    def fake_run(command, **kwargs):
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"loggedIn": false, "authMethod": null, "apiProvider": null}',
            stderr="",
        )

    monkeypatch.setattr(agent_runtime_module.subprocess, "run", fake_run)

    readiness = runtime.get_readiness()

    assert readiness.status == "auth_required"
    assert "未登录" in readiness.detail


def test_runtime_loads_skills_from_backend_dot_claude(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "backend" / ".claude" / "skills" / "requirement-analysis-methodology"
    evidence_dir = tmp_path / "backend" / ".claude" / "skills" / "notebooklm-evidence-workflow"
    methodology_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (methodology_dir / "SKILL.md").write_text("METHOD_SKILL", encoding="utf-8")
    (evidence_dir / "SKILL.md").write_text("EVIDENCE_SKILL", encoding="utf-8")

    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
            notebooklm_home_dir=tmp_path / "data" / "notebooklm",
        )
    )

    assert runtime.methodology_skill == "METHOD_SKILL"
    assert runtime.evidence_skill == "EVIDENCE_SKILL"


def test_build_prompt_contains_executable_methodology_guidance(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "backend" / ".claude" / "skills" / "requirement-analysis-methodology"
    evidence_dir = tmp_path / "backend" / ".claude" / "skills" / "notebooklm-evidence-workflow"
    methodology_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (methodology_dir / "SKILL.md").write_text("METHOD_SKILL", encoding="utf-8")
    (evidence_dir / "SKILL.md").write_text("EVIDENCE_SKILL", encoding="utf-8")

    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
            notebooklm_home_dir=tmp_path / "data" / "notebooklm",
            claude_model="glm-5",
        )
    )

    prompt = runtime._build_prompt(
        AgentTurnInput(
            project=ProjectSummary(
                id="project-1",
                name="集团业财逐笔对账需求分析",
                scenario_type="reconciliation",
                summary="分析业财逐笔对账需求。",
                status="active",
                created_at="2026-04-16T10:00:00+08:00",
                updated_at="2026-04-16T10:00:00+08:00",
                seed_key="reconciliation",
            ),
            state=ProjectState(
                current_understanding=[],
                pending_items=[],
                confirmed_items=[],
                conflict_items=[],
                mvp_items=[],
                versions=[],
                artifacts=[],
            ),
            user_message="客户说需要自动核对订单和财务科目金额。",
            selected_source_ids=[],
            source_summaries=["订单字段说明", "财务科目口径说明"],
            evidence_summary="NotebookLM 摘要",
            evidence_citations=[],
            request_artifact_types=[],
        )
    )

    assert "不要把 BABOK、JTBD、Event Storming 这些术语直接写给用户" in prompt
    assert "不要把页面诉求直接当成 job" in prompt
    assert "目标、干系人、范围、约束、风险" in prompt


def test_build_prompt_includes_recent_messages_for_conversation_continuity(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "backend" / ".claude" / "skills" / "requirement-analysis-methodology"
    evidence_dir = tmp_path / "backend" / ".claude" / "skills" / "notebooklm-evidence-workflow"
    methodology_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (methodology_dir / "SKILL.md").write_text("METHOD_SKILL", encoding="utf-8")
    (evidence_dir / "SKILL.md").write_text("EVIDENCE_SKILL", encoding="utf-8")

    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
            notebooklm_home_dir=tmp_path / "data" / "notebooklm",
            claude_model="glm-5",
        )
    )

    prompt = runtime._build_prompt(
        AgentTurnInput(
            project=ProjectSummary(
                id="project-1",
                name="集团业财逐笔对账需求分析",
                scenario_type="reconciliation",
                summary="分析业财逐笔对账需求。",
                status="active",
                created_at="2026-04-16T10:00:00+08:00",
                updated_at="2026-04-16T10:00:00+08:00",
                seed_key="reconciliation",
            ),
            state=ProjectState(
                current_understanding=[],
                pending_items=[],
                confirmed_items=[],
                conflict_items=[],
                mvp_items=[],
                versions=[],
                artifacts=[],
            ),
            user_message="我前一个问题是啥？",
            selected_source_ids=[],
            source_summaries=["订单字段说明"],
            evidence_summary="NotebookLM 摘要",
            evidence_citations=[],
            request_artifact_types=[],
            recent_messages=[
                MessageRecord(
                    id="msg-1",
                    role="user",
                    content="请用一句话说明项目核心问题",
                    source_refs=[],
                    created_at="2026-04-16T10:00:00+08:00",
                    stream_group_id="stream-1",
                ),
                MessageRecord(
                    id="msg-2",
                    role="assistant",
                    content="项目核心问题是把模糊需求转成可执行输入。",
                    source_refs=[],
                    created_at="2026-04-16T10:00:10+08:00",
                    stream_group_id="stream-1",
                ),
            ],
        )
    )

    assert "最近对话记录" in prompt
    assert "用户: 请用一句话说明项目核心问题" in prompt
    assert "助手: 项目核心问题是把模糊需求转成可执行输入。" in prompt


def test_stream_assistant_text_uses_stream_event_text_deltas(monkeypatch, tmp_path: Path) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
            notebooklm_home_dir=tmp_path / "data" / "notebooklm",
            claude_cli_path="/usr/local/bin/claude",
            claude_model="glm-5",
        )
    )

    monkeypatch.setattr(runtime, "ensure_available", lambda: None)

    async def fake_query(*, prompt, options):
        yield agent_runtime_module.StreamEvent(
            uuid="1",
            session_id="s1",
            event={"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "先想一下"}},
        )
        yield agent_runtime_module.StreamEvent(
            uuid="2",
            session_id="s1",
            event={"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "第一段。"}},
        )
        yield agent_runtime_module.StreamEvent(
            uuid="3",
            session_id="s1",
            event={"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "第二段。"}},
        )
        yield agent_runtime_module.ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s1",
            stop_reason="end_turn",
            total_cost_usd=0.0,
            usage=None,
            result="第一段。第二段。",
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            errors=None,
            uuid="4",
        )

    monkeypatch.setattr(agent_runtime_module, "query", fake_query)

    async def collect():
        chunks = []
        async for chunk in runtime.stream_assistant_text(
            AgentTurnInput(
                project=ProjectSummary(
                    id="project-1",
                    name="集团业财逐笔对账需求分析",
                    scenario_type="reconciliation",
                    summary="分析业财逐笔对账需求。",
                    status="active",
                    created_at="2026-04-16T10:00:00+08:00",
                    updated_at="2026-04-16T10:00:00+08:00",
                    seed_key="reconciliation",
                ),
                state=ProjectState(
                    current_understanding=[],
                    pending_items=[],
                    confirmed_items=[],
                    conflict_items=[],
                    mvp_items=[],
                    versions=[],
                    artifacts=[],
                ),
                user_message="继续分析",
                selected_source_ids=[],
                source_summaries=[],
                evidence_summary="",
                evidence_citations=[],
                request_artifact_types=[],
            )
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())

    assert chunks == ["第一段。", "第二段。"]


def test_run_turn_wraps_invalid_structured_output_as_provider_issue(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
            notebooklm_home_dir=tmp_path / "data" / "notebooklm",
            claude_cli_path="/usr/local/bin/claude",
            claude_model="glm-5",
        )
    )

    monkeypatch.setattr(runtime, "ensure_available", lambda: None)

    async def fake_query(*, prompt, options):
        yield agent_runtime_module.ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s1",
            stop_reason="end_turn",
            total_cost_usd=0.0,
            usage=None,
            result='{"assistant_message":"坏结果","citations":[],"current_understanding":[}',
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            errors=None,
            uuid="4",
        )

    monkeypatch.setattr(agent_runtime_module, "query", fake_query)

    async def collect():
        async for _ in runtime.run_turn(
            AgentTurnInput(
                project=ProjectSummary(
                    id="project-1",
                    name="集团业财逐笔对账需求分析",
                    scenario_type="reconciliation",
                    summary="分析业财逐笔对账需求。",
                    status="active",
                    created_at="2026-04-16T10:00:00+08:00",
                    updated_at="2026-04-16T10:00:00+08:00",
                    seed_key="reconciliation",
                ),
                state=ProjectState(
                    current_understanding=[],
                    pending_items=[],
                    confirmed_items=[],
                    conflict_items=[],
                    mvp_items=[],
                    versions=[],
                    artifacts=[],
                ),
                user_message="继续分析",
                selected_source_ids=[],
                source_summaries=[],
                evidence_summary="",
                evidence_citations=[],
                request_artifact_types=[],
            ),
            assistant_message="正文",
        ):
            pass

    with pytest.raises(ProviderIssue) as exc_info:
        asyncio.run(collect())

    assert "无法解析的结构化结果" in exc_info.value.message
