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
    _coerce_html_artifact_payload,
    _normalize_generated_artifact_output_payload,
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


def test_normalize_generated_artifact_output_payload_unwraps_content_shape() -> None:
    raw = {
        "type": "interaction_flow",
        "content": {
            "title": "逐笔对账交互稿",
            "summary": "覆盖差异查看、归因确认和提交处理。",
            "html": "<!doctype html><html><head><title>交互稿</title></head><body><main>ok</main></body></html>",
        },
    }

    normalized = _normalize_generated_artifact_output_payload(raw)

    assert normalized["title"] == "逐笔对账交互稿"
    assert normalized["summary"] == "覆盖差异查看、归因确认和提交处理。"
    assert "<main>ok</main>" in normalized["html"]


def test_normalize_generated_artifact_output_payload_maps_content_html_alias() -> None:
    raw = {
        "title": "调试测试项目 - 页面方案",
        "summary": "最小测试项目的页面结构方案。",
        "content": "<!doctype html><html><head><title>页面方案</title></head><body><main>ok</main></body></html>",
    }

    normalized = _normalize_generated_artifact_output_payload(raw)

    assert normalized["title"] == "调试测试项目 - 页面方案"
    assert normalized["summary"] == "最小测试项目的页面结构方案。"
    assert normalized["html"].startswith("<!doctype html>")


def test_coerce_html_artifact_payload_parses_marker_format() -> None:
    raw = """
TITLE: 逐笔对账页面方案
SUMMARY: 覆盖总览、差异明细和异常处理三个页面。
HTML:
<!doctype html>
<html>
  <head><title>逐笔对账页面方案</title></head>
  <body><main>ok</main></body>
</html>
    """.strip()

    parsed = _coerce_html_artifact_payload(raw)

    assert parsed["title"] == "逐笔对账页面方案"
    assert parsed["summary"] == "覆盖总览、差异明细和异常处理三个页面。"
    assert "<main>ok</main>" in parsed["html"]


def test_coerce_html_artifact_payload_parses_loose_object_format() -> None:
    raw = """{
      title: "客户需求转译台 · 页面方案",
      summary: "覆盖项目概览、材料管理和需求梳理工作台。",
      content: "<!doctype html>\\n<html><head><title>页面方案</title></head><body><main>ok</main></body></html>"
    }"""

    parsed = _coerce_html_artifact_payload(raw)

    assert parsed["title"] == "客户需求转译台 · 页面方案"
    assert parsed["summary"] == "覆盖项目概览、材料管理和需求梳理工作台。"
    assert "<main>ok</main>" in parsed["html"]


def test_claude_readiness_reports_not_configured_when_model_env_missing(monkeypatch) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=Path("/tmp/project"),
            data_dir=Path("/tmp/project/data"),
            sqlite_dir=Path("/tmp/project/data/sqlite"),
            sqlite_path=Path("/tmp/project/data/sqlite/test.db"),
            projects_dir=Path("/tmp/project/data/projects"),
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

    assert readiness.status == "not_configured"
    assert "CLAUDE_MODEL" in readiness.detail
    assert readiness.action_label == "配置 Claude 模型"


def test_claude_runtime_blocks_execution_when_model_env_missing(monkeypatch) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=Path("/tmp/project"),
            data_dir=Path("/tmp/project/data"),
            sqlite_dir=Path("/tmp/project/data/sqlite"),
            sqlite_path=Path("/tmp/project/data/sqlite/test.db"),
            projects_dir=Path("/tmp/project/data/projects"),
            claude_cli_path="/usr/local/bin/claude",
            claude_model=None,
        )
    )

    monkeypatch.setattr(agent_runtime_module.Path, "exists", lambda self: True)

    with pytest.raises(ProviderIssue, match="CLAUDE_MODEL"):
        runtime.ensure_available()


def test_claude_readiness_reports_auth_required(monkeypatch) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=Path("/tmp/project"),
            data_dir=Path("/tmp/project/data"),
            sqlite_dir=Path("/tmp/project/data/sqlite"),
            sqlite_path=Path("/tmp/project/data/sqlite/test.db"),
            projects_dir=Path("/tmp/project/data/projects"),
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


def test_streaming_prompt_requires_analysis_style_explanations(tmp_path: Path) -> None:
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
            claude_model="glm-5",
        )
    )

    prompt = runtime._build_streaming_prompt(
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
            user_message="请继续分析逐笔对账场景。",
            selected_source_ids=[],
            source_summaries=["订单字段说明", "财务科目口径说明"],
            evidence_summary="NotebookLM 摘要",
            evidence_citations=[],
            request_artifact_types=[],
        )
    )

    assert "先说清楚为什么现在要问这个或判断这个" in prompt
    assert "让用户看得见你是在推进分析，不是在直接吐结论" in prompt
    assert "如果本轮已经足够形成沉淀，要顺手说明你准备写入什么" in prompt


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


def test_artifact_prompt_uses_compact_state_summary(tmp_path: Path) -> None:
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
            claude_model="glm-5",
        )
    )

    prompt = runtime._artifact_prompt(
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
            current_understanding=[
                {
                    "id": "current-1",
                    "title": "核心目标",
                    "body": "先把模糊诉求收敛成可执行方案。",
                    "status": "active",
                    "category": "current_understanding",
                    "updated_at": "2026-04-16T10:00:00+08:00",
                    "source_ids": ["src-1", "src-2"],
                }
            ],
            pending_items=[
                {
                    "id": "pending-1",
                    "title": "一期交付物边界",
                    "body": "到底是文档为主还是方案为主？",
                    "status": "active",
                    "category": "pending_items",
                    "updated_at": "2026-04-16T10:00:00+08:00",
                    "source_ids": [],
                }
            ],
            confirmed_items=[],
            conflict_items=[],
            mvp_items=[],
            versions=[],
            artifacts=[
                {
                    "id": "artifact-1",
                    "title": "旧页面方案",
                    "body": "一份较早的页面方案",
                    "status": "generated",
                    "category": "artifacts",
                    "updated_at": "2026-04-16T10:00:00+08:00",
                    "source_ids": [],
                }
            ],
        ),
        artifact_type="page_solution",
    )

    assert "当前项目状态：" not in prompt
    assert '"id": "current-1"' not in prompt
    assert '"updated_at"' not in prompt
    assert '"source_ids"' not in prompt
    assert "当前项目沉淀摘要：" in prompt
    assert "当前理解：" in prompt
    assert "待确认项：" in prompt
    assert "核心目标：先把模糊诉求收敛成可执行方案。" in prompt
    assert "一期交付物边界：到底是文档为主还是方案为主？" in prompt


def test_artifact_prompt_uses_shorter_artifact_specific_guidance(tmp_path: Path) -> None:
    methodology_dir = tmp_path / "backend" / ".claude" / "skills" / "requirement-analysis-methodology"
    evidence_dir = tmp_path / "backend" / ".claude" / "skills" / "notebooklm-evidence-workflow"
    methodology_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (methodology_dir / "SKILL.md").write_text("METHOD_SKILL" * 200, encoding="utf-8")
    (evidence_dir / "SKILL.md").write_text("EVIDENCE_SKILL", encoding="utf-8")

    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
            claude_model="glm-5",
        )
    )

    prompt = runtime._artifact_prompt(
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
        artifact_type="interaction_flow",
    )

    assert "需求分析方法参考：" not in prompt
    assert "METHOD_SKILL" not in prompt
    assert "交付物生成提醒：" in prompt
    assert "220 行内" in prompt
    assert len(prompt) < 3000


def test_stream_assistant_text_uses_stream_event_text_deltas(monkeypatch, tmp_path: Path) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
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


def test_generate_artifact_retries_html_parse_failure_once(
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
            claude_cli_path="/usr/local/bin/claude",
            claude_model="glm-5",
        )
    )

    monkeypatch.setattr(runtime, "ensure_available", lambda: None)

    call_count = {"value": 0}

    async def fake_query(*, prompt, options):
        call_count["value"] += 1
        if call_count["value"] == 1:
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
                result="我先给你一个思路说明，不按约定格式输出。",
                structured_output=None,
                model_usage=None,
                permission_denials=None,
                errors=None,
                uuid="1",
            )
            return

        yield agent_runtime_module.ResultMessage(
            subtype="success",
            duration_ms=1,
            duration_api_ms=1,
            is_error=False,
            num_turns=1,
            session_id="s2",
            stop_reason="end_turn",
            total_cost_usd=0.0,
            usage=None,
            result="TITLE: 正确页面方案\nSUMMARY: 成功重试后的结果。\nHTML:\n<!doctype html><html><head><title>页面方案</title></head><body><main>ok</main></body></html>",
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            errors=None,
            uuid="2",
        )

    monkeypatch.setattr(agent_runtime_module, "query", fake_query)

    async def run():
        return await runtime.generate_artifact(
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
            artifact_type="page_solution",
        )

    output = asyncio.run(run())

    assert call_count["value"] == 2
    assert output.title == "正确页面方案"
    assert output.summary == "成功重试后的结果。"
    assert "<main>ok</main>" in output.html
