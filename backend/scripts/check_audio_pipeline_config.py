from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import AppSettings
from app.services.audio_transcription_service import AudioTranscriptionService
from app.services.object_storage_service import ObjectStorageService


def mask_secret(value: str | None) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 6:
        return "*" * len(value)
    return f"{value[:3]}***{value[-3:]}"


def present(value: str | None) -> str:
    return "set" if value else "missing"


def print_section(title: str) -> None:
    print(f"\n[{title}]")


def main() -> int:
    settings = AppSettings.from_env()
    object_storage = ObjectStorageService(settings)
    audio_transcription = AudioTranscriptionService(settings)

    print("Audio pipeline config probe")
    print(f"Root dir: {settings.root_dir}")
    print(f"Backend env: {settings.root_dir / 'backend' / '.env.local'}")

    print_section("Qiniu config")
    print(
        f"REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY: {present(settings.qiniu_access_key)} ({mask_secret(settings.qiniu_access_key)})"
    )
    print(
        f"REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY: {present(settings.qiniu_secret_key)} ({mask_secret(settings.qiniu_secret_key)})"
    )
    print(f"REQUIREMENT_WORKBENCH_QINIU_BUCKET: {settings.qiniu_bucket or '<missing>'}")
    print(f"REQUIREMENT_WORKBENCH_QINIU_DOMAIN: {settings.qiniu_domain or '<missing>'}")
    print(f"REQUIREMENT_WORKBENCH_QINIU_KEY_PREFIX: {settings.qiniu_key_prefix}")

    print_section("Aliyun config")
    print(
        f"REQUIREMENT_WORKBENCH_ALIYUN_AK_ID: {present(settings.aliyun_ak_id)} ({mask_secret(settings.aliyun_ak_id)})"
    )
    print(
        f"REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET: {present(settings.aliyun_ak_secret)} ({mask_secret(settings.aliyun_ak_secret)})"
    )
    print(
        f"REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY: {present(settings.aliyun_app_key)} ({mask_secret(settings.aliyun_app_key)})"
    )
    print(f"REQUIREMENT_WORKBENCH_ALIYUN_FILETRANS_REGION: {settings.aliyun_filetrans_region}")
    print(f"REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_BACKEND: {settings.audio_transcription_backend}")
    print(
        f"REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS: {settings.audio_transcription_timeout_seconds}"
    )
    print(
        f"REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_POLL_INTERVAL_SECONDS: {settings.audio_transcription_poll_interval_seconds}"
    )

    qiniu_readiness = object_storage.get_readiness()
    aliyun_readiness = audio_transcription.get_readiness()

    print_section("Readiness")
    for readiness in (qiniu_readiness, aliyun_readiness):
        print(f"{readiness.provider}: {readiness.status}")
        print(f"  summary: {readiness.summary}")
        if readiness.detail:
            print(f"  detail: {readiness.detail}")
        if readiness.action_label:
            print(f"  action: {readiness.action_label}")

    all_ready = all(readiness.status == "ready" for readiness in (qiniu_readiness, aliyun_readiness))
    print_section("Result")
    if all_ready:
        print("OK: audio provider config is ready for the next probe step.")
        print("Next recommended step: add a small Qiniu upload probe, then an Aliyun transcription probe.")
        return 0

    print("FAILED: audio provider config is not ready.")
    print("Fix the missing/invalid fields above before running the full project flow.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
