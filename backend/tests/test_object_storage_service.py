from pathlib import Path

import pytest

from app.config import AppSettings
from app.models import ProviderIssue
from app.services.object_storage_service import ObjectStorageService


def make_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        sqlite_dir=tmp_path / "data" / "sqlite",
        sqlite_path=tmp_path / "data" / "sqlite" / "test.db",
        projects_dir=tmp_path / "data" / "projects",
        qiniu_access_key="qiniu-ak",
        qiniu_secret_key="qiniu-sk",
        qiniu_bucket="audio-bucket",
        qiniu_domain="https://audio.example.com/",
    )


def test_get_readiness_reports_missing_qiniu_configuration(tmp_path: Path) -> None:
    service = ObjectStorageService(make_settings(tmp_path))
    service.settings.qiniu_access_key = None

    readiness = service.get_readiness()

    assert readiness.provider == "QINIU_OSS"
    assert readiness.status == "not_configured"
    assert "七牛" in (readiness.detail or "")


def test_upload_audio_source_returns_stable_object_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    source_path = settings.projects_dir / "project-1" / "sources" / "call.mp3"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"ID3")

    captured: dict[str, object] = {}

    class FakeAuth:
        def __init__(self, access_key: str, secret_key: str) -> None:
            captured["access_key"] = access_key
            captured["secret_key"] = secret_key

        def upload_token(self, bucket: str, key: str, expires: int) -> str:
            captured["bucket"] = bucket
            captured["token_key"] = key
            captured["expires"] = expires
            return "upload-token"

    def fake_put_file_v2(token: str, key: str, file_path: str, version: str = "v2"):
        captured["token"] = token
        captured["key"] = key
        captured["file_path"] = file_path
        captured["version"] = version
        return {"key": key}, type("Info", (), {"status_code": 200})()

    monkeypatch.setattr("app.services.object_storage_service.Auth", FakeAuth)
    monkeypatch.setattr("app.services.object_storage_service.put_file_v2", fake_put_file_v2)

    service = ObjectStorageService(settings)
    result = service.upload_audio_source(
        project_id="project-1",
        source_id="src-1",
        local_path=source_path,
    )

    assert captured["access_key"] == "qiniu-ak"
    assert captured["secret_key"] == "qiniu-sk"
    assert captured["bucket"] == "audio-bucket"
    assert captured["token"] == "upload-token"
    assert captured["file_path"] == str(source_path)
    assert captured["version"] == "v2"
    assert service.build_object_key(
        project_id="project-1",
        source_id="src-1",
        local_path=source_path,
    ) == "audio/project-1/src-1/call.mp3"
    assert result.object_key == "audio/project-1/src-1/call.mp3"
    assert result.url == "https://audio.example.com/audio/project-1/src-1/call.mp3"


def test_upload_audio_source_raises_when_qiniu_is_not_ready(tmp_path: Path) -> None:
    service = ObjectStorageService(make_settings(tmp_path))
    service.settings.qiniu_bucket = None

    source_path = service.settings.projects_dir / "project-1" / "sources" / "call.mp3"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"ID3")

    with pytest.raises(ProviderIssue) as exc_info:
        service.upload_audio_source(
            project_id="project-1",
            source_id="src-1",
            local_path=source_path,
        )

    assert exc_info.value.provider == "QINIU_OSS"
    assert "七牛" in exc_info.value.message


def test_upload_audio_source_raises_when_local_file_is_missing(tmp_path: Path) -> None:
    service = ObjectStorageService(make_settings(tmp_path))

    missing_path = service.settings.projects_dir / "project-1" / "sources" / "missing.mp3"

    with pytest.raises(FileNotFoundError):
        service.upload_audio_source(
            project_id="project-1",
            source_id="src-1",
            local_path=missing_path,
        )


def test_upload_audio_source_raises_when_qiniu_upload_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = make_settings(tmp_path)
    source_path = settings.projects_dir / "project-1" / "sources" / "call.mp3"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"ID3")

    class FakeAuth:
        def __init__(self, access_key: str, secret_key: str) -> None:
            self.access_key = access_key
            self.secret_key = secret_key

        def upload_token(self, bucket: str, key: str, expires: int) -> str:
            return "upload-token"

    def fake_put_file_v2(token: str, key: str, file_path: str, version: str = "v2"):
        return {"key": "wrong-key"}, type("Info", (), {"status_code": 502})()

    monkeypatch.setattr("app.services.object_storage_service.Auth", FakeAuth)
    monkeypatch.setattr("app.services.object_storage_service.put_file_v2", fake_put_file_v2)

    service = ObjectStorageService(settings)

    with pytest.raises(ProviderIssue) as exc_info:
        service.upload_audio_source(
            project_id="project-1",
            source_id="src-1",
            local_path=source_path,
        )

    assert exc_info.value.provider == "QINIU_OSS"
    assert exc_info.value.message == "七牛上传失败。"
