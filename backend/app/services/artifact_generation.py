import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ..config import PROJECTS_DIR
from ..db import get_connection
from ..models import ArtifactRecord
from .project_state import get_project_state


HTML_ARTIFACT_TYPES = {"page_solution", "interaction_flow"}


def _artifact_dir(project_id: str, artifact_id: str) -> Path:
    artifact_dir = PROJECTS_DIR / project_id / "artifacts" / artifact_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def validate_html_artifact(html: str) -> None:
    lowered = html.lower()
    if "<title>" not in lowered:
        raise ValueError("HTML artifact must include <title>.")
    if "<main" not in lowered:
        raise ValueError("HTML artifact must include <main>.")
    if "<nav" not in lowered:
        raise ValueError("HTML artifact must include <nav>.")
    if 'script src="http' in lowered or "script src='http" in lowered:
        raise ValueError("External scripts are not allowed.")
    if 'href="http' in lowered or "href='http" in lowered:
        raise ValueError("External links are not allowed in generated artifacts.")


def _build_document_payload(project_id: str, artifact_type: str) -> dict:
    state = get_project_state(project_id)
    return {
        "artifact_type": artifact_type,
        "title": "需求分析文档稿",
        "sections": [
            {
                "title": "当前理解",
                "items": [item.model_dump() for item in state.current_understanding],
            },
            {
                "title": "待确认项",
                "items": [item.model_dump() for item in state.pending_items],
            },
            {
                "title": "已确认项",
                "items": [item.model_dump() for item in state.confirmed_items],
            },
            {
                "title": "MVP 结论",
                "items": [item.model_dump() for item in state.mvp_items],
            },
        ],
    }


def _render_html_artifact(project_id: str, artifact_type: str) -> str:
    state = get_project_state(project_id)
    title = "页面方案" if artifact_type == "page_solution" else "交互稿"
    state_cards = state.current_understanding[:2] or state.pending_items[:2]
    card_markup = "".join(
        f"""
        <article class="card">
          <h3>{item.title}</h3>
          <p>{item.body}</p>
        </article>
        """
        for item in state_cards
    )
    html = f"""
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>{title}</title>
        <style>
          :root {{
            color: #132033;
            background: #f4f7fb;
            font-family: "SF Pro Text", "PingFang SC", sans-serif;
          }}
          body {{
            margin: 0;
            padding: 32px;
            background: linear-gradient(180deg, #f4f7fb 0%, #ebf0f8 100%);
          }}
          nav, main, section, article {{
            box-sizing: border-box;
          }}
          nav {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-radius: 20px;
            background: #fff;
            box-shadow: 0 18px 40px rgba(19, 32, 51, 0.08);
          }}
          main {{
            display: grid;
            gap: 20px;
            margin-top: 20px;
          }}
          .hero {{
            padding: 28px;
            border-radius: 24px;
            background: #16324f;
            color: #fff;
          }}
          .grid {{
            display: grid;
            grid-template-columns: 1.3fr 1fr;
            gap: 16px;
          }}
          .panel {{
            padding: 20px;
            border-radius: 20px;
            background: #fff;
            box-shadow: 0 18px 40px rgba(19, 32, 51, 0.08);
          }}
          .card {{
            padding: 14px 16px;
            border: 1px solid rgba(22, 50, 79, 0.12);
            border-radius: 16px;
            background: #f8fbff;
          }}
          .card + .card {{
            margin-top: 12px;
          }}
          ul {{
            margin: 0;
            padding-left: 20px;
          }}
        </style>
      </head>
      <body>
        <nav>
          <strong>客户需求转译台</strong>
          <span>{title}</span>
        </nav>
        <main>
          <section class="hero">
            <p>默认案例：业财逐笔对账</p>
            <h1>{title}</h1>
            <p>这个原型基于当前项目沉淀自动整理，重点展示差异识别、规则映射和人工复核闭环。</p>
          </section>
          <section class="grid">
            <section class="panel">
              <h2>关键页面</h2>
              <ul>
                <li>对账总览页</li>
                <li>逐笔差异明细页</li>
                <li>异常处理工作台</li>
                <li>映射规则配置页</li>
              </ul>
            </section>
            <section class="panel">
              <h2>关键沉淀引用</h2>
              {card_markup or '<p>当前还没有可引用沉淀。</p>'}
            </section>
          </section>
        </main>
      </body>
    </html>
    """
    validate_html_artifact(html)
    return html


def _persist_artifact(
    *,
    project_id: str,
    artifact_type: str,
    title: str,
    summary: str,
    status: str,
    content_format: str,
    content: str,
) -> ArtifactRecord:
    artifact_id = f"{artifact_type}-{uuid4().hex[:8]}"
    artifact_dir = _artifact_dir(project_id, artifact_id)
    file_name = "index.html" if content_format == "html" else "artifact.json"
    storage_path = artifact_dir / file_name
    storage_path.write_text(content, encoding="utf-8")

    created_at = datetime.now().isoformat()
    connection = get_connection()
    try:
        connection.execute(
            """
            INSERT INTO demo_artifacts (
              id, project_id, artifact_type, title, summary, status,
              content_format, storage_path, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                artifact_id,
                project_id,
                artifact_type,
                title,
                summary,
                status,
                content_format,
                str(storage_path),
                json.dumps({"artifact_type": artifact_type}, ensure_ascii=False),
                created_at,
                created_at,
            ),
        )
        connection.commit()
    finally:
        connection.close()

    return ArtifactRecord(
        id=artifact_id,
        project_id=project_id,
        artifact_type=artifact_type,
        title=title,
        summary=summary,
        status=status,
        content_format=content_format,
        storage_path=str(storage_path),
    )


def generate_artifact(project_id: str, artifact_type: str) -> ArtifactRecord:
    if artifact_type in HTML_ARTIFACT_TYPES:
        html = _render_html_artifact(project_id, artifact_type)
        return _persist_artifact(
            project_id=project_id,
            artifact_type=artifact_type,
            title="页面方案" if artifact_type == "page_solution" else "交互稿",
            summary="已生成可预览的 HTML 原型。",
            status="generated",
            content_format="html",
            content=html,
        )

    payload = _build_document_payload(project_id, artifact_type)
    return _persist_artifact(
        project_id=project_id,
        artifact_type=artifact_type,
        title=payload["title"],
        summary="已生成结构化文档稿，可供需求评审继续加工。",
        status="generated",
        content_format="json",
        content=json.dumps(payload, ensure_ascii=False, indent=2),
    )
