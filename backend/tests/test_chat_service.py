import asyncio
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import ChatCitation, ChatStreamRequest, ProviderIssue, StateItem
from app.services.chat_service import ChatService
from app.services.project_catalog import ProjectCatalog
from app.services.project_state import ProjectStateService
from app.services.seed_projects import ensure_seed_project


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        notebooklm_home_dir=data_dir / "notebooklm",
        claude_cli_path=str(tmp_path / "missing-claude"),
        claude_stream_timeout_seconds=0.1,
    )


class StubEvidenceRuntime:
    def ensure_available(self):
        return Path("/tmp/notebooklm")

    def query(self, project_id: str, question: str, selected_source_ids=None):
        raise AssertionError("ChatService 不应直接调用 NotebookLM。")


class StubArtifactGenerationService:
    pass


class StreamingAgentRuntime:
    def ensure_available(self) -> None:
        return None

    async def run_streaming_turn(self, turn):
        yield ("assistant_status", {"phase": "agent_started", "label": "已接收问题，正在启动分析"})
        yield ("message_chunk", {"text": "先确认真实范围，"})
        yield (
            "assistant_status",
            {
                "phase": "tool_running:query_notebook_evidence",
                "label": "正在检索资料证据",
            },
        )
        yield (
            "citations",
            {
                "items": [
                    ChatCitation(
                        title="订单字段说明",
                        snippet="订单号与入账记录需要一一映射。",
                        source_id="source-1",
                    ).model_dump()
                ]
            },
        )
        yield (
            "current_understanding_patch",
            {
                "op": "replace",
                "items": [
                    {
                        "id": "current-1",
                        "title": "真实目标是逐笔核对",
                        "body": "不是泛看报表，而是核对业务单据与财务科目金额是否一致。",
                        "status": "active",
                        "category": "current_understanding",
                        "updated_at": "2026-04-21T10:00:00+08:00",
                        "source_ids": ["source-1"],
                    }
                ],
            },
        )
        yield (
            "final_message",
            {
                "text": "先确认真实范围，再继续拆对账规则。",
                "citations": [
                    ChatCitation(
                        title="订单字段说明",
                        snippet="订单号与入账记录需要一一映射。",
                        source_id="source-1",
                    ).model_dump()
                ],
            },
        )
        yield ("done", {})


class FailingAgentRuntime:
    def ensure_available(self) -> None:
        return None

    async def run_streaming_turn(self, turn):
        yield ("message_chunk", {"text": "我先开始分析。"})
        raise ProviderIssue(provider="CLAUDE_AGENT_SDK", message="Claude 调用失败。")
        if False:
            yield ("done", {})


def test_chat_service_thin_shell_forwards_runtime_events_and_persists_final_message(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        notebooklm=StubEvidenceRuntime(),
        agent_runtime=StreamingAgentRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="继续分析", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert [event_type for event_type, _ in events] == [
        "assistant_status",
        "message_chunk",
        "assistant_status",
        "citations",
        "current_understanding_patch",
        "message_chunk",
        "done",
    ]
    assert events[-2][1] == {
        "text": "先确认真实范围，再继续拆对账规则。",
        "replace": True,
    }

    messages = catalog.list_recent_messages("seed-reconciliation", limit=8)
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert assistant_messages
    assert assistant_messages[0].content == "先确认真实范围，再继续拆对账规则。"
    assert assistant_messages[0].source_refs[0]["title"] == "订单字段说明"


def test_chat_service_emits_error_and_done_when_runtime_fails(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        notebooklm=StubEvidenceRuntime(),
        agent_runtime=FailingAgentRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="继续分析", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert [event_type for event_type, _ in events] == [
        "message_chunk",
        "error",
        "done",
    ]
    assert events[1][1]["provider"] == "CLAUDE_AGENT_SDK"
    assert "Claude 调用失败" in events[1][1]["message"]


def test_chat_service_never_queries_notebooklm_directly(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    notebooklm = StubEvidenceRuntime()
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        notebooklm=notebooklm,
        agent_runtime=StreamingAgentRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="继续分析", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert any(event_type == "citations" for event_type, _ in events)


def test_project_state_append_category_keeps_existing_items(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    existing = project_state.get_project_state("seed-reconciliation").pending_items
    project_state.append_category(
        project_id="seed-reconciliation",
        category="pending_items",
        items=[
            StateItem(
                id="pending-new-1",
                title="新增待确认项",
                body="需要确认一期范围。",
                status="active",
                category="pending_items",
                updated_at="2026-04-21T22:50:00+08:00",
                source_ids=[],
            )
        ],
    )

    latest = project_state.get_project_state("seed-reconciliation").pending_items

    assert len(latest) == len(existing) + 1
    assert any(item.id == "pending-new-1" for item in latest)
