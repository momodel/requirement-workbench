import asyncio
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.models import ChatCitation, ChatImageAttachment, ChatStreamRequest, ProviderIssue, StateItem
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
        claude_cli_path=str(tmp_path / "missing-claude"),
        claude_stream_timeout_seconds=0.1,
        claude_artifact_timeout_seconds=0.3,
        evidence_query_timeout_seconds=0.2,
    )


class StubEvidenceRuntime:
    def ensure_available(self):
        return Path("/tmp/qdrant")

    def query(self, project_id: str, question: str, selected_source_ids=None):
        raise AssertionError("ChatService 不应直接调用证据 runtime。")


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
                "phase": "tool_running:query_project_evidence",
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


class SlowArtifactRuntime:
    def ensure_available(self) -> None:
        return None

    async def run_streaming_turn(self, turn):
        yield (
            "assistant_status",
            {
                "phase": "tool_running:generate_artifact",
                "label": "正在生成交互稿",
            },
        )
        await asyncio.sleep(0.15)
        yield (
            "artifact_patch",
            {
                "op": "upsert",
                "items": [],
            },
        )
        yield (
            "final_message",
            {
                "text": "交互稿已写入交付物区。",
                "citations": [],
            },
        )
        yield ("done", {})


class ImageResultRuntime:
    def ensure_available(self) -> None:
        return None

    async def run_streaming_turn(self, turn):
        yield (
            "assistant_status",
            {
                "phase": "tool_running:generate_visual_mockup",
                "label": "正在生成视觉稿",
            },
        )
        yield (
            "image_result",
            {
                "title": "需求分析工作台视觉稿",
                "summary": "已生成一张工作台界面视觉稿。",
                "url": "/api/projects/seed-reconciliation/images/img-123",
                "content_type": "image/png",
            },
        )
        yield (
            "final_message",
            {
                "text": "视觉稿已生成，直接在这条消息里查看。",
                "citations": [],
            },
        )
        yield ("done", {})


class EchoImageHistoryRuntime:
    def ensure_available(self) -> None:
        return None

    async def run_streaming_turn(self, turn):
        current_user_message = next(message for message in turn.recent_messages if message.content == "看这张图")
        assert current_user_message.image_results
        yield (
            "final_message",
            {
                "text": "已收到图片。",
                "citations": [],
            },
        )
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
        evidence_runtime=StubEvidenceRuntime(),
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
    matching_messages = [
        message for message in assistant_messages if message.content == "先确认真实范围，再继续拆对账规则。"
    ]
    assert matching_messages
    assert matching_messages[-1].source_refs[0]["title"] == "订单字段说明"


def test_chat_service_persists_user_chat_image_attachment(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=EchoImageHistoryRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(
                message="看这张图",
                selected_source_ids=[],
                request_artifact_types=[],
                image_attachments=[
                    ChatImageAttachment(
                        name="界面截图.png",
                        content_type="image/png",
                        data_url="data:image/png;base64,iVBORw0KGgo=",
                    )
                ],
            ),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())
    assert events[-2][1]["text"] == "已收到图片。"

    user_message = next(
        message for message in catalog.list_recent_messages("seed-reconciliation") if message.content == "看这张图"
    )
    assert user_message.role == "user"
    assert user_message.image_results[0]["title"] == "界面截图.png"
    image_url = user_message.image_results[0]["url"]
    image_id = image_url.rsplit("/", 1)[-1]
    image_path = settings.projects_dir / "seed-reconciliation" / "chat-images" / image_id / "image.png"
    assert image_path.exists()

def test_chat_service_emits_error_and_done_when_runtime_fails(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        evidence_runtime=StubEvidenceRuntime(),
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


def test_chat_service_never_queries_evidence_runtime_directly(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    evidence_runtime = StubEvidenceRuntime()
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        evidence_runtime=evidence_runtime,
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


def test_chat_service_extends_timeout_while_generating_artifact(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=SlowArtifactRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="再来个交互稿", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert [event_type for event_type, _ in events] == [
        "assistant_status",
        "artifact_patch",
        "message_chunk",
        "done",
    ]
    assert events[0][1]["phase"] == "tool_running:generate_artifact"
    assert events[2][1]["text"] == "交互稿已写入交付物区。"


def test_chat_service_forwards_image_result_without_creating_artifact(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=ImageResultRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="生成一张界面图", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert [event_type for event_type, _ in events] == [
        "assistant_status",
        "image_result",
        "message_chunk",
        "done",
    ]
    assert events[1][1]["url"] == "/api/projects/seed-reconciliation/images/img-123"
    assert events[0][1]["phase"] == "tool_running:generate_visual_mockup"
    assert all(event_type != "artifact_patch" for event_type, _ in events)

    stream_group_id = events[-1][1]["stream_group_id"]
    assistant_message = next(
        message
        for message in catalog.list_recent_messages("seed-reconciliation")
        if message.role == "assistant" and message.stream_group_id == stream_group_id
    )
    assert assistant_message.image_results == [events[1][1]]
    assert assistant_message.source_refs == []


def test_chat_service_extends_timeout_while_generating_visual_mockup(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    class SlowImageRuntime:
        def ensure_available(self) -> None:
            return None

        async def run_streaming_turn(self, turn):
            yield (
                "assistant_status",
                {
                    "phase": "tool_running:generate_visual_mockup",
                    "label": "正在生成视觉稿",
                },
            )
            await asyncio.sleep(0.15)
            yield (
                "image_result",
                {
                    "title": "视觉稿",
                    "summary": "图片已生成。",
                    "url": "/api/projects/seed-reconciliation/images/img-456",
                    "content_type": "image/png",
                },
            )
            yield ("final_message", {"text": "图已生成。", "citations": []})
            yield ("done", {})

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=SlowImageRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="生成视觉稿", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert [event_type for event_type, _ in events] == [
        "assistant_status",
        "image_result",
        "message_chunk",
        "done",
    ]



class NeverCalledArtifactRuntime:
    def ensure_available(self) -> None:
        return None

    async def run_streaming_turn(self, turn):
        raise AssertionError("显式交付物请求不应进入主聊天 Agent loop")
        if False:
            yield ("done", {})

    async def generate_artifact(self, **kwargs):
        await asyncio.sleep(60)


def test_chat_service_starts_explicit_artifact_request_as_background_job(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    service = ChatService(
        catalog=catalog,
        project_state=ProjectStateService(catalog),
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=NeverCalledArtifactRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(
                message="生成交互稿",
                selected_source_ids=[],
                request_artifact_types=["interaction_flow"],
            ),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert [event_type for event_type, _ in events] == [
        "assistant_status",
        "artifact_patch",
        "message_chunk",
        "done",
    ]
    artifact = events[1][1]["items"][0]
    assert artifact["artifact_type"] == "interaction_flow"
    assert artifact["status"] == "generating"
    assert events[2][1]["text"] == "交付物已开始生成，完成后会出现在右侧交付物区。"


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
