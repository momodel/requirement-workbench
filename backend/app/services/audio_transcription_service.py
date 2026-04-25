from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from aliyunsdkcore.client import AcsClient
from aliyunsdkcore.request import CommonRequest

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue, ProviderReadiness


ALIYUN_FILETRANS = "ALIYUN_FILETRANS"
ALIYUN_FILETRANS_PRODUCT = "nls-filetrans"
ALIYUN_FILETRANS_VERSION = "2018-08-17"


@dataclass(frozen=True, slots=True)
class AudioTranscriptionResult:
    provider_job_id: str
    markdown: str


class AudioTranscriptionService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def get_readiness(self) -> ProviderReadiness:
        required_values = (
            self.settings.aliyun_ak_id,
            self.settings.aliyun_ak_secret,
            self.settings.aliyun_app_key,
        )
        if any(value in {None, ""} for value in required_values):
            return ProviderReadiness(
                provider=ALIYUN_FILETRANS,
                status="not_configured",
                summary="阿里云音频转写未就绪。",
                detail="缺少阿里云 AccessKeyId、AccessKeySecret 或 AppKey 配置。",
                action_label="配置阿里云音频转写",
            )

        return ProviderReadiness(
            provider=ALIYUN_FILETRANS,
            status="ready",
            summary="阿里云音频转写已就绪。",
            detail=f"region={self.settings.aliyun_filetrans_region}",
        )

    @staticmethod
    def _format_timestamp(milliseconds: int | float | str | None) -> str:
        try:
            total_seconds = max(int(float(milliseconds or 0)), 0) // 1000
        except (TypeError, ValueError):
            total_seconds = 0
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"

    @classmethod
    def format_markdown(cls, utterances: list[dict[str, Any]]) -> str:
        lines = ["# 音频转写", ""]
        for utterance in utterances:
            text = str(utterance.get("Text", "")).strip()
            if not text:
                continue

            start = cls._format_timestamp(utterance.get("BeginTime"))
            end = cls._format_timestamp(
                utterance.get("EndTime", utterance.get("BeginTime"))
            )
            lines.append(f"{start}-{end} {text}")

        markdown = "\n".join(lines).strip()
        if markdown == "# 音频转写":
            raise ProviderIssue(provider=ALIYUN_FILETRANS, message="转写结果为空。")
        return markdown

    def _client(self) -> AcsClient:
        return AcsClient(
            self.settings.aliyun_ak_id,
            self.settings.aliyun_ak_secret,
            self.settings.aliyun_filetrans_region,
        )

    def _request(self, *, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = CommonRequest()
        request.set_accept_format("JSON")
        request.set_domain(
            f"filetrans.{self.settings.aliyun_filetrans_region}.aliyuncs.com"
        )
        request.set_method("POST")
        request.set_protocol_type("HTTPS")
        request.set_version(ALIYUN_FILETRANS_VERSION)
        request.set_product(ALIYUN_FILETRANS_PRODUCT)
        request.set_action_name(action)
        request.add_header("Content-Type", "application/json")
        request.set_content(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        try:
            raw_response = self._client().do_action_with_exception(request)
        except ProviderIssue:
            raise
        except Exception as exc:  # pragma: no cover - SDK/network failures are environment-specific.
            raise ProviderIssue(
                provider=ALIYUN_FILETRANS,
                message=f"阿里云转写请求失败：{exc}",
            ) from exc

        try:
            parsed = json.loads(raw_response)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderIssue(
                provider=ALIYUN_FILETRANS,
                message="阿里云转写接口返回格式异常。",
            ) from exc

        if not isinstance(parsed, dict):
            raise ProviderIssue(
                provider=ALIYUN_FILETRANS,
                message="阿里云转写接口返回格式异常。",
            )
        return parsed

    def _submit_task(self, file_url: str, source_name: str) -> str:
        response = self._request(
            action="SubmitTask",
            payload={
                "appkey": self.settings.aliyun_app_key,
                "file_link": file_url,
                "version": "4.0",
                "enable_words": False,
                "enable_timestamp_alignment": True,
                "source_name": source_name,
            },
        )
        task_id = response.get("TaskId")
        if not task_id:
            raise ProviderIssue(provider=ALIYUN_FILETRANS, message="阿里云未返回 TaskId。")
        return str(task_id)

    def _wait_for_result(self, task_id: str) -> list[dict[str, Any]]:
        deadline = time.monotonic() + self.settings.audio_transcription_timeout_seconds
        while time.monotonic() < deadline:
            payload = self._request(action="GetTaskResult", payload={"TaskId": task_id})
            status_text = str(payload.get("StatusText", "")).upper()

            if status_text in {"QUEUEING", "RUNNING"}:
                time.sleep(self.settings.audio_transcription_poll_interval_seconds)
                continue

            if status_text != "SUCCESS":
                raise ProviderIssue(
                    provider=ALIYUN_FILETRANS,
                    message=str(payload.get("StatusMessage") or "阿里云转写失败。"),
                )

            result_payload = payload.get("Result")
            if isinstance(result_payload, str):
                try:
                    result_payload = json.loads(result_payload)
                except json.JSONDecodeError as exc:
                    raise ProviderIssue(
                        provider=ALIYUN_FILETRANS,
                        message="阿里云转写结果格式异常。",
                    ) from exc

            if not isinstance(result_payload, dict):
                raise ProviderIssue(
                    provider=ALIYUN_FILETRANS,
                    message="阿里云转写结果格式异常。",
                )

            sentences = result_payload.get("Sentences")
            if not isinstance(sentences, list):
                raise ProviderIssue(
                    provider=ALIYUN_FILETRANS,
                    message="阿里云转写结果格式异常。",
                )

            return sentences

        raise ProviderIssue(provider=ALIYUN_FILETRANS, message="阿里云转写超时。")

    def transcribe_from_url(
        self,
        *,
        file_url: str,
        source_name: str,
    ) -> AudioTranscriptionResult:
        readiness = self.get_readiness()
        if readiness.status != "ready":
            raise ProviderIssue(
                provider=ALIYUN_FILETRANS,
                message=readiness.detail or readiness.summary,
            )

        task_id = self._submit_task(file_url=file_url, source_name=source_name)
        utterances = self._wait_for_result(task_id)
        markdown = self.format_markdown(utterances)
        return AudioTranscriptionResult(
            provider_job_id=task_id,
            markdown=markdown,
        )
