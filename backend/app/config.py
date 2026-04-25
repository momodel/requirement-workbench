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
        )


DEFAULT_SETTINGS = AppSettings.from_env()
