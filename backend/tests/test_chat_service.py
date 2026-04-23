import asyncio
from pathlib import Path
import time

from app.config import AppSettings
from app.db import init_db
from app.models import (
    AgentTurnInput,
    AgentTurnResult,
    ArtifactRecord,
    ChatCitation,
    ChatStreamRequest,
    EvidenceResult,
    ProviderIssue,
    ProjectState,
    ProjectSummary,
    SourceUpsert,
)
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
        claude_stream_timeout_seconds=0.05,
        claude_structured_timeout_seconds=0.05,
        evidence_query_timeout_seconds=0.05,
    )


class StubEvidenceRuntime:
    def ensure_available(self) -> Path:
        return Path("/tmp/evidence-runtime")

    def query(
        self,
        project_id: str,
        question: str,
        *,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        return EvidenceResult(summary="stub evidence", citations=[])


class StubArtifactGenerationService:
    def __init__(self, generated_artifacts: list[ArtifactRecord] | None = None) -> None:
        self.generated_artifacts = generated_artifacts or []
        self.calls: list[dict] = []

    async def generate_from_model(self, **kwargs):
        self.calls.append(kwargs)
        if self.generated_artifacts:
            return self.generated_artifacts.pop(0)
        raise AssertionError("this test should not generate artifacts")


class EmptyPatchAgentRuntime:
    def ensure_available(self) -> None:
        return None

    async def stream_assistant_text(self, turn: AgentTurnInput):
        if False:
            yield ""

    async def run_turn(self, turn: AgentTurnInput, assistant_message: str | None = None):
        yield (
            "result",
            AgentTurnResult(
                assistant_message=assistant_message or "这一轮只补充聊天结论，不应该清空已有沉淀。",
                citations=[ChatCitation(title="stub", snippet="stub", source_id=None)],
                state_updates={
                    "current_understanding": [],
                    "pending_items": [],
                    "confirmed_items": [],
                    "conflict_items": [],
                    "mvp_items": [],
                },
                version_summary=None,
                request_artifacts=[],
            ),
        )

    async def generate_artifact(self, **kwargs):
        raise AssertionError("this test should not generate artifacts")


class ChunkThenPatchAgentRuntime:
    def __init__(self) -> None:
        self.turns: list[AgentTurnInput] = []

    def ensure_available(self) -> None:
        return None

    async def stream_assistant_text(self, turn: AgentTurnInput):
        self.turns.append(turn)
        yield "先确认范围，"
        yield "再补沉淀。"

    async def run_turn(self, turn: AgentTurnInput, assistant_message: str | None = None):
        yield (
            "result",
            AgentTurnResult(
                assistant_message=assistant_message or "先确认范围，再补沉淀。",
                citations=[ChatCitation(title="stub", snippet="stub", source_id=None)],
                state_updates={
                    "current_understanding": [
                        SourceUpsert(
                            title="真实需求先收敛范围",
                            body="先确认逐笔对账范围，再推进 MVP 能力。",
                            source_ids=[],
                            status="active",
                        )
                    ],
                    "pending_items": [],
                    "confirmed_items": [],
                    "conflict_items": [],
                    "mvp_items": [],
                },
                version_summary=None,
                request_artifacts=[],
            ),
        )

    async def generate_artifact(self, **kwargs):
        raise AssertionError("this test should not generate artifacts")


class SlowEvidenceRuntime:
    def ensure_available(self) -> Path:
        return Path("/tmp/evidence-runtime")

    def query(
        self,
        project_id: str,
        question: str,
        *,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        time.sleep(0.2)
        return EvidenceResult(summary="slow evidence", citations=[])


class SlowStructuredAgentRuntime:
    def ensure_available(self) -> None:
        return None

    async def stream_assistant_text(self, turn: AgentTurnInput):
        yield "先输出正文。"

    async def run_turn(self, turn: AgentTurnInput, assistant_message: str | None = None):
        await asyncio.sleep(0.2)
        if False:
            yield ("result", None)

    async def generate_artifact(self, **kwargs):
        raise AssertionError("this test should not generate artifacts")


class StreamOnlyAgentRuntime:
    def __init__(self) -> None:
        self.turns: list[AgentTurnInput] = []

    def ensure_available(self) -> None:
        return None

    async def stream_assistant_text(self, turn: AgentTurnInput):
        self.turns.append(turn)
        yield "这是普通追问回复。"

    async def run_turn(self, turn: AgentTurnInput, assistant_message: str | None = None):
        if False:
            yield ("result", None)
        raise AssertionError("ordinary follow-up should not trigger structured patch")

    async def generate_artifact(self, **kwargs):
        raise AssertionError("this test should not generate artifacts")


class FailingEvidenceRuntime:
    def __init__(self, issue: ProviderIssue) -> None:
        self.issue = issue

    def ensure_available(self) -> Path:
        return Path("/tmp/evidence-runtime")

    def query(
        self,
        project_id: str,
        question: str,
        *,
        selected_source_ids: list[str] | None = None,
    ) -> EvidenceResult:
        raise self.issue


def test_empty_state_updates_do_not_wipe_existing_state(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)
    project = catalog.get_project("seed-reconciliation")
    assert project is not None

    before = project_state.get_project_state("seed-reconciliation")
    assert before.current_understanding, "seed project should start with existing understanding"
    assert before.pending_items, "seed project should start with pending items"

    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=EmptyPatchAgentRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="请总结当前结论", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    after = project_state.get_project_state("seed-reconciliation")

    assert any(event_type == "message_chunk" for event_type, _ in events)
    assert after.current_understanding == before.current_understanding
    assert after.pending_items == before.pending_items
    assert after.confirmed_items == before.confirmed_items
    assert after.conflict_items == before.conflict_items
    assert after.mvp_items == before.mvp_items


def test_chat_chunks_stream_before_structured_patches_without_replace_event(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    agent_runtime = ChunkThenPatchAgentRuntime()
    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=agent_runtime,
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="请总结当前结论", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())
    status_events = [payload for event_type, payload in events if event_type == "assistant_status"]
    message_chunks = [payload for event_type, payload in events if event_type == "message_chunk"]
    patch_indexes = [
        index for index, (event_type, _) in enumerate(events) if event_type == "current_understanding_patch"
    ]
    first_status_index = next(
        index for index, (event_type, _) in enumerate(events) if event_type == "assistant_status"
    )
    first_chunk_index = next(
        index for index, (event_type, _) in enumerate(events) if event_type == "message_chunk"
    )

    assert status_events, "status events should be emitted before assistant text"
    assert status_events[0]["phase"] == "source_scan"
    assert any(
        payload["phase"] == "evidence_query" and "项目知识库证据" in payload["label"]
        for payload in status_events
    )
    assert [payload["text"] for payload in message_chunks] == ["先确认范围，", "再补沉淀。"]
    assert all("replace" not in payload for payload in message_chunks)
    assert first_status_index < first_chunk_index
    assert patch_indexes, "structured patches should still be emitted"
    assert patch_indexes[0] > max(
        index for index, (event_type, _) in enumerate(events) if event_type == "message_chunk"
    )

    messages = catalog.list_recent_messages("seed-reconciliation")
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert assistant_messages
    assert any(message.content == "先确认范围，再补沉淀。" for message in assistant_messages)
    assert agent_runtime.turns
    assert agent_runtime.turns[0].evidence_summary == "stub evidence"


def test_chat_turn_times_out_evidence_query_but_continues(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    agent_runtime = ChunkThenPatchAgentRuntime()
    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=SlowEvidenceRuntime(),
        agent_runtime=agent_runtime,
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="请总结当前结论", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert not any(event_type == "error" for event_type, _ in events)
    assert any(
        event_type == "assistant_status" and payload["phase"] == "drafting"
        for event_type, payload in events
    )
    assert any(
        event_type == "assistant_status"
        and payload["phase"] == "drafting"
        and "检索超时" in payload["label"]
        for event_type, payload in events
    )
    assert any(event_type == "message_chunk" for event_type, _ in events)
    assert agent_runtime.turns
    assert "检索超时" in agent_runtime.turns[0].evidence_summary
    assert events[-1][0] == "done"


def test_chat_turn_times_out_structured_patch_and_finishes(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=SlowStructuredAgentRuntime(),
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="请总结当前结论", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert any(event_type == "message_chunk" for event_type, _ in events)
    assert any(
        event_type == "assistant_status" and payload["phase"] == "state_patch"
        for event_type, payload in events
    )
    assert not any(event_type == "error" for event_type, _ in events)
    messages = catalog.list_recent_messages("seed-reconciliation")
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert assistant_messages
    assert any(message.content == "先输出正文。" for message in assistant_messages)
    assert events[-1][0] == "done"


def test_meta_follow_up_streams_text_without_structured_patch(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    agent_runtime = StreamOnlyAgentRuntime()
    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=agent_runtime,
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(
                message="你刚才问的前一个问题是什么？",
                selected_source_ids=[],
                request_artifact_types=[],
            ),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert any(event_type == "message_chunk" for event_type, _ in events)
    assert not any(
        event_type == "assistant_status" and payload["phase"] == "state_patch"
        for event_type, payload in events
    )
    assert not any(event_type.endswith("_patch") for event_type, _ in events)
    assert events[-1][0] == "done"
    messages = catalog.list_recent_messages("seed-reconciliation")
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert any(message.content == "这是普通追问回复。" for message in assistant_messages)
    assert agent_runtime.turns
    assert agent_runtime.turns[0].evidence_summary == "stub evidence"


def test_explicit_artifact_request_still_runs_structured_turn(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    agent_runtime = ChunkThenPatchAgentRuntime()
    artifact_generation = StubArtifactGenerationService(
        generated_artifacts=[
            ArtifactRecord(
                id="artifact-page-solution-1",
                project_id="seed-reconciliation",
                artifact_type="page_solution",
                title="页面方案草稿",
                summary="用于验证显式 artifact 请求仍会进入 structured turn。",
                status="generated",
                content_format="html",
                storage_path=str(tmp_path / "page-solution" / "index.html"),
                preview_url=None,
                body=None,
                updated_at="2026-04-23T18:55:11+08:00",
            )
        ]
    )
    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=agent_runtime,
        artifact_generation=artifact_generation,
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(
                message="请生成页面方案",
                selected_source_ids=[],
                request_artifact_types=["page_solution"],
            ),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert any(event_type == "message_chunk" for event_type, _ in events)
    assert any(
        event_type == "assistant_status" and payload["phase"] == "state_patch"
        for event_type, payload in events
    )
    assert artifact_generation.calls
    assert events[-1][0] == "done"


def test_chat_skips_structured_patch_for_ordinary_business_question(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)

    agent_runtime = StreamOnlyAgentRuntime()
    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=StubEvidenceRuntime(),
        agent_runtime=agent_runtime,
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="退款口径怎么处理", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert any(event_type == "message_chunk" for event_type, _ in events)
    assert not any(
        event_type == "assistant_status" and payload["phase"] == "state_patch"
        for event_type, payload in events
    )
    assert not any(event_type.endswith("_patch") for event_type, _ in events)
    messages = catalog.list_recent_messages("seed-reconciliation")
    assistant_messages = [message for message in messages if message.role == "assistant"]
    assert any(message.content == "这是普通追问回复。" for message in assistant_messages)
    assert agent_runtime.turns
    assert agent_runtime.turns[0].evidence_summary == "stub evidence"


def test_chat_preserves_concrete_evidence_failure_reason_in_status_and_prompt(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    ensure_seed_project(settings)

    catalog = ProjectCatalog(settings)
    project_state = ProjectStateService(catalog)
    issue = ProviderIssue(
        provider="QDRANT_LLAMA_INDEX",
        message="当前项目还没有初始化项目内知识库。",
        status_code=503,
    )
    agent_runtime = StreamOnlyAgentRuntime()
    service = ChatService(
        catalog=catalog,
        project_state=project_state,
        evidence_runtime=FailingEvidenceRuntime(issue),
        agent_runtime=agent_runtime,
        artifact_generation=StubArtifactGenerationService(),
    )

    async def collect_events():
        events = []
        async for event_type, payload in service.stream_turn(
            "seed-reconciliation",
            ChatStreamRequest(message="退款口径怎么处理", selected_source_ids=[], request_artifact_types=[]),
        ):
            events.append((event_type, payload))
        return events

    events = asyncio.run(collect_events())

    assert any(
        event_type == "assistant_status"
        and payload["phase"] == "drafting"
        and "当前项目还没有初始化项目内知识库" in payload["label"]
        for event_type, payload in events
    )
    assert agent_runtime.turns
    assert agent_runtime.turns[0].evidence_summary == "项目知识库证据检索失败：当前项目还没有初始化项目内知识库。"
