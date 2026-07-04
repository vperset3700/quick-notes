from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "cours_data.db"
ALLOWED_STATUS = ("queued", "processing", "completed", "failed")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Return a SQLite connection configured for concurrent access."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # Concurrency and reliability pragmas
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    # Primary table with retry metadata: attempt_count, last_error, next_attempt_at, max_attempts
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pdf_queue (
            hash TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            file_size_mb REAL NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            next_attempt_at TEXT,
            max_attempts INTEGER NOT NULL DEFAULT 5,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pdf_queue_status
        ON pdf_queue(status);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_pdf_queue_next_attempt
        ON pdf_queue(next_attempt_at);
        """
    )

    conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS trg_pdf_queue_updated_at
        AFTER UPDATE ON pdf_queue
        FOR EACH ROW
        BEGIN
            UPDATE pdf_queue SET updated_at = datetime('now') WHERE hash = OLD.hash;
        END;
        """
    )

    # For existing databases: try to add missing columns (silently ignore failures)
    try:
        conn.execute("ALTER TABLE pdf_queue ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0;")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE pdf_queue ADD COLUMN last_error TEXT;")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE pdf_queue ADD COLUMN next_attempt_at TEXT;")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE pdf_queue ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 5;")
    except Exception:
        pass
