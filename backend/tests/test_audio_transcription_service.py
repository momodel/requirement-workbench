import json
from pathlib import Path

import pytest

from app.config import AppSettings
from app.models import ProviderIssue
from app.services.audio_transcription_service import (
    ALIYUN_FILETRANS,
    AudioTranscriptionService,
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
        aliyun_ak_id="aliyun-ak",
        aliyun_ak_secret="aliyun-sk",
        aliyun_app_key="aliyun-app-key",
        aliyun_filetrans_region="cn-shanghai",
        audio_transcription_timeout_seconds=30,
        audio_transcription_poll_interval_seconds=0.01,
    )


def test_get_readiness_reports_missing_aliyun_configuration(tmp_path: Path) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    service.settings.aliyun_app_key = None

    readiness = service.get_readiness()

    assert readiness.provider == ALIYUN_FILETRANS
    assert readiness.status == "not_configured"
    assert readiness.summary == "阿里云音频转写未就绪。"
    assert readiness.detail == "缺少阿里云 AccessKeyId、AccessKeySecret 或 AppKey 配置。"
    assert readiness.action_label == "配置阿里云音频转写"


def test_get_readiness_reports_ready_region_when_configured(tmp_path: Path) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))

    readiness = service.get_readiness()

    assert readiness.provider == ALIYUN_FILETRANS
    assert readiness.status == "ready"
    assert readiness.summary == "阿里云音频转写已就绪。"
    assert readiness.detail == "region=cn-shanghai"
    assert readiness.action_label is None


def test_format_markdown_preserves_time_ranges() -> None:
    markdown = AudioTranscriptionService.format_markdown(
        [
            {"BeginTime": 0, "EndTime": 5000, "Text": "逐笔对账需要人工确认"},
            {"BeginTime": 5000, "EndTime": 12000, "Text": "退款口径需要独立确认"},
        ]
    )

    assert markdown.startswith("# 音频转写")
    assert "00:00-00:05 逐笔对账需要人工确认" in markdown
    assert "00:05-00:12 退款口径需要独立确认" in markdown


def test_format_markdown_raises_when_no_usable_text() -> None:
    with pytest.raises(ProviderIssue) as exc_info:
        AudioTranscriptionService.format_markdown(
            [
                {"BeginTime": 0, "EndTime": 5000, "Text": "   "},
                {"BeginTime": 5000, "EndTime": 12000, "Text": ""},
            ]
        )

    assert exc_info.value.provider == ALIYUN_FILETRANS
    assert exc_info.value.message == "转写结果为空。"


def test_request_submit_task_uses_documented_body_parameter_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    captured: dict[str, object] = {}

    class FakeCommonRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.body_params: list[tuple[str, str]] = []
            self.query_params: list[tuple[str, str]] = []
            self.content: bytes | None = None
            captured["request"] = self

        def set_accept_format(self, value: str) -> None:
            self.accept_format = value

        def set_domain(self, value: str) -> None:
            self.domain = value

        def set_method(self, value: str) -> None:
            self.method = value

        def set_protocol_type(self, value: str) -> None:
            self.protocol_type = value

        def set_version(self, value: str) -> None:
            self.version = value

        def set_product(self, value: str) -> None:
            self.product = value

        def set_action_name(self, value: str) -> None:
            self.action_name = value

        def add_header(self, key: str, value: str) -> None:
            self.headers[key] = value

        def add_body_params(self, key: str, value: str) -> None:
            self.body_params.append((key, value))

        def add_query_param(self, key: str, value: str) -> None:
            self.query_params.append((key, value))

        def set_content(self, value: bytes) -> None:
            self.content = value

    class FakeAcsClient:
        def __init__(self, ak_id: str, ak_secret: str, region: str) -> None:
            captured["ak_id"] = ak_id
            captured["ak_secret"] = ak_secret
            captured["region"] = region

        def do_action_with_exception(self, request: FakeCommonRequest) -> bytes:
            captured["sent_request"] = request
            return json.dumps({"TaskId": "task-1"}).encode("utf-8")

    monkeypatch.setattr(
        "app.services.audio_transcription_service.CommonRequest",
        FakeCommonRequest,
    )
    monkeypatch.setattr(
        "app.services.audio_transcription_service.AcsClient",
        FakeAcsClient,
    )

    response = service._request(
        action="SubmitTask",
        payload={
            "appkey": "aliyun-app-key",
            "file_link": "https://audio.example.com/call.mp3",
            "version": "4.0",
            "enable_words": False,
        },
    )

    request = captured["request"]
    assert response == {"TaskId": "task-1"}
    assert captured["ak_id"] == "aliyun-ak"
    assert captured["ak_secret"] == "aliyun-sk"
    assert captured["region"] == "cn-shanghai"
    assert request.accept_format == "JSON"
    assert request.domain == "filetrans.cn-shanghai.aliyuncs.com"
    assert request.method == "POST"
    assert request.protocol_type == "HTTPS"
    assert request.version == "2018-08-17"
    assert request.product == "nls-filetrans"
    assert request.action_name == "SubmitTask"
    assert request.body_params == [
        (
            "Task",
            json.dumps(
                {
                    "appkey": "aliyun-app-key",
                    "file_link": "https://audio.example.com/call.mp3",
                    "version": "4.0",
                    "enable_words": False,
                },
                ensure_ascii=False,
            ),
        )
    ]
    assert request.query_params == []
    assert request.content is None
    assert request.headers == {}


def test_request_get_task_result_uses_documented_query_parameter_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    captured: dict[str, object] = {}

    class FakeCommonRequest:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}
            self.body_params: list[tuple[str, str]] = []
            self.query_params: list[tuple[str, str]] = []
            self.content: bytes | None = None
            captured["request"] = self

        def set_accept_format(self, value: str) -> None:
            self.accept_format = value

        def set_domain(self, value: str) -> None:
            self.domain = value

        def set_method(self, value: str) -> None:
            self.method = value

        def set_protocol_type(self, value: str) -> None:
            self.protocol_type = value

        def set_version(self, value: str) -> None:
            self.version = value

        def set_product(self, value: str) -> None:
            self.product = value

        def set_action_name(self, value: str) -> None:
            self.action_name = value

        def add_header(self, key: str, value: str) -> None:
            self.headers[key] = value

        def add_body_params(self, key: str, value: str) -> None:
            self.body_params.append((key, value))

        def add_query_param(self, key: str, value: str) -> None:
            self.query_params.append((key, value))

        def set_content(self, value: bytes) -> None:
            self.content = value

    class FakeAcsClient:
        def __init__(self, ak_id: str, ak_secret: str, region: str) -> None:
            captured["ak_id"] = ak_id
            captured["ak_secret"] = ak_secret
            captured["region"] = region

        def do_action_with_exception(self, request: FakeCommonRequest) -> bytes:
            captured["sent_request"] = request
            return json.dumps({"StatusText": "SUCCESS", "Result": {"Sentences": []}}).encode(
                "utf-8"
            )

    monkeypatch.setattr(
        "app.services.audio_transcription_service.CommonRequest",
        FakeCommonRequest,
    )
    monkeypatch.setattr(
        "app.services.audio_transcription_service.AcsClient",
        FakeAcsClient,
    )

    response = service._request(
        action="GetTaskResult",
        payload={"TaskId": "task-123"},
    )

    request = captured["request"]
    assert response == {"StatusText": "SUCCESS", "Result": {"Sentences": []}}
    assert captured["ak_id"] == "aliyun-ak"
    assert captured["ak_secret"] == "aliyun-sk"
    assert captured["region"] == "cn-shanghai"
    assert request.accept_format == "JSON"
    assert request.domain == "filetrans.cn-shanghai.aliyuncs.com"
    assert request.method == "GET"
    assert request.protocol_type == "HTTPS"
    assert request.version == "2018-08-17"
    assert request.product == "nls-filetrans"
    assert request.action_name == "GetTaskResult"
    assert request.query_params == [("TaskId", "task-123")]
    assert request.body_params == []
    assert request.content is None
    assert request.headers == {}


def test_submit_task_sends_required_payload_and_returns_task_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    captured: dict[str, object] = {}

    def fake_request(*, action: str, payload: dict[str, object]) -> dict[str, object]:
        captured["action"] = action
        captured["payload"] = payload
        return {"TaskId": "task-123"}

    monkeypatch.setattr(service, "_request", fake_request)

    task_id = service._submit_task(
        file_url="https://audio.example.com/audio/project-1/src-1/call.mp3",
        source_name="call.mp3",
    )

    assert task_id == "task-123"
    assert captured["action"] == "SubmitTask"
    assert captured["payload"] == {
        "appkey": "aliyun-app-key",
        "file_link": "https://audio.example.com/audio/project-1/src-1/call.mp3",
        "version": "4.0",
        "enable_words": False,
        "enable_timestamp_alignment": True,
        "source_name": "call.mp3",
    }


def test_submit_task_raises_when_task_id_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(service, "_request", lambda **_: {})

    with pytest.raises(ProviderIssue) as exc_info:
        service._submit_task(
            file_url="https://audio.example.com/audio/project-1/src-1/call.mp3",
            source_name="call.mp3",
        )

    assert exc_info.value.provider == ALIYUN_FILETRANS
    assert exc_info.value.message == "阿里云未返回 TaskId。"


def test_wait_for_result_polls_until_success_and_parses_string_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    responses = iter(
        [
            {"StatusText": "QUEUEING"},
            {"StatusText": "RUNNING"},
            {
                "StatusText": "SUCCESS",
                "Result": json.dumps(
                    {
                        "Sentences": [
                            {
                                "BeginTime": 0,
                                "EndTime": 5000,
                                "Text": "逐笔对账需要人工确认",
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )
    sleeps: list[float] = []

    monkeypatch.setattr(service, "_request", lambda **_: next(responses))
    monkeypatch.setattr(
        "app.services.audio_transcription_service.time.sleep",
        lambda seconds: sleeps.append(seconds),
    )

    result = service._wait_for_result("task-123")

    assert result == [{"BeginTime": 0, "EndTime": 5000, "Text": "逐笔对账需要人工确认"}]
    assert sleeps == [0.01, 0.01]


def test_wait_for_result_raises_on_non_success_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(
        service,
        "_request",
        lambda **_: {"StatusText": "FAILED", "StatusMessage": "provider failed"},
    )

    with pytest.raises(ProviderIssue) as exc_info:
        service._wait_for_result("task-123")

    assert exc_info.value.provider == ALIYUN_FILETRANS
    assert exc_info.value.message == "provider failed"


def test_wait_for_result_raises_on_malformed_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(
        service,
        "_request",
        lambda **_: {"StatusText": "SUCCESS", "Result": {"Sentences": "bad"}},
    )

    with pytest.raises(ProviderIssue) as exc_info:
        service._wait_for_result("task-123")

    assert exc_info.value.provider == ALIYUN_FILETRANS
    assert exc_info.value.message == "阿里云转写结果格式异常。"


@pytest.mark.parametrize(
    "status_text",
    ["SUCCESS_WITH_NO_VALID_FRAGMENT", "ASR_RESPONSE_HAVE_NO_WORDS"],
)
def test_wait_for_result_treats_documented_empty_status_as_empty_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    status_text: str,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(
        service,
        "_request",
        lambda **_: {"StatusText": status_text},
    )

    result = service._wait_for_result("task-123")

    assert result == []


def test_wait_for_result_raises_on_malformed_sentence_item(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(
        service,
        "_request",
        lambda **_: {"StatusText": "SUCCESS", "Result": {"Sentences": ["bad"]}},
    )

    with pytest.raises(ProviderIssue) as exc_info:
        service._wait_for_result("task-123")

    assert exc_info.value.provider == ALIYUN_FILETRANS
    assert exc_info.value.message == "阿里云转写结果格式异常。"


def test_wait_for_result_raises_on_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    service.settings.audio_transcription_timeout_seconds = 300
    moments = iter([0.0, 0.0, 301.0])

    monkeypatch.setattr(service, "_request", lambda **_: {"StatusText": "RUNNING"})
    monkeypatch.setattr(
        "app.services.audio_transcription_service.time.monotonic",
        lambda: next(moments),
    )
    monkeypatch.setattr(
        "app.services.audio_transcription_service.time.sleep",
        lambda _seconds: None,
    )

    with pytest.raises(ProviderIssue) as exc_info:
        service._wait_for_result("task-123")

    assert exc_info.value.provider == ALIYUN_FILETRANS
    assert exc_info.value.message == "阿里云转写超时。"


def test_transcribe_from_url_returns_provider_job_id_and_markdown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(service, "_submit_task", lambda file_url, source_name: "task-1")
    monkeypatch.setattr(
        service,
        "_wait_for_result",
        lambda task_id: [{"BeginTime": 0, "EndTime": 5000, "Text": "逐笔对账需要人工确认"}],
    )

    result = service.transcribe_from_url(
        file_url="https://audio.example.com/audio/project-1/src-1/call.mp3",
        source_name="call.mp3",
    )

    assert result.provider_job_id == "task-1"
    assert "00:00-00:05 逐笔对账需要人工确认" in result.markdown


def test_transcribe_from_url_raises_when_result_is_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AudioTranscriptionService(make_settings(tmp_path))
    monkeypatch.setattr(service, "_submit_task", lambda file_url, source_name: "task-1")
    monkeypatch.setattr(service, "_wait_for_result", lambda task_id: [])

    with pytest.raises(ProviderIssue) as exc_info:
        service.transcribe_from_url(
            file_url="https://audio.example.com/audio/project-1/src-1/call.mp3",
            source_name="call.mp3",
        )

    assert exc_info.value.provider == ALIYUN_FILETRANS
    assert exc_info.value.message == "转写结果为空。"
