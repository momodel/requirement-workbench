from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import probe_audio_pipeline as probe
from app.models import ProviderIssue, ProviderReadiness


def make_settings(tmp_path):
    return SimpleNamespace(
        root_dir=tmp_path,
        aliyun_app_key="aliyun-app-key",
    )


class FakeSuccessService:
    last_instance: "FakeSuccessService | None" = None

    def __init__(self, settings) -> None:
        self.settings = settings
        self.calls: list[tuple[str, str]] = []
        FakeSuccessService.last_instance = self

    def get_readiness(self) -> ProviderReadiness:
        return ProviderReadiness(
            provider="ALIYUN_FILETRANS",
            status="ready",
            summary="阿里云音频转写已就绪。",
            detail="region=cn-shanghai",
        )

    def _request(self, *, action, payload):
        raise AssertionError("_request should not be called in this success stub")

    def transcribe_from_url(self, *, file_url: str, source_name: str):
        self.calls.append((file_url, source_name))
        return SimpleNamespace(
            provider_job_id="task-123",
            markdown="# 音频转写\n\n00:00-00:01 逐笔对账",
        )


class FakeFailureService:
    def __init__(self, settings) -> None:
        self.settings = settings

    def get_readiness(self) -> ProviderReadiness:
        return ProviderReadiness(
            provider="ALIYUN_FILETRANS",
            status="ready",
            summary="阿里云音频转写已就绪。",
            detail="region=cn-shanghai",
        )

    def _request(self, *, action, payload):
        if action == "SubmitTask":
            return {"TaskId": "task-123", "RequestId": "submit-req"}
        if action == "GetTaskResult":
            return {
                "StatusText": "FAILED",
                "StatusMessage": "AppKey mismatch",
                "RequestId": "result-req",
            }
        raise AssertionError(f"Unexpected action: {action}")

    def transcribe_from_url(self, *, file_url: str, source_name: str):
        submit_payload = {
            "appkey": self.settings.aliyun_app_key,
            "file_link": file_url,
            "version": "4.0",
            "enable_sample_rate_adaptive": True,
            "enable_words": False,
            "enable_timestamp_alignment": True,
            "source_name": source_name,
        }
        submit_result = self._request(action="SubmitTask", payload=submit_payload)
        result_payload = self._request(
            action="GetTaskResult",
            payload={"TaskId": submit_result["TaskId"]},
        )
        raise ProviderIssue(
            provider="ALIYUN_FILETRANS",
            message=str(result_payload["StatusMessage"]),
        )


def test_probe_uses_existing_url_without_upload(tmp_path, monkeypatch, capsys) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(probe.AppSettings, "from_env", staticmethod(lambda: settings))
    monkeypatch.setattr(probe, "AudioTranscriptionService", FakeSuccessService)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe_audio_pipeline.py",
            "--url",
            "https://files.example.com/audio/test3.mp3",
        ],
    )

    exit_code = probe.main()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Aliyun FileTrans live probe" in output
    assert "Audio URL: https://files.example.com/audio/test3.mp3" in output
    assert "Source name: test3.mp3" in output
    assert "Upload to Qiniu" not in output
    assert FakeSuccessService.last_instance is not None
    assert FakeSuccessService.last_instance.calls == [
        ("https://files.example.com/audio/test3.mp3", "test3.mp3")
    ]


def test_probe_prints_aliyun_failure_trace_details(tmp_path, monkeypatch, capsys) -> None:
    settings = make_settings(tmp_path)
    monkeypatch.setattr(probe.AppSettings, "from_env", staticmethod(lambda: settings))
    monkeypatch.setattr(probe, "AudioTranscriptionService", FakeFailureService)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "probe_audio_pipeline.py",
            "--url",
            "https://files.example.com/audio/test3.mp3",
        ],
    )

    exit_code = probe.main()

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "[Aliyun trace]" in output
    assert "1. action: SubmitTask" in output
    assert "2. action: GetTaskResult" in output
    assert "StatusText: FAILED" in output
    assert "StatusMessage: AppKey mismatch" in output
    assert '"RequestId": "result-req"' in output
    assert "aliyun-app-key" not in output
    assert "ali***key" in output
    assert "FAILED: ALIYUN_FILETRANS" in output
    assert "AppKey mismatch" in output
