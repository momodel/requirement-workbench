import asyncio
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from app.config import AppSettings
from app.db import init_db
from app.services import agent_runtime as agent_runtime_module
from app.models import AgentStructuredOutput, AgentTurnInput, MessageRecord, ProjectState, ProjectSummary, ProviderIssue
from app.services.agent_runtime import (
    ClaudeAgentRuntime,
    _coerce_json_payload,
    _coerce_html_artifact_payload,
    _normalize_generated_artifact_output_payload,
    _normalize_structured_output_payload,
)
from app.services.project_catalog import ProjectCatalog
from app.services.project_state import ProjectStateService
from app.services.seed_projects import ensure_seed_project


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
                "source": "项目知识库 grounding",
            },
        ],
        "pending_items": [
            {
                "id": "P001",
                "question": "退款和冲销是否都纳入一期？",
                "source": "项目知识库 grounding",
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
    assert "项目知识库 grounding" in output.current_understanding[3].body
    assert output.pending_items[0].title == "退款和冲销是否都纳入一期？"
    assert "项目知识库 grounding" in output.pending_items[0].body
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


def test_claude_readiness_uses_default_model_when_model_env_missing(monkeypatch) -> None:
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
    assert "未配置模型" in readiness.summary


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


def test_runtime_uses_project_root_as_claude_cwd(tmp_path: Path) -> None:
    runtime = ClaudeAgentRuntime(
        AppSettings(
            root_dir=tmp_path,
            data_dir=tmp_path / "data",
            sqlite_dir=tmp_path / "data" / "sqlite",
            sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
            projects_dir=tmp_path / "data" / "projects",
        )
    )
    options = runtime._build_options(
        system_prompt="测试系统提示词",
        include_partial_messages=True,
    )
    assert options.cwd == str(tmp_path)


def test_runtime_builds_isolated_claude_options(tmp_path: Path) -> None:
    (tmp_path / "backend").mkdir()
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

    options = runtime._build_options(
        system_prompt="测试系统提示词",
        include_partial_messages=True,
        output_format={"type": "object"},
    )

    assert options.setting_sources == ["project", "local"]
    assert options.plugins == []
    assert options.env["CLAUDE_CONFIG_DIR"] == str(tmp_path / "backend" / ".claude-runtime")
    assert Path(options.env["CLAUDE_CONFIG_DIR"]).exists()
    assert options.cwd == str(tmp_path / "backend")
    assert options.model == "glm-5"


def test_runtime_uses_bypass_permissions_when_mcp_tools_enabled(tmp_path: Path) -> None:
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

    options = runtime._build_options(
        system_prompt="测试系统提示词",
        include_partial_messages=True,
        mcp_servers={"artifacts": agent_runtime_module.create_sdk_mcp_server("demo")},
        allowed_tools=["generate_artifact"],
    )

    assert options.permission_mode == "bypassPermissions"


def test_build_prompt_contains_executable_methodology_guidance(tmp_path: Path) -> None:
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

    prompt = runtime._build_structured_prompt(
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
            evidence_summary="项目知识库摘要",
            evidence_citations=[],
            request_artifact_types=[],
        )
    )

    assert "不要把 BABOK、JTBD、Event Storming 这些术语直接写给用户" in prompt
    assert "不要把页面诉求直接当成 job" in prompt
    assert "目标、干系人、范围、约束、风险" in prompt


def test_streaming_prompt_requires_analysis_style_explanations(tmp_path: Path) -> None:
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
            evidence_summary="项目知识库摘要",
            evidence_citations=[],
            request_artifact_types=[],
        )
    )

    assert "先说清楚为什么现在要问这个或判断这个" in prompt
    assert "让用户看得见你是在推进分析，不是在直接吐结论" in prompt
    assert "如果本轮已经足够形成沉淀，要顺手说明你准备写入什么" in prompt
    assert "只有当你判断本轮确实应该触发交付物时" in prompt


def test_loop_prompt_distinguishes_discussion_from_real_actions(tmp_path: Path) -> None:
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

    prompt = runtime._build_loop_prompt(
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
            user_message="当前版本还是不像个网页，你觉得怎么改，给我个计划，不要直接开始改",
            selected_source_ids=[],
            source_summaries=["订单字段说明"],
            evidence_summary="",
            evidence_citations=[],
            request_artifact_types=[],
        )
    )

    assert "如果只是讨论、评审、头脑风暴、要计划、要求“不要直接开始改”，通常只聊天" in prompt
    assert "`query_project_evidence`" in prompt
    assert "`update_project_state`" in prompt
    assert "`create_version_snapshot`" in prompt
    assert "`generate_artifact`" in prompt


def test_structured_prompt_requires_artifact_request_to_match_assistant_commitment(tmp_path: Path) -> None:
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

    prompt = runtime._build_structured_prompt(
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
            user_message="做啊",
            selected_source_ids=[],
            source_summaries=["订单字段说明"],
            evidence_summary="项目知识库摘要",
            evidence_citations=[],
            request_artifact_types=[],
        ),
        assistant_message="好，我现在把它整理成一版页面方案。",
    )

    assert "本轮必须直接调用 `generate_artifact`" in prompt
    assert "不能遗漏" in prompt
    assert "调用 `generate_artifact`" in prompt


def test_build_prompt_includes_recent_messages_for_conversation_continuity(tmp_path: Path) -> None:
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
            evidence_summary="项目知识库摘要",
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
    assert "交付物生成提醒：" in prompt
    assert "整体尽量保持紧凑" in prompt
    assert "并覆盖主流程所需的关键交互入口、状态反馈和流程推进" in prompt
    assert "不要写成整页大段说明文档" in prompt
    assert "标题用自然中文，能反映当前交互场景或任务" in prompt
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
            result="ignored",
                structured_output={
                    "assistant_message": "坏结果",
                    "citations": [],
                    "current_understanding": [],
                    "pending_items": [],
                    "confirmed_items": [],
                    "conflict_items": [],
                    "mvp_items": [],
                    "version_summary": None,
                    "request_artifacts": ["bad_artifact_type"],
                },
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


def test_run_turn_returns_plain_result_when_provider_only_finishes_text(
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
    monkeypatch.setattr(
        runtime,
        "_turn_mcp_servers",
        lambda **kwargs: {"project-actions": agent_runtime_module.create_sdk_mcp_server("demo")},
    )

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
            result="已完成本轮处理。",
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            errors=None,
            uuid="4",
        )

    monkeypatch.setattr(agent_runtime_module, "query", fake_query)

    async def collect():
        events = []
        async for event in runtime.run_turn(
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
            assistant_message="正文已发出",
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    assert len(events) == 1
    event_type, result = events[0]
    assert event_type == "result"
    assert result.assistant_message == "正文已发出"
    assert result.persisted_state_updates == {}
    assert result.generated_artifacts == []
    assert result.generated_versions == []


def test_run_turn_emits_tool_status_events_from_stream_events(
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
    monkeypatch.setattr(
        runtime,
        "_turn_mcp_servers",
        lambda **kwargs: {"project-actions": agent_runtime_module.create_sdk_mcp_server("demo")},
    )

    async def fake_query(*, prompt, options):
        yield agent_runtime_module.StreamEvent(
            uuid="1",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 0,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "update_project_state",
                    "input": {},
                },
            },
        )
        yield agent_runtime_module.StreamEvent(
            uuid="2",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 1,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "create_version_snapshot",
                    "input": {},
                },
            },
        )
        yield agent_runtime_module.StreamEvent(
            uuid="3",
            session_id="s1",
            event={
                "type": "content_block_start",
                "index": 2,
                "content_block": {
                    "type": "tool_use",
                    "id": "toolu_3",
                    "name": "generate_artifact",
                    "input": {},
                },
            },
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
            result="已处理完成。",
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            errors=None,
            uuid="4",
        )

    monkeypatch.setattr(agent_runtime_module, "query", fake_query)

    async def collect():
        events = []
        async for event in runtime.run_turn(
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
            assistant_message="正文已发出",
        ):
            events.append(event)
        return events

    events = asyncio.run(collect())

    status_events = [value for event_type, value in events if event_type == "status"]
    assert status_events == [
        {"phase": "tool_running:update_project_state", "label": "正在写入本轮沉淀"},
        {"phase": "tool_running:create_version_snapshot", "label": "正在生成版本快照"},
        {"phase": "tool_running:generate_artifact", "label": "正在生成交付物预览"},
    ]
    assert events[-1][0] == "result"


def test_run_turn_uses_tool_side_effects_as_primary_result(
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

    captured: dict[str, object] = {}

    def fake_turn_mcp_servers(**kwargs):
        captured["applied_state_updates"] = kwargs["applied_state_updates"]
        captured["generated_artifacts"] = kwargs["generated_artifacts"]
        captured["generated_versions"] = kwargs["generated_versions"]
        return {"project-actions": agent_runtime_module.create_sdk_mcp_server("demo")}

    async def fake_query(*, prompt, options):
        captured["applied_state_updates"]["current_understanding"] = [
            agent_runtime_module.StateItem(
                id="current-1",
                title="核心冲突",
                body="业务字段与财务科目映射口径不一致。",
                status="active",
                category="current_understanding",
                updated_at="2026-04-21T10:00:00+08:00",
                source_ids=["src-1"],
            )
        ]
        captured["generated_versions"].append(
            agent_runtime_module.StateItem(
                id="version-1",
                title="analysis_checkpoint",
                body="已形成当前真实需求摘要。",
                status="active",
                category="versions",
                updated_at="2026-04-21T10:00:01+08:00",
                source_ids=[],
            )
        )
        captured["generated_artifacts"].append(
            agent_runtime_module.ArtifactRecord(
                id="artifact-1",
                project_id="project-1",
                artifact_type="interaction_flow",
                title="交互稿",
                summary="摘要",
                status="generated",
                content_format="html",
                storage_path="/tmp/interaction_flow.html",
                preview_url="/api/projects/project-1/artifacts/artifact-1/preview",
                body=None,
                updated_at="2026-04-21T10:00:02+08:00",
            )
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
            result="已写入项目状态和交付物。",
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            errors=None,
            uuid="4",
        )

    monkeypatch.setattr(runtime, "_turn_mcp_servers", fake_turn_mcp_servers)
    monkeypatch.setattr(agent_runtime_module, "query", fake_query)

    async def collect():
        async for event_type, result in runtime.run_turn(
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
            assistant_message="好，我继续整理。",
        ):
            return event_type, result
        return None

    event_type, result = asyncio.run(collect())

    assert event_type == "result"
    assert "current_understanding" in result.persisted_state_updates
    assert result.persisted_state_updates["current_understanding"][0].title == "核心冲突"
    assert result.generated_versions[0].title == "analysis_checkpoint"
    assert result.generated_artifacts[0].artifact_type == "interaction_flow"


def test_commit_artifacts_registers_in_process_artifact_tool(monkeypatch, tmp_path: Path) -> None:
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

    captured: dict[str, list] = {}

    async def fake_query(*, prompt, options):
        assert options.allowed_tools == ["generate_artifact"]
        assert options.mcp_servers is not None
        assert "artifacts" in options.mcp_servers
        captured["artifacts"].append(
            agent_runtime_module.ArtifactRecord(
                id="artifact-1",
                project_id="project-1",
                artifact_type="interaction_flow",
                title="交互稿",
                summary="摘要",
                status="generated",
                content_format="html",
                storage_path="/tmp/interaction_flow.html",
                preview_url="/api/projects/project-1/artifacts/artifact-1/preview",
                body=None,
                updated_at="2026-04-21T10:00:00+08:00",
            )
        )
        captured["versions"].append(
            agent_runtime_module.StateItem(
                id="version-1",
                title="artifact_generated",
                body="已生成 interaction_flow 交付物：交互稿",
                status="active",
                category="versions",
                updated_at="2026-04-21T10:00:01+08:00",
                source_ids=[],
            )
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
            result="已写入交付物区。",
            structured_output=None,
            model_usage=None,
            permission_denials=None,
            errors=None,
            uuid="4",
        )

    monkeypatch.setattr(agent_runtime_module, "query", fake_query)
    monkeypatch.setattr(
        runtime,
        "_artifact_mcp_servers",
        lambda **kwargs: captured.update(
            {
                "artifacts": kwargs["generated_artifacts"],
                "versions": kwargs["generated_versions"],
            }
        ) or {"artifacts": agent_runtime_module.create_sdk_mcp_server("demo")},
    )

    artifacts, versions = asyncio.run(
        runtime.commit_artifacts(
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
            artifact_types=["interaction_flow"],
            assistant_message="好，我现在开始整理。",
        )
    )

    assert len(artifacts) == 1
    assert len(versions) == 1
    assert artifacts[0].title == "交互稿"


def test_generate_artifact_tool_creates_artifact_and_version(tmp_path: Path) -> None:
    settings = AppSettings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        sqlite_dir=tmp_path / "data" / "sqlite",
        sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
        projects_dir=tmp_path / "data" / "projects",
        claude_cli_path="/usr/local/bin/claude",
        claude_model="glm-5",
    )
    init_db(settings)
    ensure_seed_project(settings)

    runtime = ClaudeAgentRuntime(settings)
    project = runtime.catalog.get_project("seed-reconciliation")
    assert project is not None
    state = runtime.project_state_service.get_project_state("seed-reconciliation")
    generated_artifacts = []
    generated_versions = []

    tool_def = runtime._make_generate_artifact_tool(
        project=project,
        state=state,
        generated_artifacts=generated_artifacts,
        generated_versions=generated_versions,
    )

    result = asyncio.run(
        tool_def.handler(
            {
                "artifact_type": "interaction_flow",
                "title": "逐笔对账交互稿",
                "summary": "覆盖聊天推进、沉淀联动和交付预览。",
                "html": "<!doctype html><html><head><title>逐笔对账交互稿</title></head><body><main>ok</main></body></html>",
                "focus": "先覆盖创建项目到生成交付物主流程",
                "working_notes": "强调聊天推进和右侧沉淀联动",
            }
        )
    )

    assert generated_artifacts
    assert generated_versions
    assert generated_artifacts[0].artifact_type == "interaction_flow"
    assert generated_versions[0].title == "artifact_generated"
    assert result["content"][0]["type"] == "text"
    assert "逐笔对账交互稿" in result["content"][0]["text"]
    saved_artifact = runtime.catalog.get_artifact(project.id, generated_artifacts[0].id)
    assert saved_artifact is not None


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
