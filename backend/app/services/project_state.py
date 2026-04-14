from ..models import ProjectState
from .seed_projects import SEED_STATE


def get_project_state(project_id: str) -> ProjectState:
    if project_id == "seed-reconciliation":
        return SEED_STATE

    return ProjectState(
        current_understanding=[],
        pending_items=[],
        confirmed_items=[],
        conflict_items=[],
        mvp_items=[],
        versions=[],
        artifacts=[]
    )
