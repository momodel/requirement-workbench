from datetime import datetime
from uuid import uuid4

from ..db import get_connection
from ..models import ArtifactRecord, ProjectSummary, SourceRecord, StateItem


def list_projects() -> list[ProjectSummary]:
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, name, scenario_type, summary, status, created_at, updated_at, seed_key
            FROM projects
            ORDER BY created_at
            """
        ).fetchall()
    finally:
        connection.close()

    return [
        ProjectSummary(
            id=row["id"],
            name=row["name"],
            scenario_type=row["scenario_type"],
            summary=row["summary"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            seed_key=row["seed_key"],
        )
        for row in rows
    ]


def create_project(name: str, summary: str, scenario_type: str) -> ProjectSummary:
    project = ProjectSummary(
        id=f"project-{uuid4().hex[:8]}",
        name=name,
        scenario_type=scenario_type,
        summary=summary,
        status="draft",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        seed_key=None,
    )

    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO projects (
              id, name, scenario_type, summary, status, created_at, updated_at, seed_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project.id,
                project.name,
                project.scenario_type,
                project.summary,
                project.status,
                project.created_at,
                project.updated_at,
                project.seed_key,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return project


def get_project(project_id: str) -> ProjectSummary | None:
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT id, name, scenario_type, summary, status, created_at, updated_at, seed_key
            FROM projects
            WHERE id = ?
            """,
            (project_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return ProjectSummary(
        id=row["id"],
        name=row["name"],
        scenario_type=row["scenario_type"],
        summary=row["summary"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        seed_key=row["seed_key"],
    )


def list_sources(project_id: str) -> list[SourceRecord]:
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
              id,
              project_id,
              name,
              source_kind,
              upload_kind,
              storage_path,
              normalized_path,
              parse_status,
              parse_summary,
              sync_status
            FROM sources
            WHERE project_id = ?
            ORDER BY created_at, id
            """,
            (project_id,),
        ).fetchall()
    finally:
        connection.close()

    return [
        SourceRecord(
            id=row["id"],
            project_id=row["project_id"],
            name=row["name"],
            source_kind=row["source_kind"],
            upload_kind=row["upload_kind"],
            storage_path=row["storage_path"],
            normalized_path=row["normalized_path"],
            parse_status=row["parse_status"],
            parse_summary=row["parse_summary"],
            sync_status=row["sync_status"] if "sync_status" in row.keys() else "pending",
        )
        for row in rows
    ]


def get_source(project_id: str, source_id: str) -> SourceRecord | None:
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT
              id,
              project_id,
              name,
              source_kind,
              upload_kind,
              storage_path,
              normalized_path,
              parse_status,
              parse_summary,
              sync_status
            FROM sources
            WHERE project_id = ? AND id = ?
            """,
            (project_id, source_id),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return SourceRecord(
        id=row["id"],
        project_id=row["project_id"],
        name=row["name"],
        source_kind=row["source_kind"],
        upload_kind=row["upload_kind"],
        storage_path=row["storage_path"],
        normalized_path=row["normalized_path"],
        parse_status=row["parse_status"],
        parse_summary=row["parse_summary"],
        sync_status=row["sync_status"],
    )


def list_versions(project_id: str) -> list[StateItem]:
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, trigger_kind, summary
            FROM version_snapshots
            WHERE project_id = ?
            ORDER BY created_at
            """,
            (project_id,),
        ).fetchall()
    finally:
        connection.close()

    return [
        StateItem(id=row["id"], title=row["trigger_kind"], body=row["summary"])
        for row in rows
    ]


def list_artifacts(project_id: str) -> list[ArtifactRecord]:
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, project_id, artifact_type, title, summary, status, content_format, storage_path
            FROM demo_artifacts
            WHERE project_id = ?
            ORDER BY created_at
            """,
            (project_id,),
        ).fetchall()
    finally:
        connection.close()

    return [
        ArtifactRecord(
            id=row["id"],
            project_id=row["project_id"],
            artifact_type=row["artifact_type"],
            title=row["title"],
            summary=row["summary"],
            status=row["status"],
            content_format=row["content_format"],
            storage_path=row["storage_path"],
        )
        for row in rows
    ]


def get_artifact(project_id: str, artifact_id: str) -> ArtifactRecord | None:
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT id, project_id, artifact_type, title, summary, status, content_format, storage_path
            FROM demo_artifacts
            WHERE project_id = ? AND id = ?
            """,
            (project_id, artifact_id),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    return ArtifactRecord(
        id=row["id"],
        project_id=row["project_id"],
        artifact_type=row["artifact_type"],
        title=row["title"],
        summary=row["summary"],
        status=row["status"],
        content_format=row["content_format"],
        storage_path=row["storage_path"],
    )
