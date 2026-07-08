from __future__ import annotations

import asyncio
import base64
import binascii
import mimetypes
import uuid
from pathlib import Path

from ..models import AgentTurnInput, ArtifactRecord, ArtifactType, ChatImageAttachment, ChatStreamRequest, ProviderIssue
from .artifact_generation import ArtifactGenerationService
from .project_catalog import ProjectCatalog
from .project_state import ProjectStateService
from .runtime_contracts import AgentRuntime, EvidenceRuntime, WikiRuntime


class ChatService:
    def __init__(
        self,
        catalog: ProjectCatalog,
        project_state: ProjectStateService,
        evidence_runtime: EvidenceRuntime,
        agent_runtime: AgentRuntime,
        artifact_generation: ArtifactGenerationService,
        wiki_runtime: WikiRuntime | None = None,
    ):
        self.catalog = catalog
        self.project_state = project_state
        self.evidence_runtime = evidence_runtime
        self.agent_runtime = agent_runtime
        self.artifact_generation = artifact_generation
        self.wiki_runtime = wiki_runtime

    async def _query_evidence_with_timeout(self, *args, **kwargs):
        return await asyncio.wait_for(
            asyncio.to_thread(self.evidence_runtime.query, *args, **kwargs),
            timeout=self.catalog.settings.evidence_query_timeout_seconds,
        )

    def _stream_timeout_for_phase(self, phase: str | None) -> float:
        base_timeout = self.catalog.settings.llm_stream_timeout_seconds
        if not phase:
            return base_timeout

        if phase == "tool_running:generate_artifact":
            return max(
                base_timeout,
                self.catalog.settings.llm_artifact_timeout_seconds + 15,
            )

        if phase == "tool_running:generate_visual_mockup":
            return max(
                base_timeout,
                self.catalog.settings.image_generation_timeout_seconds + 15,
            )

        if phase == "tool_running:query_project_evidence":
            return max(
                base_timeout,
                self.catalog.settings.evidence_query_timeout_seconds + 10,
            )

        return base_timeout

    @staticmethod
    def _artifact_title(artifact_type: ArtifactType) -> str:
        return {
            "document": "需求文档稿",
            "page_solution": "页面方案原型",
            "interaction_flow": "交互稿原型",
        }[artifact_type]

    @staticmethod
    def _artifact_summary(artifact_type: ArtifactType) -> str:
        return {
            "document": "文档稿正在生成中。",
            "page_solution": "页面方案正在生成中。",
            "interaction_flow": "交互稿正在生成中。",
        }[artifact_type]

    def _save_chat_image_attachments(
        self,
        *,
        project_id: str,
        attachments: list[ChatImageAttachment],
    ) -> list[dict]:
        image_refs: list[dict] = []
        for attachment in attachments[:4]:
            if not attachment.content_type.startswith("image/"):
                raise ValueError("聊天附件目前只支持图片。")
            if not attachment.data_url.startswith("data:"):
                raise ValueError("图片附件格式不正确。")
            try:
                header, encoded = attachment.data_url.split(",", 1)
            except ValueError as exc:
                raise ValueError("图片附件缺少 data URL 内容。") from exc
            if ";base64" not in header:
                raise ValueError("图片附件必须使用 base64 data URL。")
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("图片附件 base64 内容无法解析。") from exc
            if len(image_bytes) > 5 * 1024 * 1024:
                raise ValueError("单张聊天图片不能超过 5MB。")

            image_id = f"user-image-{uuid.uuid4().hex[:10]}"
            extension = mimetypes.guess_extension(attachment.content_type) or Path(attachment.name).suffix or ".png"
            if extension == ".jpe":
                extension = ".jpg"
            image_dir = self.catalog.settings.projects_dir / project_id / "chat-images" / image_id
            image_dir.mkdir(parents=True, exist_ok=True)
            (image_dir / f"image{extension}").write_bytes(image_bytes)
            image_refs.append(
                {
                    "id": image_id,
                    "title": attachment.name,
                    "summary": "用户上传的聊天图片",
                    "url": f"/api/projects/{project_id}/chat-images/{image_id}",
                    "content_type": attachment.content_type,
                }
            )
        return image_refs

    async def _complete_requested_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
        artifact_type: ArtifactType,
        user_message: str,
    ) -> None:
        project = self.catalog.get_project(project_id)
        if not project:
            return
        state = self.project_state.get_project_state(project_id)
        title = self._artifact_title(artifact_type)
        try:
            generated = await self.agent_runtime.generate_artifact(
                project=project,
                state=state,
                artifact_type=artifact_type,
                additional_instruction=user_message,
            )
            artifact = self.artifact_generation.save_generated_output(
                project_id=project_id,
                artifact_type=artifact_type,
                generated=generated,
                metadata={"generator": "async-artifact-request"},
                artifact_id=artifact_id,
            )
            self.project_state.create_artifact_version(
                project_id=project_id,
                artifact_title=artifact.title,
                artifact_type=artifact.artifact_type,
            )
        except Exception as exc:
            self.catalog.save_artifact(
                project_id=project_id,
                artifact_type=artifact_type,
                title=title,
                summary=str(exc) or "交付物生成失败。",
                status="failed",
                content_format="markdown" if artifact_type == "document" else "html",
                storage_path=None,
                body=None,
                metadata={"generator": "async-artifact-request", "error": str(exc)},
                artifact_id=artifact_id,
            )

    def _create_requested_artifact_jobs(
        self,
        *,
        project_id: str,
        artifact_types: list[ArtifactType],
        user_message: str,
    ) -> list[ArtifactRecord]:
        artifacts: list[ArtifactRecord] = []
        for artifact_type in dict.fromkeys(artifact_types):
            artifact = self.catalog.save_artifact(
                project_id=project_id,
                artifact_type=artifact_type,
                title=self._artifact_title(artifact_type),
                summary=self._artifact_summary(artifact_type),
                status="generating",
                content_format="markdown" if artifact_type == "document" else "html",
                storage_path=None,
                body=None,
                metadata={"generator": "async-artifact-request"},
            )
            artifacts.append(artifact)
            asyncio.create_task(
                self._complete_requested_artifact(
                    project_id=project_id,
                    artifact_id=artifact.id,
                    artifact_type=artifact_type,
                    user_message=user_message,
                )
            )
        return artifacts

    async def stream_turn(self, project_id: str, payload: ChatStreamRequest):
        project = self.catalog.get_project(project_id)
        if not project:
            raise LookupError("Project not found")

        stream_group_id = f"stream-{uuid.uuid4().hex[:10]}"
        user_image_refs = self._save_chat_image_attachments(
            project_id=project_id,
            attachments=payload.image_attachments,
        )
        self.catalog.create_message(
            project_id=project_id,
            role="user",
            content=payload.message,
            source_refs=[{"__image_results__": user_image_refs}] if user_image_refs else None,
            stream_group_id=stream_group_id,
        )

        if payload.request_artifact_types:
            artifacts = self._create_requested_artifact_jobs(
                project_id=project_id,
                artifact_types=payload.request_artifact_types,
                user_message=payload.message,
            )
            yield (
                "assistant_status",
                {
                    "phase": "tool_running:generate_artifact",
                    "label": "交付物已进入后台生成",
                },
            )
            yield (
                "artifact_patch",
                {
                    "op": "upsert",
                    "items": [artifact.model_dump() for artifact in artifacts],
                },
            )
            message = "交付物已开始生成，完成后会出现在右侧交付物区。"
            self.catalog.create_message(
                project_id=project_id,
                role="assistant",
                content=message,
                stream_group_id=stream_group_id,
            )
            yield ("message_chunk", {"text": message, "replace": True})
            yield ("done", {"stream_group_id": stream_group_id})
            return

        state = self.project_state.get_project_state(project_id)
        sources = self.catalog.list_sources(project_id)
        selected_sources = [
            source for source in sources if source.id in payload.selected_source_ids
        ] or sources
        turn_input = AgentTurnInput(
            project=project,
            state=state,
            user_message=payload.message,
            selected_source_ids=payload.selected_source_ids,
            source_summaries=[source.parse_summary or source.name for source in selected_sources],
            evidence_summary="当前还没有调用项目知识库检索工具。",
            evidence_citations=[],
            request_artifact_types=payload.request_artifact_types,
            recent_messages=self.catalog.list_recent_messages(project_id, limit=12),
            user_image_refs=user_image_refs,
        )

        assistant_saved = False
        final_assistant_message = ""
        final_citations: list[dict] = []
        final_images: list[dict] = []
        current_timeout = (
            self.catalog.settings.llm_artifact_timeout_seconds + 15
            if payload.request_artifact_types
            else self.catalog.settings.llm_stream_timeout_seconds
        )

        try:
            iterator = self.agent_runtime.run_streaming_turn(turn_input)
            while True:
                try:
                    event_type, value = await asyncio.wait_for(
                        iterator.__anext__(),
                        timeout=current_timeout,
                    )
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError as exc:
                    raise ProviderIssue(
                        provider="CLAUDE_AGENT_SDK",
                        message="Claude 回复超时，当前轮对话已中止。请稍后重试。",
                    ) from exc

                if event_type == "assistant_status":
                    current_timeout = self._stream_timeout_for_phase(
                        str(value.get("phase") or "")
                    )
                elif payload.request_artifact_types:
                    current_timeout = self.catalog.settings.llm_artifact_timeout_seconds + 15
                else:
                    current_timeout = self.catalog.settings.llm_stream_timeout_seconds

                if event_type == "image_result":
                    final_images.append(value)
                    yield (event_type, value)
                    continue

                if event_type == "final_message":
                    final_assistant_message = str(value.get("text") or "").strip()
                    raw_citations = value.get("citations")
                    final_citations = raw_citations if isinstance(raw_citations, list) else []
                    if final_assistant_message:
                        yield (
                            "message_chunk",
                            {
                                "text": final_assistant_message,
                                "replace": True,
                            },
                        )
                    if final_assistant_message and not assistant_saved:
                        self.catalog.create_message(
                            project_id=project_id,
                            role="assistant",
                            content=final_assistant_message,
                            source_refs=final_citations + ([{"__image_results__": final_images}] if final_images else []),
                            stream_group_id=stream_group_id,
                        )
                        assistant_saved = True
                    continue

                if event_type == "done":
                    continue

                if event_type == "version_patch" and self.wiki_runtime is not None:
                    items = value.get("items") if isinstance(value, dict) else None
                    if isinstance(items, list):
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            if item.get("title") == "artifact_generated":
                                continue
                            self.wiki_runtime.schedule_maintain_after_checkpoint(
                                project_id,
                                str(item.get("body") or item.get("title") or ""),
                            )

                yield (event_type, value)
        except ProviderIssue as exc:
            if final_assistant_message and not assistant_saved:
                self.catalog.create_message(
                    project_id=project_id,
                    role="assistant",
                    content=final_assistant_message,
                    source_refs=final_citations + ([{"__image_results__": final_images}] if final_images else []),
                    stream_group_id=stream_group_id,
                )
            yield (
                "error",
                {
                    "provider": exc.provider,
                    "message": exc.message,
                },
            )

        yield ("done", {"stream_group_id": stream_group_id})
