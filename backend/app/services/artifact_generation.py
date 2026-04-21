from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ArtifactRecord, ArtifactType, ProjectState, ProjectSummary, ProviderIssue
from .project_catalog import ProjectCatalog
from .runtime_contracts import AgentRuntime


class ArtifactGenerationService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings
        self.catalog = ProjectCatalog(settings)

    def validate_html_output(self, artifact_title: str, html: str) -> str:
        cleaned = html.strip()
        if not cleaned:
            raise ValueError(f"{artifact_title} 的 HTML 不能为空。")
        if "<!doctype html" not in cleaned.lower():
            raise ValueError(f"{artifact_title} 的 HTML 缺少 doctype。")
        if "<title" not in cleaned.lower():
            raise ValueError(f"{artifact_title} 的 HTML 缺少 title。")
        if "<main" not in cleaned.lower():
            raise ValueError(f"{artifact_title} 的 HTML 缺少主内容区域。")
        if "<script" in cleaned.lower() and re.search(r"<script[^>]+src=['\"]https?://", cleaned, re.I):
            raise ValueError(f"{artifact_title} 的 HTML 包含外链脚本。")
        return cleaned

    def _artifact_dir(self, project_id: str, artifact_type: ArtifactType) -> Path:
        artifact_dir = self.settings.projects_dir / project_id / "artifacts" / artifact_type
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    @staticmethod
    def _normalize_title(artifact_type: ArtifactType, title: str) -> str:
        cleaned = " ".join((title or "").split()).strip()
        if artifact_type == "document":
            return cleaned or "需求文档稿"

        if artifact_type == "page_solution":
            if not cleaned:
                return "页面方案原型"
            if "页面方案" in cleaned or "页面原型" in cleaned:
                return cleaned
            if "设计稿" in cleaned:
                return re.sub(r"(页面)?设计稿", "页面方案", cleaned, count=1)
            return f"页面方案 - {cleaned}"

        if not cleaned:
            return "交互稿原型"
        if "交互稿" in cleaned or "交互原型" in cleaned:
            return cleaned
        return f"交互稿 - {cleaned}"

    @staticmethod
    def _normalize_summary(summary: str) -> str:
        cleaned = " ".join((summary or "").split()).strip()
        if cleaned and ("<!doctype html" in cleaned.lower() or re.search(r"<[^>]+>", cleaned)):
            return "当前已生成可预览草稿。"
        return cleaned or "当前已生成可预览草稿。"

    @staticmethod
    def _state_item_payload(items) -> list[dict]:
        normalized: list[dict] = []
        for item in items:
            payload = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            normalized.append(
                {
                    "title": payload.get("title", ""),
                    "body": payload.get("body", ""),
                    "status": payload.get("status", ""),
                    "source_ids": payload.get("source_ids", []),
                }
            )
        return normalized

    def _generation_cache_key(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        additional_instruction: str | None = None,
    ) -> str:
        payload = {
            "artifact_type": artifact_type,
            "additional_instruction": additional_instruction or "",
            "project": {
                "name": project.name,
                "scenario_type": project.scenario_type,
                "summary": project.summary,
            },
            "state": {
                "current_understanding": self._state_item_payload(state.current_understanding),
                "pending_items": self._state_item_payload(state.pending_items),
                "confirmed_items": self._state_item_payload(state.confirmed_items),
                "conflict_items": self._state_item_payload(state.conflict_items),
                "mvp_items": self._state_item_payload(state.mvp_items),
            },
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _reusable_artifact(
        self,
        *,
        project_id: str,
        artifact_type: ArtifactType,
        cache_key: str,
    ) -> ArtifactRecord | None:
        latest = self.catalog.get_latest_artifact_with_metadata(project_id, artifact_type)
        if not latest:
            return None

        artifact, metadata = latest
        if metadata.get("generation_cache_key") != cache_key:
            return None

        if artifact.content_format == "html":
            if not artifact.storage_path or not Path(artifact.storage_path).exists():
                return None
        elif artifact.content_format == "markdown" and not (artifact.body or "").strip():
            return None

        return artifact

    def save_generated_output(
        self,
        *,
        project_id: str,
        artifact_type: ArtifactType,
        generated: GeneratedArtifactOutput,
        metadata: dict | None = None,
    ) -> ArtifactRecord:
        normalized_title = self._normalize_title(artifact_type, generated.title)
        normalized_summary = self._normalize_summary(generated.summary)

        if artifact_type == "document":
            body = (generated.body or "").strip()
            if not body:
                raise ValueError("文档稿正文不能为空。")
            return self.catalog.save_artifact(
                project_id=project_id,
                artifact_type=artifact_type,
                title=normalized_title,
                summary=normalized_summary,
                status="generated",
                content_format="markdown",
                storage_path=None,
                body=body,
                metadata=metadata,
            )

        html = self.validate_html_output(normalized_title, generated.html or "")
        index_path = self._artifact_dir(project_id, artifact_type) / "index.html"
        index_path.write_text(html, encoding="utf-8")
        return self.catalog.save_artifact(
            project_id=project_id,
            artifact_type=artifact_type,
            title=normalized_title,
            summary=normalized_summary,
            status="generated",
            content_format="html",
            storage_path=str(index_path),
            body=None,
            metadata=metadata,
        )

    async def generate_from_model(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        agent_runtime: AgentRuntime,
        additional_instruction: str | None = None,
    ) -> ArtifactRecord:
        generation_cache_key = self._generation_cache_key(
            project=project,
            state=state,
            artifact_type=artifact_type,
            additional_instruction=additional_instruction,
        )
        cached = self._reusable_artifact(
            project_id=project.id,
            artifact_type=artifact_type,
            cache_key=generation_cache_key,
        )
        if cached:
            return cached

        try:
            runtime_kwargs = {
                "project": project,
                "state": state,
                "artifact_type": artifact_type,
            }
            if additional_instruction:
                runtime_kwargs["additional_instruction"] = additional_instruction
            generated = await asyncio.wait_for(
                agent_runtime.generate_artifact(**runtime_kwargs),
                timeout=self.settings.claude_artifact_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message="Claude 交付物生成超时，请稍后重试。",
                status_code=504,
            ) from exc

        return self.save_generated_output(
            project_id=project.id,
            artifact_type=artifact_type,
            generated=generated,
            metadata={
                "generator": "claude-agent-sdk",
                "generation_cache_key": generation_cache_key,
            },
        )
