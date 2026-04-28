from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..models import (
    MobileVoiceBootstrap,
    ProviderIssue,
    ProviderReadiness,
    SourceRecord,
    StateItem,
    VoiceTranscriptEntry,
)
from .project_catalog import ProjectCatalog, now_iso
from .project_state import ProjectStateService
from .runtime_contracts import EvidenceRuntime


@dataclass(slots=True)
class VoiceRoundContext:
    source: SourceRecord
    initial_prompt: str


class MobileVoiceService:
    PROVIDER_NAME = "VOLCENGINE_REALTIME_VOICE"

    def __init__(
        self,
        catalog: ProjectCatalog,
        project_state: ProjectStateService,
        evidence_runtime: EvidenceRuntime,
    ) -> None:
        self.catalog = catalog
        self.project_state = project_state
        self.evidence_runtime = evidence_runtime

    def get_provider_readiness(self) -> ProviderReadiness:
        settings = self.catalog.settings
        missing: list[str] = []
        if not settings.volcengine_voice_app_id:
            missing.append("REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_APP_ID")
        if not settings.volcengine_voice_access_key:
            missing.append("REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_ACCESS_KEY")

        if missing:
            return ProviderReadiness(
                provider=self.PROVIDER_NAME,
                status="not_configured",
                summary="实时语音未配置，手机端实时通话不可用。",
                detail="缺少配置：" + "、".join(missing),
                action_label="配置实时语音",
            )

        return ProviderReadiness(
            provider=self.PROVIDER_NAME,
            status="ready",
            summary="实时语音桥接配置已就绪。",
            detail=(
                f"ws={settings.volcengine_voice_ws_url}; "
                f"resource_id={settings.volcengine_voice_resource_id}; "
                f"speaker={settings.volcengine_voice_speaker}"
            ),
            action_label=None,
        )

    def list_recent_rounds(self, project_id: str, *, limit: int = 12) -> list[SourceRecord]:
        rounds = [
            source
            for source in self.catalog.list_sources(project_id)
            if source.source_kind == "voice_session" and self._is_closed_round(source)
        ]
        return list(reversed(rounds[-limit:]))

    def build_initial_prompt(self, project_id: str) -> str:
        project = self.catalog.get_project(project_id)
        if project is None:
            raise LookupError("Project not found")

        state = self.project_state.get_project_state(project_id)
        sections = [
            "你是客户需求转译台的手机端语音访谈助手，正在和客户做需求澄清。",
            "只说自然中文，适合语音播报，优先理解真实需求, 提供合适方案；",
            "",
            f"当前项目：{project.name}",
            f"项目摘要：{project.summary}",
        ]

        known = self._format_state_items(
            "当前较可信的理解",
            state.current_understanding,
            empty_text="当前还没有形成稳定理解。",
        )
        pending = self._format_state_items(
            "优先待确认项",
            state.pending_items,
            empty_text="当前没有记录待确认项。",
        )
        confirmed = self._format_state_items(
            "已确认事实",
            state.confirmed_items,
            empty_text="当前还没有明确锁定的已确认事实。",
        )
        return "\n".join([*sections, known, pending, confirmed]).strip()

    def get_bootstrap(self, project_id: str) -> MobileVoiceBootstrap:
        project = self.catalog.get_project(project_id)
        if project is None:
            raise LookupError("Project not found")

        return MobileVoiceBootstrap(
            project=project,
            evidence=self.evidence_runtime.get_project_readiness(project_id),
            voice=self.get_provider_readiness(),
            initial_prompt=self.build_initial_prompt(project_id),
            recent_rounds=self.list_recent_rounds(project_id),
        )

    def create_round(self, project_id: str) -> VoiceRoundContext:
        project = self.catalog.get_project(project_id)
        if project is None:
            raise LookupError("Project not found")

        self._ensure_round_ready(project_id)
        started_at = now_iso(self.catalog.settings)
        timestamp_label = started_at[5:16].replace("T", " ")
        round_name = f"语音访谈记录 {timestamp_label}"
        file_name = f"voice-round-{started_at[:19].replace(':', '').replace('-', '')}.md"
        storage_path = self.catalog.settings.projects_dir / project_id / "sources" / file_name
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        prompt = self.build_initial_prompt(project_id)
        storage_path.write_text(
            self._render_round_markdown(
                project_name=project.name,
                started_at=started_at,
                updated_at=started_at,
                finished=False,
                entries=[],
            ),
            encoding="utf-8",
        )

        source = self.catalog.create_source(
            project_id=project_id,
            name=round_name,
            source_kind="voice_session",
            upload_kind="text",
            storage_path=str(storage_path),
            normalized_path=str(storage_path),
            index_input_mode="direct_text",
            normalize_status="parsed",
            normalize_summary="语音访谈记录已开始，等待实时转写写入。",
            index_status="pending",
            index_error=None,
        )
        return VoiceRoundContext(source=source, initial_prompt=prompt)

    def sync_round(
        self,
        *,
        project_id: str,
        source_id: str,
        entries: list[VoiceTranscriptEntry],
        finished: bool,
    ) -> SourceRecord:
        source = self.catalog.get_source(source_id)
        if source is None or source.project_id != project_id:
            raise LookupError("Voice round not found")
        if source.source_kind != "voice_session":
            raise ValueError("source_id is not a mobile voice round")

        if not source.storage_path:
            raise ValueError("Voice round source has no storage path")
        storage_path = Path(source.storage_path)
        project = self.catalog.get_project(project_id)
        if project is None:
            raise LookupError("Project not found")

        updated_at = now_iso(self.catalog.settings)
        markdown = self._render_round_markdown(
            project_name=project.name,
            started_at=source.created_at,
            updated_at=updated_at,
            finished=finished,
            entries=entries,
        )
        storage_path.write_text(markdown, encoding="utf-8")

        summary = self._build_round_summary(entries, finished=finished)
        refreshed = self.catalog.update_source_normalization(
            source_id=source_id,
            normalized_path=str(storage_path),
            index_input_mode="direct_text",
            normalize_status="parsed",
            normalize_summary=summary,
            index_status="pending",
            index_error=None,
        )

        if not entries:
            return refreshed

        try:
            self.evidence_runtime.reindex_source(project_id, source_id)
        except ProviderIssue as exc:
            self.catalog.update_source_index_status(
                source_id=source_id,
                index_status="index_failed",
                index_error=exc.message,
            )
            raise

        self.catalog.update_source_index_status(
            source_id=source_id,
            index_status="indexed",
            index_error=None,
        )

        latest = self.catalog.get_source(source_id)
        if latest is None:
            raise LookupError("Voice round disappeared after reindex")
        return latest

    def _ensure_round_ready(self, project_id: str) -> None:
        voice = self.get_provider_readiness()
        if voice.status != "ready":
            raise ProviderIssue(
                provider=self.PROVIDER_NAME,
                message=voice.detail or voice.summary,
            )

        evidence = self.evidence_runtime.get_global_readiness()
        if evidence.status != "ready":
            raise ProviderIssue(
                provider=evidence.provider,
                message=evidence.detail or evidence.summary,
            )

        self.evidence_runtime.ensure_project_knowledge_base(project_id)

    @staticmethod
    def _format_state_items(title: str, items: list[StateItem], *, empty_text: str) -> str:
        if not items:
            return f"{title}：{empty_text}"

        snippets = []
        for item in items[:4]:
            body = " ".join(item.body.split()).strip()
            if len(body) > 80:
                body = f"{body[:80].rstrip()}..."
            snippets.append(f"- {item.title}：{body}")
        return "\n".join([f"{title}：", *snippets])

    @staticmethod
    def _render_round_markdown(
        *,
        project_name: str,
        started_at: str,
        updated_at: str,
        finished: bool,
        entries: list[VoiceTranscriptEntry],
    ) -> str:
        lines = [
            f"# 语音访谈记录 · {project_name}",
            "",
            f"- 开始时间：{started_at}",
            f"- 最近更新：{updated_at}",
            f"- 轮次状态：{'已结束' if finished else '进行中'}",
            "- 来源：手机端实时语音通话",
            "",
            "## 实时对话转写",
        ]

        if not entries:
            lines.extend(
                [
                    "",
                    "当前还没有写入实时转写内容。",
                ]
            )
            return "\n".join(lines).strip() + "\n"

        for entry in entries:
            role_label = {
                "user": "用户",
                "assistant": "助手",
                "system": "系统",
            }.get(entry.role, entry.role)
            status = "最终稿" if entry.is_final else "实时草稿"
            lines.extend(
                [
                    "",
                    f"### {role_label} · {status}",
                    entry.text.strip(),
                ]
            )
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _build_round_summary(entries: list[VoiceTranscriptEntry], *, finished: bool) -> str:
        if not entries:
            return "本轮已结束，未写入有效转写。" if finished else "语音访谈记录已开始，等待实时转写写入。"

        latest_user = next(
            (item for item in reversed(entries) if item.role == "user" and item.text.strip()),
            None,
        )
        latest_assistant = next(
            (item for item in reversed(entries) if item.role == "assistant" and item.text.strip()),
            None,
        )
        parts: list[str] = []
        if latest_user:
            parts.append(f"用户：{' '.join(latest_user.text.split())[:90]}")
        if latest_assistant:
            parts.append(f"助手：{' '.join(latest_assistant.text.split())[:90]}")
        if not parts:
            parts.append("语音轮次已有转写内容。")
        if finished:
            parts.append("本轮已结束。")
        return "；".join(parts)

    @staticmethod
    def _is_closed_round(source: SourceRecord) -> bool:
        summary = (source.normalize_summary or "").strip()
        return "本轮已结束" in summary
