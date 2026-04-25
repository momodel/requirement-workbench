import json
from pathlib import Path

from app.config import AppSettings
from app.services.image_generation import ApimartImageGenerationService


def make_settings(tmp_path: Path) -> AppSettings:
    data_dir = tmp_path / "data"
    return AppSettings(
        root_dir=tmp_path,
        data_dir=data_dir,
        sqlite_dir=data_dir / "sqlite",
        sqlite_path=data_dir / "sqlite" / "test.db",
        projects_dir=data_dir / "projects",
        apimart_api_key="key",
        apimart_base_url="https://api.example.test",
        apimart_image_model="gpt-image-2",
    )


def test_image_generation_payload_keeps_tool_parameters_configurable(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    service = ApimartImageGenerationService(settings)
    captured = {}

    def fake_request_json(method, path, payload=None):
        captured["method"] = method
        captured["path"] = path
        captured["payload"] = payload
        return {"data": {"result": {"images": [{"url": ["https://cdn.example.test/a.png"]}]}}}

    def fake_download(url):
        captured["download_url"] = url
        return b"png", "image/png"

    monkeypatch.setattr(service, "_request_json", fake_request_json)
    monkeypatch.setattr(service, "_download_image", fake_download)

    result = service._generate_sync(
        project_id="project-1",
        artifact_id="artifact-1",
        title="视觉稿",
        summary="summary",
        prompt="生成工作台视觉稿",
        size="16:9",
        resolution="2k",
        n=1,
        quality="high",
        style="clean enterprise SaaS",
        reference_image_urls=["https://example.test/ref.png"],
        extra_parameters={"seed": 7},
        output_dir=tmp_path / "image-output",
    )

    assert captured["path"] == "/v1/images/generations"
    assert captured["payload"] == {
        "model": "gpt-image-2",
        "prompt": "生成工作台视觉稿",
        "n": 1,
        "size": "16:9",
        "resolution": "2k",
        "quality": "high",
        "style": "clean enterprise SaaS",
        "image_urls": ["https://example.test/ref.png"],
        "seed": 7,
    }
    assert result.image_path.exists()
    assert result.image_path.read_bytes() == b"png"


def test_image_generation_extracts_nested_apimart_url():
    payload = {"data": {"result": {"images": [{"url": ["https://cdn.example.test/a.png"]}]}}}
    assert ApimartImageGenerationService._extract_image_url(payload) == "https://cdn.example.test/a.png"
