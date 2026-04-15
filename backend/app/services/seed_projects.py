import json
import sqlite3

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
    confirmed_items=[
        StateItem(
            id="confirmed-1",
            title="旧 demo 已转入参考资产区",
            body="当前仓库主路径只保留一期主工程和当前有效文档。"
        )
    ],
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

SEED_MESSAGES = [
    {
        "id": "msg-seed-user",
        "role": "user",
        "content": "我们需要核对业务系统和财务系统对应科目的逐笔金额。",
        "source_refs_json": "[]",
    },
    {
        "id": "msg-seed-assistant",
        "role": "assistant",
        "content": "我会先把问题收敛成字段映射、科目口径和人工复核边界三部分。",
        "source_refs_json": "[]",
    },
]


def _upsert_project(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT OR REPLACE INTO projects (
          id, name, scenario_type, summary, status, created_at, updated_at, seed_key
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            SEED_PROJECT.id,
            SEED_PROJECT.name,
            SEED_PROJECT.scenario_type,
            SEED_PROJECT.summary,
            SEED_PROJECT.status,
            SEED_PROJECT.created_at,
            SEED_PROJECT.updated_at,
            SEED_PROJECT.seed_key,
        ),
    )


def _upsert_sources(connection: sqlite3.Connection) -> None:
    for source in SEED_SOURCES:
        connection.execute(
            """
            INSERT OR REPLACE INTO sources (
              id, project_id, name, source_kind, upload_kind, storage_path,
              normalized_path, notebook_import_mode, parse_status, parse_summary, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.id,
                source.project_id,
                source.name,
                source.source_kind,
                source.upload_kind,
                None,
                None,
                "normalized-text",
                source.parse_status,
                source.parse_summary,
                SEED_PROJECT.created_at,
            ),
        )


def _upsert_state_items(connection: sqlite3.Connection) -> None:
    state_map = {
        "current_understanding": SEED_STATE.current_understanding,
        "pending_items": SEED_STATE.pending_items,
        "confirmed_items": SEED_STATE.confirmed_items,
        "conflict_items": SEED_STATE.conflict_items,
        "mvp_items": SEED_STATE.mvp_items,
    }

    for category, items in state_map.items():
        for item in items:
            connection.execute(
                """
                INSERT OR REPLACE INTO state_items (
                  id, project_id, category, title, body, status, source_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    SEED_PROJECT.id,
                    category,
                    item.title,
                    item.body,
                    "active",
                    json.dumps([]),
                    SEED_PROJECT.updated_at,
                ),
            )


def _upsert_versions(connection: sqlite3.Connection) -> None:
    for item in SEED_STATE.versions:
        connection.execute(
            """
            INSERT OR REPLACE INTO version_snapshots (
              id, project_id, trigger_kind, summary, state_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.id,
                SEED_PROJECT.id,
                "seed",
                item.body,
                json.dumps(
                    {
                        "current_understanding": [entry.model_dump() for entry in SEED_STATE.current_understanding],
                        "pending_items": [entry.model_dump() for entry in SEED_STATE.pending_items],
                    },
                    ensure_ascii=False,
                ),
                SEED_PROJECT.updated_at,
            ),
        )


def _upsert_messages(connection: sqlite3.Connection) -> None:
    for message in SEED_MESSAGES:
        connection.execute(
            """
            INSERT OR REPLACE INTO messages (
              id, project_id, role, content, source_refs_json, created_at, stream_group_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message["id"],
                SEED_PROJECT.id,
                message["role"],
                message["content"],
                message["source_refs_json"],
                SEED_PROJECT.created_at,
                "seed-stream",
            ),
        )


def seed_database(connection: sqlite3.Connection) -> None:
    _upsert_project(connection)
    _upsert_sources(connection)
    _upsert_state_items(connection)
    _upsert_versions(connection)
    _upsert_messages(connection)
