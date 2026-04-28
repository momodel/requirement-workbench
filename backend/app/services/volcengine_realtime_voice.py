from __future__ import annotations

import asyncio
import json
import struct
import uuid
from dataclasses import dataclass, field
from typing import Any

import websockets
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from ..config import AppSettings
from ..models import ProviderIssue, VoiceTranscriptEntry
from .mobile_voice import MobileVoiceService
from .project_catalog import now_iso


PROTOCOL_VERSION = 0x1
HEADER_SIZE = 0x1
SERIALIZATION_RAW = 0x0
SERIALIZATION_JSON = 0x1
COMPRESSION_NONE = 0x0

MESSAGE_TYPE_FULL_CLIENT_REQUEST = 0x1
MESSAGE_TYPE_AUDIO_ONLY_REQUEST = 0x2
MESSAGE_TYPE_AUDIO_ONLY_RESPONSE = 0xB
MESSAGE_TYPE_ERROR = 0xF

FLAG_EVENT = 0x4

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_END_ASR = 400
EVENT_TASK_REQUEST = 200
FLUSH_DEBOUNCE_SECONDS = 0.1

EVENT_NAMES = {
    50: "connection_started",
    51: "connection_failed",
    52: "connection_finished",
    150: "session_started",
    151: "session_failed",
    152: "session_finished",
    251: "config_updated",
    350: "tts_sentence_start",
    351: "tts_sentence_end",
    359: "tts_ended",
    450: "asr_info",
    451: "asr_response",
    459: "asr_ended",
    550: "chat_response",
    553: "chat_text_query_confirmed",
    559: "chat_ended",
    599: "dialog_common_error",
}


def _frame_header(message_type: int, flags: int, serialization: int) -> bytes:
    return bytes(
        [
            (PROTOCOL_VERSION << 4) | HEADER_SIZE,
            (message_type << 4) | flags,
            (serialization << 4) | COMPRESSION_NONE,
            0,
        ]
    )


def _pack_text_event(
    *,
    event_id: int,
    payload: dict[str, Any],
    session_id: str | None = None,
) -> bytes:
    optional = bytearray()
    optional.extend(struct.pack(">I", event_id))
    if session_id is not None:
        session_bytes = session_id.encode("utf-8")
        optional.extend(struct.pack(">I", len(session_bytes)))
        optional.extend(session_bytes)
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return b"".join(
        [
            _frame_header(MESSAGE_TYPE_FULL_CLIENT_REQUEST, FLAG_EVENT, SERIALIZATION_JSON),
            bytes(optional),
            struct.pack(">I", len(payload_bytes)),
            payload_bytes,
        ]
    )


def _pack_audio_chunk(*, payload: bytes, session_id: str) -> bytes:
    session_bytes = session_id.encode("utf-8")
    optional = bytearray()
    optional.extend(struct.pack(">I", EVENT_TASK_REQUEST))
    optional.extend(struct.pack(">I", len(session_bytes)))
    optional.extend(session_bytes)
    return b"".join(
        [
            _frame_header(MESSAGE_TYPE_AUDIO_ONLY_REQUEST, FLAG_EVENT, SERIALIZATION_RAW),
            bytes(optional),
            struct.pack(">I", len(payload)),
            payload,
        ]
    )


def _safe_decode_json(payload: bytes) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"raw_text": payload.decode("utf-8", errors="ignore")}
    return decoded if isinstance(decoded, dict) else {"value": decoded}


def _merge_stream_text(current: str, incoming: str) -> str:
    if not current:
        return incoming
    if incoming.startswith(current):
        return incoming
    if current.startswith(incoming):
        return current

    overlap = min(len(current), len(incoming))
    while overlap > 0:
        if current.endswith(incoming[:overlap]):
            return current + incoming[overlap:]
        overlap -= 1
    return f"{current}{incoming}"


@dataclass(slots=True)
class RealtimeTranscriptState:
    entries: list[VoiceTranscriptEntry] = field(default_factory=list)
    current_user_index: int | None = None
    current_user_question_id: str | None = None
    current_assistant_index: int | None = None
    current_assistant_question_id: str | None = None
    current_assistant_reply_id: str | None = None

    def update_user(self, *, text: str, question_id: str | None, is_final: bool) -> None:
        if self.current_user_index is None or (
            question_id and question_id != self.current_user_question_id
        ):
            self.entries.append(
                VoiceTranscriptEntry(
                    role="user",
                    text=text,
                    is_final=is_final,
                    question_id=question_id,
                )
            )
            self.current_user_index = len(self.entries) - 1
            self.current_user_question_id = question_id
        else:
            entry = self.entries[self.current_user_index]
            entry.text = text
            entry.is_final = is_final
            entry.question_id = question_id or entry.question_id
        if is_final:
            self.current_user_index = None
            self.current_user_question_id = None

    def finalize_user(self) -> None:
        if self.current_user_index is None:
            return
        self.entries[self.current_user_index].is_final = True
        self.current_user_index = None
        self.current_user_question_id = None

    def update_assistant(
        self,
        *,
        text: str,
        question_id: str | None,
        reply_id: str | None,
        is_final: bool,
    ) -> None:
        if self.current_assistant_index is None or (
            reply_id and reply_id != self.current_assistant_reply_id
        ) or (
            reply_id is None
            and question_id is not None
            and question_id != self.current_assistant_question_id
        ):
            self.entries.append(
                VoiceTranscriptEntry(
                    role="assistant",
                    text=text,
                    is_final=is_final,
                    question_id=question_id,
                    reply_id=reply_id,
                )
            )
            self.current_assistant_index = len(self.entries) - 1
            self.current_assistant_question_id = question_id
            self.current_assistant_reply_id = reply_id
        else:
            entry = self.entries[self.current_assistant_index]
            entry.text = _merge_stream_text(entry.text, text)
            entry.is_final = is_final
            entry.question_id = question_id or entry.question_id
            entry.reply_id = reply_id or entry.reply_id
        if is_final:
            self.current_assistant_index = None
            self.current_assistant_question_id = None
            self.current_assistant_reply_id = None

    def finalize_assistant(self) -> None:
        if self.current_assistant_index is None:
            return
        self.entries[self.current_assistant_index].is_final = True
        self.current_assistant_index = None
        self.current_assistant_question_id = None
        self.current_assistant_reply_id = None

    def interrupt_assistant(self) -> bool:
        if self.current_assistant_index is None:
            return False
        self.entries[self.current_assistant_index].is_final = True
        self.current_assistant_index = None
        self.current_assistant_question_id = None
        self.current_assistant_reply_id = None
        return True


class VolcengineRealtimeVoiceBridge:
    def __init__(
        self,
        settings: AppSettings,
        mobile_voice: MobileVoiceService,
    ) -> None:
        self.settings = settings
        self.mobile_voice = mobile_voice

    async def serve(self, websocket: WebSocket, project_id: str) -> None:
        voice_readiness = self.mobile_voice.get_provider_readiness()
        if voice_readiness.status != "ready":
            await websocket.accept()
            await websocket.send_json(
                {
                    "type": "error",
                    "provider": voice_readiness.provider,
                    "message": voice_readiness.detail or voice_readiness.summary,
                }
            )
            await websocket.close(code=4403)
            return

        round_context = await asyncio.to_thread(self.mobile_voice.create_round, project_id)
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "round_started",
                "project_id": project_id,
                "source_id": round_context.source.id,
                "source_name": round_context.source.name,
                "initial_prompt": round_context.initial_prompt,
            }
        )

        connect_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        transcript = RealtimeTranscriptState()
        flush_lock = asyncio.Lock()
        flush_task: asyncio.Task[None] | None = None
        flush_requested = False
        flush_immediate = False

        async def flush_entries(*, force_finished: bool):
            async with flush_lock:
                return await asyncio.to_thread(
                    self.mobile_voice.sync_round,
                    project_id=project_id,
                    source_id=round_context.source.id,
                    entries=list(transcript.entries),
                    finished=force_finished,
                )

        def schedule_flush(*, delay: float = FLUSH_DEBOUNCE_SECONDS) -> None:
            nonlocal flush_immediate, flush_requested, flush_task
            flush_requested = True
            if delay <= 0:
                flush_immediate = True
            if flush_task and not flush_task.done():
                return

            async def runner() -> None:
                nonlocal flush_immediate, flush_requested, flush_task
                try:
                    while flush_requested:
                        should_flush_now = flush_immediate
                        flush_requested = False
                        flush_immediate = False
                        if not should_flush_now and delay > 0:
                            await asyncio.sleep(delay)
                        source = await flush_entries(force_finished=False)
                        await websocket.send_json(
                            {
                                "type": "round_synced",
                                "source": source.model_dump(),
                            }
                        )
                except ProviderIssue as exc:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "provider": exc.provider,
                            "message": exc.message,
                        }
                    )
                except Exception as exc:  # pragma: no cover - defensive
                    await websocket.send_json(
                        {
                            "type": "error",
                            "provider": "VOICE_ROUND_SYNC",
                            "message": str(exc),
                        }
                    )
                finally:
                    flush_task = None
                    if flush_requested:
                        schedule_flush(delay=0 if flush_immediate else FLUSH_DEBOUNCE_SECONDS)

            flush_task = asyncio.create_task(runner())

        headers = {
            "X-Api-App-ID": self.settings.volcengine_voice_app_id or "",
            "X-Api-Access-Key": self.settings.volcengine_voice_access_key or "",
            "X-Api-Resource-Id": self.settings.volcengine_voice_resource_id,
            "X-Api-App-Key": self.settings.volcengine_voice_app_key,
            "X-Api-Connect-Id": connect_id,
        }
        upstream = None

        try:
            upstream = await self._connect(headers)
            await upstream.send(
                _pack_text_event(
                    event_id=EVENT_START_CONNECTION,
                    payload={},
                )
            )
            await upstream.send(
                _pack_text_event(
                    event_id=EVENT_START_SESSION,
                    session_id=session_id,
                    payload=self._start_session_payload(round_context.initial_prompt),
                )
            )

            async def upstream_reader() -> None:
                nonlocal session_id
                async for raw_message in upstream:
                    if not isinstance(raw_message, bytes):
                        continue
                    parsed = self._parse_provider_message(raw_message)
                    if parsed.get("session_id"):
                        session_id = parsed["session_id"]
                    if parsed["kind"] == "audio":
                        await websocket.send_bytes(parsed["payload"])
                        continue

                    event_id = parsed.get("event_id")
                    payload = parsed.get("payload", {})
                    event_name = EVENT_NAMES.get(event_id, f"event_{event_id}")
                    await websocket.send_json(
                        {
                            "type": "provider_event",
                            "event_id": event_id,
                            "event_name": event_name,
                            "payload": payload,
                            "received_at": now_iso(self.settings),
                        }
                    )

                    if event_id == 450:
                        if transcript.interrupt_assistant():
                            schedule_flush(delay=0)
                    elif event_id == 451:
                        results = payload.get("results")
                        if isinstance(results, list) and results:
                            head = results[0] if isinstance(results[0], dict) else {}
                            text = str(head.get("text") or "").strip()
                            if text:
                                transcript.update_user(
                                    text=text,
                                    question_id=payload.get("question_id"),
                                    is_final=not bool(head.get("is_interim")),
                                )
                                schedule_flush()
                    elif event_id == 459:
                        transcript.finalize_user()
                        schedule_flush(delay=0)
                    elif event_id == 550:
                        content = str(payload.get("content") or "").strip()
                        if content:
                            transcript.update_assistant(
                                text=content,
                                question_id=payload.get("question_id"),
                                reply_id=payload.get("reply_id"),
                                is_final=False,
                            )
                            schedule_flush()
                    elif event_id == 559:
                        transcript.finalize_assistant()
                        schedule_flush(delay=0)
                    elif event_id in {151, 599}:
                        raise ProviderIssue(
                            provider=self.mobile_voice.PROVIDER_NAME,
                            message=str(payload.get("message") or payload.get("error") or "实时语音返回错误。"),
                        )
                    elif event_id == 152:
                        return

            async def client_reader() -> None:
                while True:
                    message = await websocket.receive()
                    if message.get("type") == "websocket.disconnect":
                        return
                    if text := message.get("text"):
                        payload = json.loads(text)
                        msg_type = payload.get("type")
                        if msg_type == "end_asr":
                            await upstream.send(
                                _pack_text_event(
                                    event_id=EVENT_END_ASR,
                                    session_id=session_id,
                                    payload={},
                                )
                            )
                            continue
                        if msg_type == "finish_session":
                            await upstream.send(
                                _pack_text_event(
                                    event_id=EVENT_FINISH_SESSION,
                                    session_id=session_id,
                                    payload={},
                                )
                            )
                            return
                        continue
                    if data := message.get("bytes"):
                        await upstream.send(
                            _pack_audio_chunk(
                                payload=data,
                                session_id=session_id,
                            )
                        )

            tasks = {
                asyncio.create_task(upstream_reader()),
                asyncio.create_task(client_reader()),
            }
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                exc = task.exception()
                if exc:
                    raise exc
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        except ProviderIssue as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "provider": exc.provider,
                    "message": exc.message,
                }
            )
        except WebSocketDisconnect:
            pass
        except ConnectionClosed as exc:
            await websocket.send_json(
                {
                    "type": "error",
                    "provider": self.mobile_voice.PROVIDER_NAME,
                    "message": f"实时语音连接已断开：{exc}",
                }
            )
        finally:
            if flush_task and not flush_task.done():
                try:
                    await flush_task
                except Exception:
                    pass
            try:
                await flush_entries(force_finished=True)
            except Exception:
                pass
            try:
                if upstream is not None:
                    await upstream.send(
                        _pack_text_event(
                            event_id=EVENT_FINISH_CONNECTION,
                            payload={},
                        )
                    )
            except Exception:
                pass
            if upstream is not None:
                await upstream.close()
            try:
                await websocket.close()
            except Exception:
                pass

    async def _connect(self, headers: dict[str, str]):
        connect_kwargs = {
            "uri": self.settings.volcengine_voice_ws_url,
            "max_size": None,
            "ping_interval": 20,
            "ping_timeout": 20,
        }
        try:
            try:
                return await websockets.connect(
                    extra_headers=headers,
                    **connect_kwargs,
                )
            except TypeError:
                return await websockets.connect(
                    additional_headers=headers,
                    **connect_kwargs,
                )
        except Exception as exc:
            raise ProviderIssue(
                provider=self.mobile_voice.PROVIDER_NAME,
                message=f"实时语音连接失败：{exc}",
            ) from exc

    def _start_session_payload(self, initial_prompt: str) -> dict[str, Any]:
        dialog_extra: dict[str, Any] = {
            "input_mod": "push_to_talk",
            "enable_conversation_truncate": True,
        }
        if self.settings.volcengine_voice_model:
            dialog_extra["model"] = self.settings.volcengine_voice_model

        return {
            "asr": {
                "audio_info": {
                    "format": "pcm",
                    "sample_rate": 16000,
                    "channel": 1,
                },
                "extra": {},
            },
            "tts": {
                "speaker": self.settings.volcengine_voice_speaker,
                "audio_config": {
                    "channel": 1,
                    "format": "pcm_s16le",
                    "sample_rate": 24000,
                },
                "extra": {},
            },
            "dialog": {
                "bot_name": self.settings.volcengine_voice_bot_name,
                "system_role": initial_prompt,
                "speaking_style": self.settings.volcengine_voice_speaking_style,
                "dialog_id": "",
                "extra": dialog_extra,
            },
        }

    def _parse_provider_message(self, message: bytes) -> dict[str, Any]:
        if len(message) < 8:
            raise ProviderIssue(
                provider=self.mobile_voice.PROVIDER_NAME,
                message="实时语音返回了非法数据帧。",
            )

        byte1 = message[1]
        byte2 = message[2]
        message_type = byte1 >> 4
        flags = byte1 & 0x0F
        serialization = byte2 >> 4
        offset = 4

        if message_type == MESSAGE_TYPE_AUDIO_ONLY_RESPONSE:
            payload_size = struct.unpack(">I", message[offset : offset + 4])[0]
            offset += 4
            return {
                "kind": "audio",
                "payload": message[offset : offset + payload_size],
            }

        error_code = None
        if message_type == MESSAGE_TYPE_ERROR:
            error_code = struct.unpack(">I", message[offset : offset + 4])[0]
            offset += 4

        event_id = None
        session_id = None
        if flags == FLAG_EVENT:
            event_id = struct.unpack(">I", message[offset : offset + 4])[0]
            offset += 4
            if len(message) >= offset + 4:
                session_id_size = struct.unpack(">I", message[offset : offset + 4])[0]
                offset += 4
                session_id = message[offset : offset + session_id_size].decode(
                    "utf-8",
                    errors="ignore",
                )
                offset += session_id_size

        payload_size = struct.unpack(">I", message[offset : offset + 4])[0]
        offset += 4
        payload = message[offset : offset + payload_size]
        decoded = (
            _safe_decode_json(payload)
            if serialization == SERIALIZATION_JSON
            else {"raw": payload.hex()}
        )
        if error_code is not None:
            decoded["status_code"] = error_code

        return {
            "kind": "event",
            "event_id": event_id,
            "session_id": session_id,
            "payload": decoded,
        }
