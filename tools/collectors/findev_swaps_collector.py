"""FinDev swaps snapshot — read-only peek at swaps.db (WAL-safe, index-only count)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from collectors import register, default_findev_repo

DEFAULT_REPO = default_findev_repo()


def _recent_rows(con: sqlite3.Connection, table: str, limit: int = 5) -> dict:
    cur = con.execute(f"SELECT * FROM {table} ORDER BY rowid DESC LIMIT {limit}")
    cols = [d[0] for d in cur.description]
    return {"id": table, "title": table, "columns": cols,
            "rows": [list(r) for r in cur.fetchall()]}


@register("findev-swaps")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    db = repo_path / "swaps.db"
    if not db.exists():
        return {"summary": [{"label": "swaps.db", "value": "missing", "tone": "bad"}],
                "tables": [], "charts": [], "notes": [f"{db} not found"],
                "source": {"repo": str(repo_path), "collector": "findev-swaps",
                           "note": "swaps.db"}}
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=30)
    try:
        max_row = con.execute(
            "SELECT COALESCE(MAX(rowid), 0) FROM swap_trades").fetchone()[0]
        runs_count = con.execute(
            "SELECT COUNT(*) FROM orchestrator_runs").fetchone()[0]
        scrape = _recent_rows(con, "scrape_log")
    finally:
        con.close()
    return {
        "summary": [
            {"label": "swap_trades (max rowid)", "value": f"{max_row:,}"},
            {"label": "orchestrator_runs", "value": str(runs_count)},
            {"label": "db size", "value": f"{db.stat().st_size / (1 << 30):.0f} GB"},
        ],
        "tables": [scrape],
        "charts": [],
        "notes": ["Read-only snapshot. Row count via MAX(rowid) — a COUNT(*) "
                  "on the 346 GB swap_trades table is a full scan and is avoided."],
        "source": {"repo": str(repo_path), "collector": "findev-swaps",
                   "note": "swaps.db"},
    }
