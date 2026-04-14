import sqlite3
from pathlib import Path

from .config import SQLITE_DIR, SQLITE_PATH


def init_db() -> None:
    SQLITE_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(SQLITE_PATH)
    try:
        schema_path = Path(__file__).with_name("schema.sql")
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        connection.commit()
    finally:
        connection.close()


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(SQLITE_PATH)
    connection.row_factory = sqlite3.Row
    return connection
