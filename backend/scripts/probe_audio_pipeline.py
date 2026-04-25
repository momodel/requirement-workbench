from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import AppSettings
from app.models import ProviderIssue
from app.services.audio_transcription_service import AudioTranscriptionService


@dataclass(slots=True)
class AliyunRequestTrace:
    action: str
    payload: dict[str, Any]
    response: dict[str, Any] | None = None
    exception: str | None = None


def print_section(title: str) -> None:
    print(f"\n[{title}]")


def read_preview(markdown: str, limit: int = 12) -> str:
    lines = [line.rstrip() for line in markdown.splitlines()]
    return "\n".join(lines[:limit]).strip()


def mask_secret(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def redact_for_logging(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() == "appkey" and isinstance(item, str):
                redacted[key] = mask_secret(item)
            else:
                redacted[key] = redact_for_logging(item)
        return redacted
    if isinstance(value, list):
        return [redact_for_logging(item) for item in value]
    return value


def print_json(value: Any, *, indent: int = 2) -> None:
    dumped = json.dumps(
        redact_for_logging(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    for line in dumped.splitlines():
        print((" " * indent) + line)


def infer_source_name(file_url: str) -> str:
    parsed = urlparse(file_url)
    filename = PurePosixPath(unquote(parsed.path)).name
    return filename or "audio-probe.mp3"


def install_trace(audio_transcription: AudioTranscriptionService) -> list[AliyunRequestTrace]:
    traces: list[AliyunRequestTrace] = []
    original_request = audio_transcription._request

    def traced_request(*, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        trace = AliyunRequestTrace(
            action=action,
            payload=dict(payload),
        )
        traces.append(trace)
        try:
            response = original_request(action=action, payload=payload)
        except Exception as exc:
            trace.exception = f"{exc.__class__.__name__}: {exc}"
            raise
        trace.response = response
        return response

    audio_transcription._request = traced_request
    return traces


def print_traces(traces: list[AliyunRequestTrace]) -> None:
    if not traces:
        print("No Aliyun request trace captured.")
        return

    for index, trace in enumerate(traces, start=1):
        print(f"{index}. action: {trace.action}")
        print("  request_payload:")
        print_json(trace.payload, indent=4)
        if trace.response is not None:
            status_text = trace.response.get("StatusText")
            status_message = trace.response.get("StatusMessage")
            if status_text is not None:
                print(f"  StatusText: {status_text}")
            if status_message is not None:
                print(f"  StatusMessage: {status_message}")
            print("  response_json:")
            print_json(trace.response, indent=4)
        if trace.exception is not None:
            print(f"  exception: {trace.exception}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Aliyun FileTrans live probe using an existing public audio URL.",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Already uploaded public audio file URL.",
    )
    parser.add_argument(
        "--source-name",
        help="Optional source name sent to Aliyun. Defaults to URL basename.",
    )
    args = parser.parse_args()

    settings = AppSettings.from_env()
    audio_transcription = AudioTranscriptionService(settings)
    traces = install_trace(audio_transcription)
    source_name = args.source_name or infer_source_name(args.url)

    print("Aliyun FileTrans live probe")
    print(f"Root dir: {settings.root_dir}")
    print(f"Audio URL: {args.url}")
    print(f"Source name: {source_name}")

    print_section("Readiness")
    aliyun_readiness = audio_transcription.get_readiness()
    print(f"{aliyun_readiness.provider}: {aliyun_readiness.status}")
    print(f"  summary: {aliyun_readiness.summary}")
    if aliyun_readiness.detail:
        print(f"  detail: {aliyun_readiness.detail}")

    if aliyun_readiness.status != "ready":
        print_section("Result")
        print("FAILED: provider readiness is not ready; aborting live probe.")
        return 1

    try:
        print_section("Step 1: Submit + poll Aliyun FileTrans")
        transcription = audio_transcription.transcribe_from_url(
            file_url=args.url,
            source_name=source_name,
        )
        print(f"provider_job_id: {transcription.provider_job_id}")

        print_section("Transcript preview")
        print(read_preview(transcription.markdown))

        print_section("Result")
        print("OK: Aliyun FileTrans succeeded with existing URL.")
        return 0
    except ProviderIssue as exc:
        print_section("Aliyun trace")
        print_traces(traces)
        print_section("Result")
        print(f"FAILED: {exc.provider}")
        print(exc.message)
        return 1
    except Exception as exc:  # pragma: no cover - probe script guardrail
        print_section("Aliyun trace")
        print_traces(traces)
        print_section("Result")
        print(f"FAILED: unexpected error: {exc.__class__.__name__}: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
