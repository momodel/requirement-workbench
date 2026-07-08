from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import DEFAULT_SETTINGS
from ..services.llm_model import resolve_llm_config

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LlmSettingsPayload(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_format: str | None = None


class LlmSettingsResponse(BaseModel):
    api_key_configured: bool
    api_key_preview: str
    base_url: str
    model: str
    api_format: str


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


def _mask_api_key(key: str) -> str:
    """Return a non-secret preview so the UI can confirm a key is set without exposing it."""
    if not key:
        return ""
    if len(key) <= 12:
        return "****"
    return f"{key[:6]}...{key[-4:]}"


def _current_snapshot() -> LlmSettingsResponse:
    api_key, base_url, model, fmt = resolve_llm_config(DEFAULT_SETTINGS)
    return LlmSettingsResponse(
        api_key_configured=bool(api_key),
        api_key_preview=_mask_api_key(api_key),
        base_url=base_url or "",
        model=model,
        api_format=fmt,
    )


@router.get("/llm", response_model=LlmSettingsResponse)
def get_llm_settings() -> LlmSettingsResponse:
    return _current_snapshot()


@router.put("/llm", response_model=LlmSettingsResponse)
def update_llm_settings(payload: LlmSettingsPayload) -> LlmSettingsResponse:
    if payload.api_key:
        os.environ["LLM_API_KEY"] = payload.api_key
        _persist_env_setting("LLM_API_KEY", payload.api_key)
    if payload.base_url is not None:
        os.environ["LLM_BASE_URL"] = payload.base_url
        _persist_env_setting("LLM_BASE_URL", payload.base_url)
    if payload.model is not None:
        DEFAULT_SETTINGS.llm_model = payload.model
        os.environ["LLM_MODEL"] = payload.model
        _persist_env_setting("LLM_MODEL", payload.model)
    if payload.api_format is not None:
        fmt = payload.api_format.strip().lower()
        if fmt in ("anthropic", "openai", ""):
            DEFAULT_SETTINGS.llm_api_format = fmt or None
            if fmt:
                os.environ["LLM_API_FORMAT"] = fmt
                _persist_env_setting("LLM_API_FORMAT", fmt)
            else:
                os.environ.pop("LLM_API_FORMAT", None)
                _persist_env_setting("LLM_API_FORMAT", "")

    return _current_snapshot()
