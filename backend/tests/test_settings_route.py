from __future__ import annotations

import os

import app.routes.settings as settings_module
from app.config import DEFAULT_SETTINGS
from app.routes.settings import (
    LlmSettingsPayload,
    get_llm_settings,
    update_llm_settings,
)

LONG_SECRET = "sk-llm-1234567890abcdefghijNOAL"


def test_get_masks_api_key(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", LONG_SECRET)
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com")
    monkeypatch.setattr(DEFAULT_SETTINGS, "llm_model", "test-model")

    resp = get_llm_settings()

    assert resp.api_key_configured is True
    assert resp.api_key_preview
    assert LONG_SECRET not in resp.api_key_preview
    assert resp.base_url == "https://example.com"
    assert resp.model == "test-model"
    assert resp.api_format in ("anthropic", "openai")


def test_get_when_no_key_reports_unconfigured(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    resp = get_llm_settings()

    assert resp.api_key_configured is False
    assert resp.api_key_preview == ""


def test_update_without_api_key_keeps_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_API_KEY", "sk-existing-xxxxxxxxxx")
    env_file = tmp_path / ".env.local"
    env_file.write_text("LLM_API_KEY=sk-existing-xxxxxxxxxx\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "_env_local_path", lambda: env_file)

    resp = update_llm_settings(LlmSettingsPayload(base_url="https://new.example.com"))

    assert resp.api_key_configured is True
    assert os.environ["LLM_API_KEY"] == "sk-existing-xxxxxxxxxx"
    assert resp.api_key_preview != "sk-existing-xxxxxxxxxx"


def test_update_with_new_api_key_persists_and_masks(monkeypatch, tmp_path):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env.local"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings_module, "_env_local_path", lambda: env_file)

    new_key = "sk-new-1234567890abcd"
    resp = update_llm_settings(LlmSettingsPayload(api_key=new_key))

    assert resp.api_key_configured is True
    assert new_key not in resp.api_key_preview
    assert os.environ["LLM_API_KEY"] == new_key
    assert f"LLM_API_KEY={new_key}" in env_file.read_text(encoding="utf-8")


def test_legacy_env_names_still_resolve(monkeypatch):
    # Old ANTHROPIC_*/CLAUDE_* names must keep working as a fallback.
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-legacy-1234567890")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.legacy.com/anthropic")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("CLAUDE_MODEL", "legacy-model")
    monkeypatch.setattr(DEFAULT_SETTINGS, "llm_model", None)

    resp = get_llm_settings()

    assert resp.api_key_configured is True
    assert resp.base_url == "https://api.legacy.com/anthropic"
    assert resp.model == "legacy-model"
    assert resp.api_format == "anthropic"


def test_current_snapshot_is_independently_testable(monkeypatch):
    """_current_snapshot accepts an explicit settings object, no global needed."""
    from app.config import AppSettings
    from app.routes.settings import _current_snapshot

    monkeypatch.setenv("LLM_API_KEY", "sk-snap-1234567890ab")
    monkeypatch.setenv("LLM_BASE_URL", "https://snap.example.com/v1")
    monkeypatch.delenv("LLM_API_FORMAT", raising=False)

    custom = AppSettings(
        root_dir=DEFAULT_SETTINGS.root_dir,
        data_dir=DEFAULT_SETTINGS.data_dir,
        sqlite_dir=DEFAULT_SETTINGS.sqlite_dir,
        sqlite_path=DEFAULT_SETTINGS.sqlite_path,
        projects_dir=DEFAULT_SETTINGS.projects_dir,
        llm_model="snap-model",
    )

    resp = _current_snapshot(custom)

    assert resp.model == "snap-model"
    assert resp.base_url == "https://snap.example.com/v1"
    assert resp.api_key_configured is True
    assert resp.api_format == "openai"
