from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_local_env_file(root_dir: Path) -> None:
    env_path = root_dir / "backend" / ".env.local"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        if os.environ.get(key) in {None, ""}:
            os.environ[key] = value


@dataclass(slots=True)
class AppSettings:
    root_dir: Path
    data_dir: Path
    sqlite_dir: Path
    sqlite_path: Path
    projects_dir: Path
    qdrant_path: Path | None = None
    qdrant_url: str | None = None
    qdrant_collection_prefix: str = "project"
    evidence_backend: str = "qdrant_llamaindex"
    embedder_backend: str = "fastembed"
    embedder_model: str | None = None
    reranker_model: str | None = None
    evidence_recall_top_k: int = 20
    chunk_size: int = 500
    chunk_overlap: int = 120
    evidence_query_timeout_seconds: float = 15.0
    evidence_top_k: int = 6
    claude_cli_path: str | None = None
    claude_model: str | None = None
    claude_max_turns: int = 6
    claude_stream_timeout_seconds: float = 90.0
    claude_structured_timeout_seconds: float = 45.0
    claude_artifact_timeout_seconds: float = 180.0
    default_timezone: str = "Asia/Shanghai"
    apimart_api_key: str | None = None
    apimart_base_url: str | None = None
    apimart_image_model: str | None = None
    public_api_base_url: str = "http://127.0.0.1:8001"
    image_generation_timeout_seconds: float = 240.0
    image_generation_request_timeout_seconds: float = 60.0
    image_generation_poll_interval_seconds: float = 2.0
    qiniu_access_key: str | None = None
    qiniu_secret_key: str | None = None
    qiniu_bucket: str | None = None
    qiniu_domain: str | None = None
    qiniu_key_prefix: str = "audio"
    audio_transcription_backend: str = "aliyun_filetrans"
    audio_transcription_timeout_seconds: float = 300.0
    audio_transcription_poll_interval_seconds: float = 2.0
    aliyun_ak_id: str | None = None
    aliyun_ak_secret: str | None = None
    aliyun_app_key: str | None = None
    aliyun_filetrans_region: str = "cn-shanghai"
    volcengine_voice_ws_url: str = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
    volcengine_voice_app_id: str | None = None
    volcengine_voice_access_key: str | None = None
    volcengine_voice_resource_id: str = "volc.speech.dialog"
    volcengine_voice_app_key: str = "PlgvMymc7f3tQnJ6"
    volcengine_voice_bot_name: str = "需求访谈助手"
    volcengine_voice_speaking_style: str = "口语自然、像资深需求分析顾问。"
    volcengine_voice_model: str | None = None
    volcengine_voice_speaker: str = "zh_female_vv_jupiter_bigtts"

    def __post_init__(self) -> None:
        if self.qdrant_path is None:
            self.qdrant_path = self.data_dir / "qdrant"

    @property
    def cas_project_dir(self) -> Path:
        candidate = self.root_dir / "backend"
        return candidate if candidate.exists() else self.root_dir

    @classmethod
    def from_env(cls) -> "AppSettings":
        root_dir = Path(__file__).resolve().parents[2]
        _load_local_env_file(root_dir)
        data_dir = Path(os.getenv("REQUIREMENT_WORKBENCH_DATA_DIR", root_dir / "data"))
        sqlite_dir = Path(os.getenv("REQUIREMENT_WORKBENCH_SQLITE_DIR", data_dir / "sqlite"))
        sqlite_path = Path(
            os.getenv(
                "REQUIREMENT_WORKBENCH_SQLITE_PATH",
                sqlite_dir / "requirement-workbench.db",
            )
        )
        projects_dir = Path(
            os.getenv("REQUIREMENT_WORKBENCH_PROJECTS_DIR", data_dir / "projects")
        )
        qdrant_path = Path(os.getenv("REQUIREMENT_WORKBENCH_QDRANT_PATH", data_dir / "qdrant"))

        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            sqlite_dir=sqlite_dir,
            sqlite_path=sqlite_path,
            projects_dir=projects_dir,
            qdrant_path=qdrant_path,
            qdrant_url=os.getenv("REQUIREMENT_WORKBENCH_QDRANT_URL"),
            qdrant_collection_prefix=os.getenv("REQUIREMENT_WORKBENCH_QDRANT_COLLECTION_PREFIX", "project"),
            evidence_backend=os.getenv("REQUIREMENT_WORKBENCH_EVIDENCE_BACKEND", "qdrant_llamaindex"),
            embedder_backend=os.getenv("REQUIREMENT_WORKBENCH_EMBEDDER_BACKEND", "fastembed"),
            embedder_model=os.getenv("REQUIREMENT_WORKBENCH_EMBEDDER_MODEL") or "BAAI/bge-small-zh-v1.5",
            reranker_model=os.getenv("REQUIREMENT_WORKBENCH_RERANKER_MODEL") or None,
            evidence_recall_top_k=int(os.getenv("REQUIREMENT_WORKBENCH_EVIDENCE_RECALL_TOP_K", "20")),
            chunk_size=int(os.getenv("REQUIREMENT_WORKBENCH_CHUNK_SIZE", "500")),
            chunk_overlap=int(os.getenv("REQUIREMENT_WORKBENCH_CHUNK_OVERLAP", "120")),
            evidence_query_timeout_seconds=float(
                os.getenv(
                    "REQUIREMENT_WORKBENCH_EVIDENCE_QUERY_TIMEOUT_SECONDS",
                    os.getenv("EVIDENCE_QUERY_TIMEOUT_SECONDS", "15"),
                )
            ),
            evidence_top_k=int(
                os.getenv(
                    "REQUIREMENT_WORKBENCH_EVIDENCE_TOP_K",
                    os.getenv("EVIDENCE_TOP_K", "6"),
                )
            ),
            claude_cli_path=os.getenv("CLAUDE_CODE_CLI_PATH"),
            claude_model=os.getenv("CLAUDE_MODEL"),
            claude_max_turns=int(os.getenv("CLAUDE_MAX_TURNS", "6")),
            claude_stream_timeout_seconds=float(
                os.getenv("CLAUDE_STREAM_TIMEOUT_SECONDS", "90")
            ),
            claude_structured_timeout_seconds=float(
                os.getenv("CLAUDE_STRUCTURED_TIMEOUT_SECONDS", "45")
            ),
            claude_artifact_timeout_seconds=float(
                os.getenv("CLAUDE_ARTIFACT_TIMEOUT_SECONDS", "180")
            ),
            default_timezone=os.getenv("REQUIREMENT_WORKBENCH_TIMEZONE", "Asia/Shanghai"),
            apimart_api_key=os.getenv("APIMART_API_KEY"),
            apimart_base_url=os.getenv("APIMART_BASE_URL"),
            apimart_image_model=os.getenv("APIMART_IMAGE_MODEL"),
            public_api_base_url=os.getenv("PUBLIC_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/"),
            image_generation_timeout_seconds=float(os.getenv("IMAGE_GENERATION_TIMEOUT_SECONDS", "240")),
            image_generation_request_timeout_seconds=float(os.getenv("IMAGE_GENERATION_REQUEST_TIMEOUT_SECONDS", "60")),
            image_generation_poll_interval_seconds=float(os.getenv("IMAGE_GENERATION_POLL_INTERVAL_SECONDS", "2")),
            qiniu_access_key=os.getenv("REQUIREMENT_WORKBENCH_QINIU_ACCESS_KEY"),
            qiniu_secret_key=os.getenv("REQUIREMENT_WORKBENCH_QINIU_SECRET_KEY"),
            qiniu_bucket=os.getenv("REQUIREMENT_WORKBENCH_QINIU_BUCKET"),
            qiniu_domain=os.getenv("REQUIREMENT_WORKBENCH_QINIU_DOMAIN"),
            qiniu_key_prefix=os.getenv("REQUIREMENT_WORKBENCH_QINIU_KEY_PREFIX", "audio"),
            audio_transcription_backend=os.getenv(
                "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_BACKEND",
                "aliyun_filetrans",
            ),
            audio_transcription_timeout_seconds=float(
                os.getenv(
                    "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_TIMEOUT_SECONDS",
                    "300",
                )
            ),
            audio_transcription_poll_interval_seconds=float(
                os.getenv(
                    "REQUIREMENT_WORKBENCH_AUDIO_TRANSCRIPTION_POLL_INTERVAL_SECONDS",
                    "2",
                )
            ),
            aliyun_ak_id=os.getenv("REQUIREMENT_WORKBENCH_ALIYUN_AK_ID"),
            aliyun_ak_secret=os.getenv("REQUIREMENT_WORKBENCH_ALIYUN_AK_SECRET"),
            aliyun_app_key=os.getenv("REQUIREMENT_WORKBENCH_ALIYUN_APP_KEY"),
            aliyun_filetrans_region=os.getenv(
                "REQUIREMENT_WORKBENCH_ALIYUN_FILETRANS_REGION",
                "cn-shanghai",
            ),
            volcengine_voice_ws_url=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_WS_URL",
                "wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
            ),
            volcengine_voice_app_id=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_APP_ID"
            ),
            volcengine_voice_access_key=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_ACCESS_KEY"
            ),
            volcengine_voice_resource_id=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_RESOURCE_ID",
                "volc.speech.dialog",
            ),
            volcengine_voice_app_key=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_APP_KEY",
                "PlgvMymc7f3tQnJ6",
            ),
            volcengine_voice_bot_name=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_BOT_NAME",
                "需求访谈助手",
            ),
            volcengine_voice_speaking_style=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_SPEAKING_STYLE",
                "口语自然、简短明确、像资深需求分析顾问。",
            ),
            volcengine_voice_model=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_MODEL"
            ),
            volcengine_voice_speaker=os.getenv(
                "REQUIREMENT_WORKBENCH_VOLCENGINE_VOICE_SPEAKER",
                "zh_female_vv_jupiter_bigtts",
            ),
        )


DEFAULT_SETTINGS = AppSettings.from_env()
