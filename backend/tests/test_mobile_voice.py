import asyncio
import json
import threading
from pathlib import Path

from app.config import AppSettings
from app.db import init_db
from app.main import build_services
from app.models import CreateProjectRequest, ProviderReadiness, StateItem, VoiceTranscriptEntry
from app.services.volcengine_realtime_voice import (
    FLAG_EVENT,
    MESSAGE_TYPE_FULL_CLIENT_REQUEST,
    RealtimeTranscriptState,
    SERIALIZATION_JSON,
)


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        claude_cli_path=str(tmp_path / "fake-claude"),
        volcengine_voice_app_id="app-id",
        volcengine_voice_access_key="access-key",
    )


def install_fake_evidence_runtime(services) -> None:
    def fake_global_readiness() -> ProviderReadiness:
        return ProviderReadiness(
            provider="QDRANT_LLAMA_INDEX",
            status="ready",
            summary="项目内证据运行时已就绪。",
            detail="qdrant path: fake",
            action_label=None,
        )

    def fake_project_readiness(project_id: str, claude=None) -> ProviderReadiness:
        return ProviderReadiness(
            provider="QDRANT_LLAMA_INDEX",
            status="ready",
            summary=f"{project_id} knowledge base ready",
            detail=None,
            action_label=None,
        )

    def fake_ensure_project_knowledge_base(project_id: str):
        project = services.catalog.get_project(project_id)
        assert project is not None
        return services.catalog.upsert_knowledge_base(
            project_id=project_id,
            provider="QDRANT_LLAMA_INDEX",
            external_knowledge_base_id=f"kb-{project_id}",
            display_name=f"{project.name} Evidence KB",
            description=project.summary,
            status="ready",
            status_error=None,
        )

    def fake_reindex_source(project_id: str, source_id: str):
        services.catalog.update_source_index_status(
            source_id=source_id,
            index_status="indexed",
            index_error=None,
        )
        return []

    services.evidence_runtime.get_global_readiness = fake_global_readiness
    services.evidence_runtime.get_project_readiness = fake_project_readiness
    services.evidence_runtime.ensure_project_knowledge_base = fake_ensure_project_knowledge_base
    services.evidence_runtime.reindex_source = fake_reindex_source


def test_mobile_voice_round_syncs_into_source_and_prompt(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    services = build_services(settings)
    install_fake_evidence_runtime(services)

    project = services.catalog.create_project(
        CreateProjectRequest(
            name="移动端语音访谈",
            scenario_type="mobile-voice",
            summary="客户用手机和需求助手做实时语音访谈。",
        )
    )
    services.project_state.append_category(
        project_id=project.id,
        category="pending_items",
        items=[
            StateItem(
                id="pending-1",
                title="确认首期范围",
                body="先确认手机端是否只做语音访谈和知识库入库。",
                source_ids=[],
            )
        ],
    )

    bootstrap = services.mobile_voice.get_bootstrap(project.id)
    assert bootstrap.voice.status == "ready"
    assert "客户需求转译台的手机端语音访谈助手" in bootstrap.initial_prompt
    assert "确认首期范围" in bootstrap.initial_prompt

    round_context = services.mobile_voice.create_round(project.id)
    assert round_context.source.source_kind == "voice_session"
    assert Path(round_context.source.storage_path or "").exists()
    assert "需求澄清" in round_context.initial_prompt

    updated = services.mobile_voice.sync_round(
        project_id=project.id,
        source_id=round_context.source.id,
        entries=[
            VoiceTranscriptEntry(role="user", text="我们手机端只保留语音访谈。", is_final=True),
            VoiceTranscriptEntry(
                role="assistant",
                text="收到，我会围绕语音访谈和知识库沉淀继续追问。",
                is_final=True,
            ),
        ],
        finished=True,
    )

    assert updated.index_status == "indexed"
    assert "本轮已结束" in (updated.normalize_summary or "")

    content = Path(updated.storage_path or "").read_text(encoding="utf-8")
    assert "我们手机端只保留语音访谈。" in content
    assert "我会围绕语音访谈和知识库沉淀继续追问。" in content
    assert "轮次状态：已结束" in content


def test_mobile_voice_recent_rounds_only_include_closed_sessions(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    services = build_services(settings)
    install_fake_evidence_runtime(services)

    project = services.catalog.create_project(
        CreateProjectRequest(
            name="voice session visibility",
            scenario_type="mobile-voice",
            summary="Only closed voice sessions should count as interview records.",
        )
    )

    round_context = services.mobile_voice.create_round(project.id)
    assert services.mobile_voice.list_recent_rounds(project.id) == []

    services.mobile_voice.sync_round(
        project_id=project.id,
        source_id=round_context.source.id,
        entries=[],
        finished=True,
    )

    recent_rounds = services.mobile_voice.list_recent_rounds(project.id)
    assert len(recent_rounds) == 1
    assert "本轮已结束" in (recent_rounds[0].normalize_summary or "")


def test_realtime_voice_flushes_follow_up_updates_before_session_end(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    init_db(settings)
    services = build_services(settings)
    install_fake_evidence_runtime(services)

    project = services.catalog.create_project(
        CreateProjectRequest(
            name="实时语音写库",
            scenario_type="mobile-voice",
            summary="验证 flush 进行中追加的新转写也会续刷到知识库。",
        )
    )

    original_sync_round = services.mobile_voice.sync_round
    sync_calls: list[tuple[bool, list[str]]] = []
    first_flush_started = threading.Event()
    release_first_flush = threading.Event()

    def observed_sync_round(*, project_id: str, source_id: str, entries, finished: bool):
        sync_calls.append((finished, [entry.text for entry in entries]))
        if not finished and len(sync_calls) == 1:
            first_flush_started.set()
            assert release_first_flush.wait(timeout=1)
        return original_sync_round(
            project_id=project_id,
            source_id=source_id,
            entries=entries,
            finished=finished,
        )

    class FakeUpstream:
        def __init__(self) -> None:
            self.disconnect_event = asyncio.Event()
            self.messages = [
                _provider_event_bytes(
                    451,
                    {
                        "question_id": "q-1",
                        "results": [{"text": "先确认一期范围", "is_interim": False}],
                    },
                ),
                _provider_event_bytes(459, {"question_id": "q-1"}),
                ("await_first_flush", None),
                _provider_event_bytes(
                    550,
                    {
                        "question_id": "q-1",
                        "reply_id": "r-1",
                        "content": "我先追问一期范围和例外规则。",
                    },
                ),
                _provider_event_bytes(559, {"question_id": "q-1", "reply_id": "r-1"}),
                ("release_first_flush", None),
                ("yield_control", None),
                _provider_event_bytes(152, {}),
            ]

        async def send(self, _message) -> None:
            return None

        async def close(self) -> None:
            self.disconnect_event.set()

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self.messages:
                self.disconnect_event.set()
                raise StopAsyncIteration

            next_item = self.messages.pop(0)
            if next_item == ("await_first_flush", None):
                await asyncio.to_thread(first_flush_started.wait, 1)
                await asyncio.sleep(0.01)
                return await self.__anext__()
            if next_item == ("release_first_flush", None):
                release_first_flush.set()
                return await self.__anext__()
            if next_item == ("yield_control", None):
                await asyncio.sleep(0.05)
                return await self.__anext__()

            if not self.messages:
                self.disconnect_event.set()
            return next_item

    class FakeWebSocket:
        def __init__(self, disconnect_event: asyncio.Event) -> None:
            self.disconnect_event = disconnect_event
            self.accepted = False
            self.closed = False
            self.json_messages: list[dict] = []

        async def accept(self) -> None:
            self.accepted = True

        async def send_json(self, payload: dict) -> None:
            self.json_messages.append(payload)

        async def send_bytes(self, _payload: bytes) -> None:
            return None

        async def receive(self) -> dict:
            await self.disconnect_event.wait()
            return {"type": "websocket.disconnect"}

        async def close(self, code: int | None = None) -> None:
            self.closed = True

    async def fake_connect(_headers):
        return FakeUpstream()

    async def exercise_bridge() -> None:
        services.mobile_voice.sync_round = observed_sync_round
        services.realtime_voice_bridge._connect = fake_connect
        upstream = await fake_connect({})
        websocket = FakeWebSocket(upstream.disconnect_event)

        async def patched_connect(_headers):
            return upstream

        services.realtime_voice_bridge._connect = patched_connect
        await services.realtime_voice_bridge.serve(websocket, project.id)

    asyncio.run(exercise_bridge())

    non_final_calls_with_assistant = [
        texts
        for finished, texts in sync_calls
        if not finished and any("我先追问一期范围和例外规则。" in text for text in texts)
    ]
    assert non_final_calls_with_assistant


def test_realtime_transcript_interrupts_partial_assistant_before_follow_up() -> None:
    transcript = RealtimeTranscriptState()

    transcript.update_assistant(
        text="第一段助手回复",
        question_id="q-1",
        reply_id=None,
        is_final=False,
    )

    assert transcript.interrupt_assistant() is True

    transcript.update_user(
        text="我打断一下，补充一个边界条件",
        question_id="q-2",
        is_final=True,
    )
    transcript.update_assistant(
        text="收到，我继续围绕这个边界条件追问。",
        question_id="q-2",
        reply_id=None,
        is_final=False,
    )

    assistant_entries = [entry for entry in transcript.entries if entry.role == "assistant"]
    assert len(assistant_entries) == 2
    assert assistant_entries[0].text == "第一段助手回复"
    assert assistant_entries[0].is_final is True
    assert assistant_entries[1].text == "收到，我继续围绕这个边界条件追问。"
    assert assistant_entries[1].is_final is False


def test_realtime_transcript_splits_assistant_turns_by_question_id_when_reply_id_missing() -> None:
    transcript = RealtimeTranscriptState()

    transcript.update_assistant(
        text="先确认一期范围。",
        question_id="q-1",
        reply_id=None,
        is_final=False,
    )
    transcript.update_assistant(
        text="再确认异常处理。",
        question_id="q-2",
        reply_id=None,
        is_final=False,
    )

    assistant_entries = [entry for entry in transcript.entries if entry.role == "assistant"]
    assert len(assistant_entries) == 2
    assert assistant_entries[0].text == "先确认一期范围。"
    assert assistant_entries[0].question_id == "q-1"
    assert assistant_entries[1].text == "再确认异常处理。"
    assert assistant_entries[1].question_id == "q-2"


def _provider_event_bytes(event_id: int, payload: dict) -> bytes:
    session_id = b"session-test"
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = bytes(
        [
            0x11,
            (MESSAGE_TYPE_FULL_CLIENT_REQUEST << 4) | FLAG_EVENT,
            SERIALIZATION_JSON << 4,
            0,
        ]
    )
    return b"".join(
        [
            header,
            event_id.to_bytes(4, "big"),
            len(session_id).to_bytes(4, "big"),
            session_id,
            len(payload_bytes).to_bytes(4, "big"),
            payload_bytes,
        ]
    )
