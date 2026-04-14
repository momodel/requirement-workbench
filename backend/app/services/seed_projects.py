from ..models import ProjectState, ProjectSummary, SourceRecord, StateItem


SEED_PROJECT = ProjectSummary(
    id="seed-reconciliation",
    name="业财逐笔对账",
    scenario_type="financial-reconciliation",
    summary="默认 seed project，用于验证一期的 project-first 工作台和全链路骨架。",
    status="seed",
    created_at="2026-04-14T00:00:00+08:00",
    updated_at="2026-04-14T00:00:00+08:00",
    seed_key="reconciliation"
)

SEED_SOURCES = [
    SourceRecord(
        id="src-order-fields",
        project_id=SEED_PROJECT.id,
        name="订单字段说明.md",
        source_kind="markdown",
        upload_kind="seed",
        parse_status="parsed",
        parse_summary="包含订单号、业务类型、含税金额和退款标记。",
        sync_status="pending"
    ),
    SourceRecord(
        id="src-finance-rules",
        project_id=SEED_PROJECT.id,
        name="财务科目口径.pdf",
        source_kind="pdf",
        upload_kind="seed",
        parse_status="parsed",
        parse_summary="定义结算、退款、冲销对应的财务科目口径。",
        sync_status="pending"
    )
]

SEED_STATE = ProjectState(
    current_understanding=[
        StateItem(
            id="understanding-1",
            title="仓库主路径已切换到全栈一期",
            body="旧 demo 已归档，新的 frontend/backend/data/docs 成为主工程。"
        )
    ],
    pending_items=[
        StateItem(
            id="pending-1",
            title="接入真实 AgentRuntime 和 EvidenceRuntime",
            body="当前后端先保留接口和占位实现，后续再换成 Claude 与 NotebookLM。"
        )
    ],
    confirmed_items=[],
    conflict_items=[],
    mvp_items=[],
    versions=[
        StateItem(
            id="version-1",
            title="初始化快照",
            body="完成旧资产归档和一期全栈骨架创建。"
        )
    ],
    artifacts=[]
)
