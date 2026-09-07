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


def _day(ts):
    try:
        return _dt.datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d")
    except Exception:
        return "unknown"


def _bucket(rows, keyfn):
    agg = {}
    for r in rows:
        k = keyfn(r)
        b = agg.setdefault(k, {"key": k, "fresh": 0, "cached": 0, "reasoning": 0,
                               "calls": 0, "cost_usd": 0.0, "lane": _lane(r)})
        b["fresh"] += _fresh(r); b["cached"] += _cached(r)
        b["reasoning"] += _reasoning(r); b["calls"] += _calls(r)
        b["cost_usd"] += _cost(r)
    return sorted(agg.values(), key=lambda x: -x["fresh"])


def _aggregate(rows):
    return {
        "by_provider": _bucket(rows, _lane),
        "by_model":    _bucket(rows, lambda r: (r.get("model") or "?").strip() or "?")[:15],
        "by_profile":  _bucket(rows, lambda r: r.get("profile") or "(root)"),
        "by_task":     _bucket(rows, lambda r: (r.get("task") or "").strip() or "main")[:12],
    }


def _timeseries(rows, max_days=30):
    days, provs = set(), set()
    cell = {}
    for r in rows:
        d, p = _day(r.get("last_seen")), _lane(r)
        if d == "unknown":
            continue
        days.add(d); provs.add(p)
        cell[(d, p)] = cell.get((d, p), 0) + _fresh(r)
    ordered = sorted(days)[-max_days:]
    keep = set(ordered)
    series = [{"name": p, "data": [cell.get((d, p), 0) for d in ordered]}
              for p in sorted(provs)]
    series.sort(key=lambda s: -sum(s["data"]))
    return {"days": ordered, "series": series,
            "calendar": [[d, sum(cell.get((d, p), 0) for p in provs)] for d in sorted(keep)]}


def _sankey(rows, top_models=10):
    top = {m["key"] for m in _bucket(rows, lambda r: (r.get("model") or "?"))[:top_models]}
    flows = {}
    for r in rows:
        f = _fresh(r)
        if not f:
            continue
        prof, prov = r.get("profile") or "(root)", _lane(r)
        model = (r.get("model") or "?").strip() or "?"
        if model not in top:
            model = "other models"
        flows[(prof, prov)] = flows.get((prof, prov), 0) + f
        flows[(prov, model)] = flows.get((prov, model), 0) + f
    names = sorted({n for pair in flows for n in pair})
    return {"nodes": [{"name": n} for n in names],
            "links": [{"source": a, "target": b, "value": v}
                      for (a, b), v in sorted(flows.items(), key=lambda kv: -kv[1])]}
