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

import os
HERMES_ROOT = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))


_COLS = ["session_id","model","billing_provider","billing_base_url","billing_mode",
         "task","api_call_count","input_tokens","output_tokens","cache_read_tokens",
         "cache_write_tokens","reasoning_tokens","estimated_cost_usd","actual_cost_usd",
         "cost_status","cost_source","first_seen","last_seen"]


def _fmt(n):
    n = float(n or 0)
    for suf, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= div:
            return f"{n/div:.2f}{suf}"
    return str(int(round(n)))


@register("model-usage")
def collect(repo_path=None) -> dict:
    root = Path(repo_path) if repo_path else HERMES_ROOT
    rows = _read_all(root)
    dbs = _dbs(root)

    if not rows:
        return {"summary": [], "tables": [], "charts": [],
                "notes": [f"No session_model_usage rows found under {root}."],
                "source": {"note": f"scanned {len(dbs)} db(s)"}, "viz": {}}

    agg = _aggregate(rows)
    ts = _timeseries(rows)
    sankey = _sankey(rows)

    fresh = sum(_fresh(r) for r in rows)
    cached = sum(_cached(r) for r in rows)
    reasoning = sum(_reasoning(r) for r in rows)
    calls = sum(_calls(r) for r in rows)
    cost = sum(_cost(r) for r in rows)
    local_fresh = sum(_fresh(r) for r in rows if _lane(r) == "local")
    cloud_fresh = fresh - local_fresh
    priced = sum(_fresh(r) for r in rows if _cost(r) > 0)

    summary = [
        {"label": "Fresh tokens", "value": _fmt(fresh)},
        {"label": "Cached reads", "value": _fmt(cached)},
        {"label": "API calls", "value": f"{calls:,}"},
        {"label": "Est. cost (partial)", "value": f"${cost:,.2f}", "tone": "accent"},
        {"label": "Local share",
         "value": f"{(100.0*local_fresh/fresh if fresh else 0):.0f}%",
         "tone": "ok" if local_fresh else None},
        {"label": "Lanes", "value": str(len(agg["by_provider"]))},
    ]

    def _tbl(title, items, label):
        return {"title": title,
                "columns": [label, "lane", "fresh", "cached", "calls", "est_cost_usd"],
                "rows": [[i["key"], i["lane"], _fmt(i["fresh"]), _fmt(i["cached"]),
                          f"{i['calls']:,}", f"${i['cost_usd']:,.4f}"] for i in items]}

    tables = [
        _tbl("Usage by model", agg["by_model"], "model"),
        _tbl("Usage by profile", agg["by_profile"], "profile"),
        _tbl("Usage by provider / lane", agg["by_provider"], "provider"),
    ]

    # Compact rows so the browser can re-aggregate under cross-filtering.
    compact = [[r.get("profile") or "(root)", _lane(r), (r.get("model") or "?").strip() or "?",
                (r.get("task") or "").strip() or "main", _fresh(r), _cached(r),
                _day(r.get("last_seen"))] for r in rows]

    viz = {
        "schema": ["profile", "lane", "model", "task", "fresh", "cached", "day"],
        "rows": compact,
        "palette": ["#38bdf8", "#f472b6", "#4ade80", "#facc15", "#a78bfa",
                    "#22d3ee", "#fb923c", "#f87171", "#2dd4bf", "#c084fc"],
        "by_provider": agg["by_provider"],
        "by_model": agg["by_model"],
        "by_profile": agg["by_profile"],
        "by_task": agg["by_task"],
        "timeseries": ts,
        "sankey": sankey,
        "totals": {"fresh": fresh, "cached": cached, "reasoning": reasoning,
                   "calls": calls, "cost_usd": round(cost, 4),
                   "local_fresh": local_fresh, "cloud_fresh": cloud_fresh,
                   "profiles": len(agg["by_profile"]), "models": len(agg["by_model"])},
    }

    notes = [
        f"Scanned {len(dbs)} state.db file(s) under {root}; {len(rows)} usage rows.",
        "Primary metric is FRESH tokens (input+output). Cached reads are tracked "
        "separately because they dwarf fresh usage and would flatten every chart.",
        f"Cost is partial — only {(100.0*priced/fresh if fresh else 0):.0f}% of fresh tokens "
        "came from priced lanes (zai and local report $0).",
        "Daily buckets use date(last_seen) of per-session aggregate rows — an activity "
        "view, not exact per-call timestamps.",
    ]

    return {"summary": summary, "tables": tables, "charts": [], "notes": notes,
            "source": {"note": f"{len(rows)} rows across {len(dbs)} profile db(s)"},
            "viz": viz}


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
