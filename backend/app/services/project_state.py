from __future__ import annotations

import json

from ..models import ProjectState, StateCategory, StateItem
from .project_catalog import ProjectCatalog


def empty_project_state() -> ProjectState:
    return ProjectState(
        current_understanding=[],
        pending_items=[],
        confirmed_items=[],
        conflict_items=[],
        mvp_items=[],
        versions=[],
        artifacts=[],
    )


class ProjectStateService:
    def __init__(self, catalog: ProjectCatalog):
        self.catalog = catalog

    def get_project_state(self, project_id: str) -> ProjectState:
        grouped = self.catalog.list_state_items(project_id)
        return ProjectState(
            current_understanding=grouped["current_understanding"],
            pending_items=grouped["pending_items"],
            confirmed_items=grouped["confirmed_items"],
            conflict_items=grouped["conflict_items"],
            mvp_items=grouped["mvp_items"],
            versions=grouped["versions"],
            artifacts=grouped["artifacts"],
        )

    def replace_category(
        self,
        *,
        project_id: str,
        category: StateCategory,
        items: list[StateItem],
    ) -> list[StateItem]:
        self.catalog.replace_state_items(project_id, category, items)
        return items

    def snapshot_json(self, project_id: str) -> str:
        state = self.get_project_state(project_id)
        return state.model_dump_json()

    def create_version(self, *, project_id: str, trigger_kind: str, summary: str) -> StateItem:
        return self.catalog.create_version_snapshot(
            project_id=project_id,
            trigger_kind=trigger_kind,
            summary=summary,
            state_json=self.snapshot_json(project_id),
        )
