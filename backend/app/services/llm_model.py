from __future__ import annotations

import os
from typing import Literal

from langchain_core.language_models import BaseChatModel

from ..config import AppSettings
from ..models import ProviderIssue, ProviderReadiness

LLM_PROVIDER = "DEEP_AGENTS"
ApiFormat = Literal["anthropic", "openai"]


def _env(*names: str, default: str = "") -> str:
    """Read the first set env var (supports renamed/new names with legacy fallback)."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def resolve_llm_config(
    settings: AppSettings,
) -> tuple[str, str | None, str, ApiFormat]:
    """Resolve (api_key, base_url, model, api_format) with legacy env-name fallback."""
    api_key = _env("LLM_API_KEY", "ANTHROPIC_API_KEY")
    base_url = _env("LLM_BASE_URL", "ANTHROPIC_BASE_URL") or None
    model = settings.llm_model or _env("LLM_MODEL", "CLAUDE_MODEL")
    fmt = (settings.llm_api_format or _env("LLM_API_FORMAT") or "").lower()
    if fmt not in ("anthropic", "openai"):
        # Auto-detect by base_url shape when not specified explicitly.
        # Note: "/v1" alone (without "anthropic" in the URL) is treated as OpenAI.
        # Edge case: an Anthropic-compatible proxy whose URL contains "/v1" but not
        # "anthropic" would be misdetected. Set LLM_API_FORMAT explicitly to override.
        if base_url and "anthropic" in base_url:
            fmt = "anthropic"
        elif base_url and ("/v1" in base_url or "openai" in base_url):
            fmt = "openai"
        else:
            fmt = "anthropic"
    return api_key, base_url, model, fmt


def build_chat_model(
    settings: AppSettings,
    *,
    timeout: float | None = None,
    max_retries: int = 2,
) -> BaseChatModel:
    """Build a LangChain chat model for the configured base_url format.

    Supports both Anthropic-compatible (ChatAnthropic) and OpenAI-compatible
    (ChatOpenAI) endpoints, selected by LLM_API_FORMAT or auto-detected from
    the base_url.
    """
    api_key, base_url, model, fmt = resolve_llm_config(settings)
    if not api_key:
        raise ProviderIssue(
            provider=LLM_PROVIDER,
            message="未配置 LLM_API_KEY（或旧名 ANTHROPIC_API_KEY），主链路无法启动。",
        )
    if not model:
        raise ProviderIssue(
            provider=LLM_PROVIDER,
            message="未配置 LLM_MODEL（或旧名 CLAUDE_MODEL），主链路无法启动。",
        )
    to = timeout or settings.llm_stream_timeout_seconds or 120
    if fmt == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model, api_key=api_key, base_url=base_url, timeout=to, max_retries=max_retries
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model, api_key=api_key, base_url=base_url, timeout=to, max_retries=max_retries
    )


def llm_readiness(settings: AppSettings) -> ProviderReadiness:
    api_key, base_url, model, fmt = resolve_llm_config(settings)
    if not api_key or not model:
        return ProviderReadiness(
            provider=LLM_PROVIDER,
            status="not_configured",
            summary="LLM 运行时还没有准备好。",
            detail="未配置 LLM_API_KEY 或 LLM_MODEL。",
            action_label="配置 LLM 模型",
        )
    detail = f"当前模型：{model}；接口格式：{fmt}"
    if base_url:
        detail += f"；base_url：{base_url}"
    return ProviderReadiness(
        provider=LLM_PROVIDER,
        status="ready",
        summary="LLM 运行时已就绪，且已锁定模型配置。",
        detail=detail,
    )
