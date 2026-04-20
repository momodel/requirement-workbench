from __future__ import annotations

import re
from pathlib import Path

from ..config import AppSettings, DEFAULT_SETTINGS
from ..models import ArtifactRecord, ArtifactType, ProjectState, ProjectSummary
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

    async def generate_from_model(
        self,
        *,
        project: ProjectSummary,
        state: ProjectState,
        artifact_type: ArtifactType,
        agent_runtime: AgentRuntime,
    ) -> ArtifactRecord:
        generated = await agent_runtime.generate_artifact(
            project=project,
            state=state,
            artifact_type=artifact_type,
        )

        if artifact_type == "document":
            body = (generated.body or "").strip()
            if not body:
                raise ValueError("文档稿正文不能为空。")
            return self.catalog.save_artifact(
                project_id=project.id,
                artifact_type=artifact_type,
                title=generated.title,
                summary=generated.summary,
                status="generated",
                content_format="markdown",
                storage_path=None,
                body=body,
                metadata={"generator": "claude-agent-sdk"},
            )

        html = self.validate_html_output(generated.title, generated.html or "")
        index_path = self._artifact_dir(project.id, artifact_type) / "index.html"
        index_path.write_text(html, encoding="utf-8")
        return self.catalog.save_artifact(
            project_id=project.id,
            artifact_type=artifact_type,
            title=generated.title,
            summary=generated.summary,
            status="generated",
            content_format="html",
            storage_path=str(index_path),
            body=None,
            metadata={"generator": "claude-agent-sdk"},
        )
