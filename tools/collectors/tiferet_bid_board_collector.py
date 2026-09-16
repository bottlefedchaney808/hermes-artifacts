"""Tiferet Bid Board — pipeline, pricing, and bid calendar from Copper data."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from collectors import register, default_findev_repo

DEFAULT_REPO = default_findev_repo()


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _find_tiferet_dirs(repo_path: Path):
    """Candidate locations for price_history.json / final_db.json."""
    cands = [repo_path / "Tiferet", repo_path, Path(os.environ.get("TIFERET_DIR", "")),
             Path("C:/Users/bottl/Tiferet"),
             Path("C:/Users/bottl/ConstructionDevelopment/pygtp-construction-budget/db")]
    seen = []
    for c in cands:
        if c and c.is_dir() and c not in seen:
            seen.append(c)
    return seen


@register("tiferet-bid-board")
def collect(repo_path=None) -> dict:
    """Collect Tiferet bid pipeline data and build dashboard payload."""
    repo_path = Path(repo_path) if repo_path else DEFAULT_REPO
    price_history = None
    final_db = None
    for d in _find_tiferet_dirs(repo_path):
        if price_history is None:
            price_history = load_json(d / "price_history.json")
        if final_db is None:
            final_db = load_json(d / "final_db.json")

    summary = []
    if isinstance(price_history, dict):
        ph = price_history.get("records", price_history) if isinstance(price_history, dict) else price_history
    elif isinstance(price_history, list):
        ph = price_history
    else:
        ph = []

    if ph:
        total_value = sum(p.get("grand_total", 0) or 0 for p in ph)
        summary.append({"label": "combined quoted", "value": f"${total_value:,.0f}"})
        projects = set()
        for p in ph:
            proj = p.get("project_name") or p.get("project") or p.get("name")
            if proj:
                projects.add(proj)
        summary.append({"label": "projects", "value": str(len(projects))})
        summary.append({"label": "proposals", "value": str(len(ph))})
    fd = final_db if isinstance(final_db, list) else []
    summary.append({"label": "final_db records", "value": str(len(fd))})
    summary.append({"label": "updated", "value": datetime.now().strftime("%Y-%m-%d %H:%M")})

    # Funnel from final_db stage data (real db has no stage -> project_type mix)
    funnel = {}
    for entry in fd:
        if isinstance(entry, dict):
            stage = entry.get("stage")
            if stage:
                funnel[stage] = funnel.get(stage, 0) + 1
    if not funnel:
        for p in ph:
            t = p.get("project_type") or "unknown"
            funnel[t] = funnel.get(t, 0) + 1
    funnel_rows = [[s, str(n)] for s, n in sorted(funnel.items(), key=lambda x: -x[1])]

    # Top projects by combined value
    project_values = {}
    for p in ph:
        proj = p.get("project_name") or p.get("project") or p.get("name") or "unknown"
        project_values[proj] = project_values.get(proj, 0) + (p.get("grand_total", 0) or 0)
    top_rows = [[proj, f"${v:,.0f}"] for proj, v in sorted(project_values.items(), key=lambda x: -x[1])[:10]]

    tables = []
    if funnel_rows:
        tables.append({"id": "funnel", "title": "Pipeline Funnel",
                       "columns": ["Stage", "Count"], "rows": funnel_rows})
    if top_rows:
        tables.append({"id": "top-projects", "title": "Top Projects by Combined Value",
                       "columns": ["Project", "Combined Value"], "rows": top_rows})

    out = {
        "summary": summary,
        "tables": tables,
        "charts": [],
        "notes": ["Tiferet bid pipeline data from price_history.json and final_db.json"],
        "source": {
            "repo": str(repo_path),
            "collector": "tiferet-bid-board",
            "note": "price_history.json + final_db.json"
        }
    }

    # Full dashboard payload for the Tiferet Bid Desk template. When sources are
    # absent the template falls back to its embedded snapshot (Sep 3, 2026).
    if ph or fd:
        out["tiferet"] = {
            "meta": {"generated": datetime.now().strftime("%b %d, %Y"),
                     "sources": "price_history.json (%s recs) · final_db.json (%s)" % (len(ph), len(fd))},
            "kpi": {
                "pipeline_total": sum(p.get("grand_total", 0) or 0 for p in ph),
                "sf": sum(p.get("total_sf", 0) or 0 for p in ph),
                "units": sum(p.get("unit_count", 0) or 0 for p in ph),
                "records": len(ph),
                "sf_total_n": sum(1 for p in ph if p.get("total_sf")),
                "projects": len({p.get("project_name") or p.get("project") or p.get("name") for p in ph if p.get("project_name") or p.get("project") or p.get("name")}),
                "final_db": len(fd),
            },
            "funnel": [{"stage": s, "n": n} for s, n in sorted(funnel.items(), key=lambda x: -x[1])],
            "top": [{"name": proj, "n_proposals": 0, "combined_total": v, "max_total": 0}
                    for proj, v in sorted(project_values.items(), key=lambda x: -x[1])[:6]],
        }
    return out
