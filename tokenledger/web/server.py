"""tokenledger web UI server.

Serves the dashboard and JSON API endpoints.
Start with: tokenledger ui [--host 127.0.0.1] [--port 8787]
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tokenledger.storage.db import default_db_path, init_db

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="tokenledger UI", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def _conn() -> sqlite3.Connection:
    db_path = init_db()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/context/{context_id}")
def context_detail(context_id: int):
    return FileResponse(STATIC_DIR / "context.html")


# ---------------------------------------------------------------------------
# API — summary stat cards
# ---------------------------------------------------------------------------

@app.get("/api/summary")
def api_summary() -> dict[str, Any]:
    with _conn() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(total_cost), 0)   AS all_time,
                COALESCE(SUM(CASE WHEN timestamp >= datetime('now', '-7 days')
                               THEN total_cost ELSE 0 END), 0) AS this_week,
                COALESCE(SUM(CASE WHEN timestamp >= datetime('now', '-30 days')
                               THEN total_cost ELSE 0 END), 0) AS this_month,
                COUNT(*)                        AS call_count,
                COALESCE(SUM(input_tokens), 0)  AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS total_output_tokens
            FROM calls
        """).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# API — cost by context (bar chart)
# ---------------------------------------------------------------------------

@app.get("/api/contexts")
def api_contexts() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT
                c.id,
                c.name,
                c.source,
                c.started_at,
                c.ended_at,
                CASE WHEN c.ended_at IS NULL THEN 1 ELSE 0 END AS is_active,
                COUNT(ca.id)                     AS call_count,
                COALESCE(SUM(ca.total_cost), 0)  AS total_cost,
                COALESCE(SUM(ca.input_tokens), 0)  AS total_input_tokens,
                COALESCE(SUM(ca.output_tokens), 0) AS total_output_tokens
            FROM contexts c
            LEFT JOIN calls ca ON ca.context_id = c.id
            GROUP BY c.id
            ORDER BY total_cost DESC
            LIMIT 20
        """).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# API — timeline (line chart)
# ---------------------------------------------------------------------------

@app.get("/api/timeline")
def api_timeline(days: int = 30) -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT
                date(timestamp) AS day,
                COALESCE(SUM(total_cost), 0)  AS daily_cost,
                COUNT(*)                       AS call_count
            FROM calls
            WHERE timestamp >= datetime('now', :offset)
            GROUP BY day
            ORDER BY day
        """, {"offset": f"-{days} days"}).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# API — model breakdown (donut chart)
# ---------------------------------------------------------------------------

@app.get("/api/models")
def api_models() -> list[dict[str, Any]]:
    with _conn() as conn:
        rows = conn.execute("""
            SELECT
                model,
                COUNT(*)                        AS call_count,
                COALESCE(SUM(total_cost), 0)    AS total_cost,
                COALESCE(SUM(input_tokens), 0)  AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS total_output_tokens
            FROM calls
            GROUP BY model
            ORDER BY total_cost DESC
        """).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# API — context detail
# ---------------------------------------------------------------------------

@app.get("/api/contexts/{context_id}")
def api_context_detail(context_id: int) -> dict[str, Any]:
    with _conn() as conn:
        ctx = conn.execute(
            "SELECT * FROM contexts WHERE id = ?", (context_id,)
        ).fetchone()
        if ctx is None:
            raise HTTPException(status_code=404, detail="Context not found")

        calls = conn.execute("""
            SELECT * FROM calls
            WHERE context_id = ?
            ORDER BY timestamp
        """, (context_id,)).fetchall()

        totals = conn.execute("""
            SELECT
                COALESCE(SUM(total_cost), 0)    AS total_cost,
                COALESCE(SUM(input_tokens), 0)  AS total_input_tokens,
                COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
                COUNT(*)                         AS call_count
            FROM calls WHERE context_id = ?
        """, (context_id,)).fetchone()

    return {
        "context": dict(ctx),
        "totals": dict(totals),
        "calls": [dict(c) for c in calls],
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_ui(host: str = "127.0.0.1", port: int = 8787) -> None:
    import uvicorn
    import webbrowser
    url = f"http://{host}:{port}"
    print(f"tokenledger UI at {url}")
    webbrowser.open(url)
    uvicorn.run(app, host=host, port=port, log_level="warning")
