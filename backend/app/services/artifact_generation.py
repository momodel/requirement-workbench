from ..models import ArtifactRecord


def generate_placeholder_artifact(project_id: str, artifact_type: str) -> ArtifactRecord:
    return ArtifactRecord(
        id=f"{project_id}-{artifact_type}",
        project_id=project_id,
        artifact_type=artifact_type,
        title=f"{artifact_type} 占位稿",
        summary="当前仅创建 artifact 占位记录，后续接真实模型生成与 HTML 校验。",
        status="placeholder",
        content_format="json"
    )
