from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import DEFAULT_SETTINGS

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ClaudeSettingsPayload(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


class ClaudeSettingsResponse(BaseModel):
    api_key: str
    base_url: str
    model: str


def _env_local_path() -> Path:
    return DEFAULT_SETTINGS.root_dir / "backend" / ".env.local"


def _persist_env_setting(key: str, value: str) -> None:
    """Update or insert a single KEY=value line in .env.local, preserving the rest."""
    env_path = _env_local_path()
    if not env_path.exists():
        env_path.write_text(f"{key}={value}\n", encoding="utf-8")
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        stripped = line.lstrip("#").strip()
        if stripped.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@router.get("/claude", response_model=ClaudeSettingsResponse)
def get_claude_settings() -> ClaudeSettingsResponse:
    return ClaudeSettingsResponse(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        base_url=os.environ.get("ANTHROPIC_BASE_URL", ""),
        model=DEFAULT_SETTINGS.claude_model or os.environ.get("CLAUDE_MODEL", ""),
    )


@router.put("/claude", response_model=ClaudeSettingsResponse)
def update_claude_settings(payload: ClaudeSettingsPayload) -> ClaudeSettingsResponse:
    if payload.api_key is not None:
        os.environ["ANTHROPIC_API_KEY"] = payload.api_key
        _persist_env_setting("ANTHROPIC_API_KEY", payload.api_key)
    if payload.base_url is not None:
        os.environ["ANTHROPIC_BASE_URL"] = payload.base_url
        _persist_env_setting("ANTHROPIC_BASE_URL", payload.base_url)
    if payload.model is not None:
        DEFAULT_SETTINGS.claude_model = payload.model
        os.environ["CLAUDE_MODEL"] = payload.model
        _persist_env_setting("CLAUDE_MODEL", payload.model)

    return ClaudeSettingsResponse(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        base_url=os.environ.get("ANTHROPIC_BASE_URL", ""),
        model=DEFAULT_SETTINGS.claude_model or os.environ.get("CLAUDE_MODEL", ""),
    )
