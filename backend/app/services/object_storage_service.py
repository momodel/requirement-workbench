from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from qiniu import Auth

try:
    from qiniu import put_file_v2
except ImportError:  # pragma: no cover - compatibility for qiniu 7.13.0 top-level exports
    from qiniu import put_file as put_file_v2

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ProviderIssue, ProviderReadiness


QINIU_OSS = "QINIU_OSS"


@dataclass(frozen=True, slots=True)
class UploadedObject:
    object_key: str
    url: str


class ObjectStorageService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings

    def get_readiness(self) -> ProviderReadiness:
        required_values = (
            self.settings.qiniu_access_key,
            self.settings.qiniu_secret_key,
            self.settings.qiniu_bucket,
            self.settings.qiniu_domain,
        )
        if any(value in {None, ""} for value in required_values):
            return ProviderReadiness(
                provider=QINIU_OSS,
                status="not_configured",
                summary="七牛对象存储未就绪。",
                detail="缺少七牛 AccessKey、SecretKey、Bucket 或 Domain 配置。",
                action_label="配置七牛对象存储",
            )

        return ProviderReadiness(
            provider=QINIU_OSS,
            status="ready",
            summary="七牛对象存储已就绪。",
            detail=f"bucket={self.settings.qiniu_bucket}",
        )

    def build_object_key(self, *, project_id: str, source_id: str, local_path: Path) -> str:
        prefix = (self.settings.qiniu_key_prefix or "audio").strip("/") or "audio"
        return f"{prefix}/{project_id}/{source_id}/{local_path.name}"

    def upload_audio_source(
        self,
        *,
        project_id: str,
        source_id: str,
        local_path: Path,
    ) -> UploadedObject:
        readiness = self.get_readiness()
        if readiness.status != "ready":
            raise ProviderIssue(
                provider=QINIU_OSS,
                message=readiness.detail or readiness.summary,
            )

        if not local_path.exists():
            raise FileNotFoundError(str(local_path))

        object_key = self.build_object_key(
            project_id=project_id,
            source_id=source_id,
            local_path=local_path,
        )
        token = Auth(
            self.settings.qiniu_access_key,
            self.settings.qiniu_secret_key,
        ).upload_token(self.settings.qiniu_bucket, object_key, 3600)
        result, info = put_file_v2(
            token,
            object_key,
            str(local_path),
            version="v2",
        )
        if info.status_code != 200 or not result or result.get("key") != object_key:
            raise ProviderIssue(provider=QINIU_OSS, message="七牛上传失败。")

        domain = self.settings.qiniu_domain.rstrip("/")
        return UploadedObject(
            object_key=object_key,
            url=f"{domain}/{object_key}",
        )
