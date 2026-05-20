"""SQLite storage layer for tokenledger.

All API calls and context sessions are persisted here.
Default location: ~/.tokenledger/tokenledger.db
Override with TOKENLEDGER_DB env var.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def default_db_path() -> str:
    return os.environ.get(
        "TOKENLEDGER_DB",
        str(Path.home() / ".tokenledger" / "tokenledger.db"),
    )


def init_db(db_path: str | None = None) -> str:
    """Create tables if they don't exist. Returns the db path used."""
    path = db_path or default_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS contexts (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT    NOT NULL,
                source    TEXT    NOT NULL CHECK(source IN ('git', 'manual')),
                started_at TEXT   NOT NULL,
                ended_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS calls (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                context_id    INTEGER REFERENCES contexts(id),
                timestamp     TEXT    NOT NULL,
                model         TEXT    NOT NULL,
                input_tokens  INTEGER,
                output_tokens INTEGER,
                input_cost    REAL,
                output_cost   REAL,
                total_cost    REAL,
                request_id    TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_calls_context  ON calls(context_id);
            CREATE INDEX IF NOT EXISTS idx_calls_timestamp ON calls(timestamp);
        """)
    return path


@contextmanager
def get_conn(db_path: str | None = None):
    path = db_path or default_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Context operations
# ---------------------------------------------------------------------------

def open_context(name: str, source: str, db_path: str | None = None) -> int:
    """Open a new context session. Returns the new context id."""
    now = datetime.now(tz=timezone.utc).isoformat()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO contexts (name, source, started_at) VALUES (?, ?, ?)",
            (name, source, now),
        )
        return cur.lastrowid


def close_context(context_id: int, db_path: str | None = None) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE contexts SET ended_at = ? WHERE id = ?",
            (now, context_id),
        )


def get_open_context(db_path: str | None = None) -> sqlite3.Row | None:
    """Return the most recent open (unended) context, if any."""
    with get_conn(db_path) as conn:
        return conn.execute(
            "SELECT * FROM contexts WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()


# ---------------------------------------------------------------------------
# Call recording
# ---------------------------------------------------------------------------

def record_call(
    *,
    context_id: int | None,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    input_cost: float | None,
    output_cost: float | None,
    total_cost: float | None,
    request_id: str | None,
    db_path: str | None = None,
) -> int:
    now = datetime.now(tz=timezone.utc).isoformat()
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO calls
               (context_id, timestamp, model, input_tokens, output_tokens,
                input_cost, output_cost, total_cost, request_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (context_id, now, model, input_tokens, output_tokens,
             input_cost, output_cost, total_cost, request_id),
        )
        return cur.lastrowid


# ---------------------------------------------------------------------------
# Reporting queries
# ---------------------------------------------------------------------------

def get_context_summary(db_path: str | None = None) -> list[sqlite3.Row]:
    """Return per-context cost and call count, newest first."""
    with get_conn(db_path) as conn:
        return conn.execute("""
            SELECT
                c.id,
                c.name,
                c.source,
                c.started_at,
                c.ended_at,
                COUNT(ca.id)        AS call_count,
                SUM(ca.total_cost)  AS total_cost,
                SUM(ca.input_tokens)  AS total_input_tokens,
                SUM(ca.output_tokens) AS total_output_tokens
            FROM contexts c
            LEFT JOIN calls ca ON ca.context_id = c.id
            GROUP BY c.id
            ORDER BY c.id DESC
        """).fetchall()


def get_calls_for_context(context_id: int | None, db_path: str | None = None) -> list[sqlite3.Row]:
    with get_conn(db_path) as conn:
        if context_id is None:
            return conn.execute(
                "SELECT * FROM calls WHERE context_id IS NULL ORDER BY timestamp"
            ).fetchall()
        return conn.execute(
            "SELECT * FROM calls WHERE context_id = ? ORDER BY timestamp",
            (context_id,),
        ).fetchall()
