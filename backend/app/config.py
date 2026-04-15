import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("REQUIREMENT_WORKBENCH_DATA_DIR", ROOT_DIR / "data"))
SQLITE_DIR = DATA_DIR / "sqlite"
SQLITE_PATH = SQLITE_DIR / "requirement-workbench.db"
PROJECTS_DIR = DATA_DIR / "projects"
BACKEND_PORT = int(os.environ.get("REQUIREMENT_WORKBENCH_BACKEND_PORT", "8000"))
FRONTEND_PORT = int(os.environ.get("REQUIREMENT_WORKBENCH_FRONTEND_PORT", "5173"))
