from __future__ import annotations

import os

import app.routes.settings as settings_module
from app.config import DEFAULT_SETTINGS
from app.routes.settings import (
    ClaudeSettingsPayload,
    get_claude_settings,
    update_claude_settings,
)

LONG_SECRET = "sk-cp-1234567890abcdefghijNOAL"


def test_get_masks_api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", LONG_SECRET)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.com")
    monkeypatch.setattr(DEFAULT_SETTINGS, "claude_model", "test-model")

    resp = get_claude_settings()

    assert resp.api_key_configured is True
    assert resp.api_key_preview
    # the raw secret must never appear in the masked preview
    assert LONG_SECRET not in resp.api_key_preview
    assert resp.base_url == "https://example.com"
    assert resp.model == "test-model"


def test_get_when_no_key_reports_unconfigured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    resp = get_claude_settings()

    assert resp.api_key_configured is False
    assert resp.api_key_preview == ""


def test_update_without_api_key_keeps_existing(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-existing-xxxxxxxxxx")
    env_file = tmp_path / ".env.local"
    env_file.write_text("ANTHROPIC_API_KEY=sk-existing-xxxxxxxxxx\n", encoding="utf-8")
    monkeypatch.setattr(settings_module, "_env_local_path", lambda: env_file)

    resp = update_claude_settings(ClaudeSettingsPayload(base_url="https://new.example.com"))

    assert resp.api_key_configured is True
    # empty/omitted api_key must not overwrite the existing key
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-existing-xxxxxxxxxx"
    assert resp.api_key_preview != "sk-existing-xxxxxxxxxx"


def test_update_with_new_api_key_persists_and_masks(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    env_file = tmp_path / ".env.local"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setattr(settings_module, "_env_local_path", lambda: env_file)

    new_key = "sk-new-1234567890abcd"
    resp = update_claude_settings(ClaudeSettingsPayload(api_key=new_key))

    assert resp.api_key_configured is True
    assert new_key not in resp.api_key_preview
    assert os.environ["ANTHROPIC_API_KEY"] == new_key
    assert f"ANTHROPIC_API_KEY={new_key}" in env_file.read_text(encoding="utf-8")
