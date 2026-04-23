from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ArtifactRecord, ArtifactType, ProjectState, ProjectSummary, ProviderIssue
from .project_catalog import ProjectCatalog
from .project_state import ProjectStateService
from .runtime_contracts import AgentRuntime


class ArtifactGenerationService:
    def __init__(self, settings: AppSettings = DEFAULT_SETTINGS):
        self.settings = settings
        self.catalog = ProjectCatalog(settings)
        self.project_state = ProjectStateService(self.catalog)

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
    ) -> str:
        payload = {
            "artifact_type": artifact_type,
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

    @staticmethod
    def _artifact_type_label(artifact_type: ArtifactType) -> str:
        if artifact_type == "document":
            return "文档稿"
        if artifact_type == "page_solution":
            return "页面方案"
        if artifact_type == "interaction_flow":
            return "交互稿"
        return artifact_type

    def _create_artifact_version(
        self,
        *,
        project_id: str,
        artifact: ArtifactRecord,
    ) -> None:
        summary = f"已生成{self._artifact_type_label(artifact.artifact_type)}《{artifact.title}》"
        self.catalog.create_version_snapshot(
            project_id=project_id,
            trigger_kind="交付物生成",
            summary=summary,
            state_json=self.project_state.snapshot_json(project_id),
        )

    async def generate_from_model(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        agent_runtime: AgentRuntime,
    ) -> ArtifactRecord:
        generation_cache_key = self._generation_cache_key(
            project=project,
            state=state,
            artifact_type=artifact_type,
        )
        cached = self._reusable_artifact(
            project_id=project.id,
            artifact_type=artifact_type,
            cache_key=generation_cache_key,
        )
        if cached:
            return cached

        try:
            generated = await asyncio.wait_for(
                agent_runtime.generate_artifact(
                    project=project,
                    state=state,
                    artifact_type=artifact_type,
                ),
                timeout=self.settings.claude_artifact_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderIssue(
                provider="CLAUDE_AGENT_SDK",
                message="Claude 交付物生成超时，请稍后重试。",
                status_code=504,
            ) from exc

        if artifact_type == "document":
            body = (generated.body or "").strip()
            if not body:
                raise ValueError("文档稿正文不能为空。")
            artifact = self.catalog.save_artifact(
                project_id=project.id,
                artifact_type=artifact_type,
                title=generated.title,
                summary=generated.summary,
                status="generated",
                content_format="markdown",
                storage_path=None,
                body=body,
                metadata={
                    "generator": "claude-agent-sdk",
                    "generation_cache_key": generation_cache_key,
                },
            )
            self._create_artifact_version(project_id=project.id, artifact=artifact)
            return artifact

        html = self.validate_html_output(generated.title, generated.html or "")
        index_path = self._artifact_dir(project.id, artifact_type) / "index.html"
        index_path.write_text(html, encoding="utf-8")
        artifact = self.catalog.save_artifact(
            project_id=project.id,
            artifact_type=artifact_type,
            title=generated.title,
            summary=generated.summary,
            status="generated",
            content_format="html",
            storage_path=str(index_path),
            body=None,
            metadata={
                "generator": "claude-agent-sdk",
                "generation_cache_key": generation_cache_key,
            },
        )
        self._create_artifact_version(project_id=project.id, artifact=artifact)
        return artifact
