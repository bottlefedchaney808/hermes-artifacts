"""Model usage board — aggregate session_model_usage across all Hermes profiles.

collect(repo_path) treats repo_path as the HERMES ROOT directory (the manifest
supplies it; `--repo` overrides). Read-only, stdlib only.
"""
from __future__ import annotations

import datetime as _dt
import glob as _glob
import sqlite3
from pathlib import Path

from collectors import register

HERMES_ROOT = Path("C:/Users/bottl/AppData/Local/hermes")


@register("model-usage")
def collect(repo_path=None) -> dict:
    return {"summary": [], "tables": [], "charts": [],
            "notes": ["No usage data found."],
            "source": {"note": "no state.db scanned"},
            "viz": {}}


_COLS = ["session_id","model","billing_provider","billing_base_url","billing_mode",
         "task","api_call_count","input_tokens","output_tokens","cache_read_tokens",
         "cache_write_tokens","reasoning_tokens","estimated_cost_usd","actual_cost_usd",
         "cost_status","cost_source","first_seen","last_seen"]


def _dbs(root: Path) -> list[tuple[str, Path]]:
    """[(profile_name, db_path)] for the root db + every profiles/*/state.db."""
    root = Path(root)
    out = []
    if (root / "state.db").exists():
        out.append(("(root)", root / "state.db"))
    for p in sorted(_glob.glob(str(root / "profiles" / "*" / "state.db"))):
        out.append((Path(p).parent.name, Path(p)))
    return out


def _read_all(root: Path) -> list[dict]:
    rows = []
    for profile, db in _dbs(root):
        try:
            conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            cur = conn.execute("select %s from session_model_usage" % ",".join(_COLS))
            for r in cur.fetchall():
                d = dict(zip(_COLS, r))
                d["profile"] = profile
                rows.append(d)
            conn.close()
        except Exception:
            continue          # missing table / locked / corrupt -> skip that profile
    return rows


_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _host(url: str) -> str:
    u = (url or "").split("://", 1)[-1]
    return (u.split("/", 1)[0] if "/" in u else u).lower()


def _lane(r: dict) -> str:
    prov = (r.get("billing_provider") or "").strip().lower()
    host = _host(r.get("billing_base_url") or "").split(":")[0]
    if prov in ("custom", "llamacpp") or host in _LOOPBACK:
        return "local"
    if prov == "moa":
        return "moa"
    return prov or "unknown"


def _fresh(r):     return (r.get("input_tokens") or 0) + (r.get("output_tokens") or 0)
def _cached(r):    return r.get("cache_read_tokens") or 0
def _reasoning(r): return r.get("reasoning_tokens") or 0
def _cost(r):      return r.get("estimated_cost_usd") or 0.0
def _calls(r):     return r.get("api_call_count") or 0
