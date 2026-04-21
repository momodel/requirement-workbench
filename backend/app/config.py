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
    notebooklm_home_dir: Path
    claude_cli_path: str | None = None
    claude_model: str | None = None
    claude_max_turns: int = 6
    claude_stream_timeout_seconds: float = 90.0
    claude_structured_timeout_seconds: float = 45.0
    claude_artifact_timeout_seconds: float = 180.0
    notebooklm_query_timeout_seconds: float = 30.0
    notebooklm_default_notebook_id: str | None = None
    notebooklm_mode: str = "real"
    default_timezone: str = "Asia/Shanghai"

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
        notebooklm_home_dir = Path(
            os.getenv("NOTEBOOKLM_HOME", data_dir / "notebooklm")
        )

        return cls(
            root_dir=root_dir,
            data_dir=data_dir,
            sqlite_dir=sqlite_dir,
            sqlite_path=sqlite_path,
            projects_dir=projects_dir,
            notebooklm_home_dir=notebooklm_home_dir,
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
            notebooklm_query_timeout_seconds=float(
                os.getenv("NOTEBOOKLM_QUERY_TIMEOUT_SECONDS", "30")
            ),
            notebooklm_default_notebook_id=os.getenv("NOTEBOOKLM_DEFAULT_NOTEBOOK_ID"),
            notebooklm_mode=os.getenv("NOTEBOOKLM_MODE", "real").strip().lower() or "real",
            default_timezone=os.getenv("REQUIREMENT_WORKBENCH_TIMEZONE", "Asia/Shanghai"),
        )


DEFAULT_SETTINGS = AppSettings.from_env()
