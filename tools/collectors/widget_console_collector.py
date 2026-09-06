"""Widget Console — live catalog snapshot + API health for the widget-console board."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from collectors import register, default_findev_repo

DEFAULT_REPO = default_findev_repo()
API = "http://127.0.0.1:8787"


@register("widget-console")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    notes, cards, tables = [], [], []
    widgets: list[dict] = []
    try:
        with urllib.request.urlopen(API + "/api/widgets/catalog", timeout=5) as r:
            payload = json.loads(r.read().decode())
        widgets = payload.get("widgets") or payload if isinstance(payload, list) else payload.get("widgets", [])
        cards.append({"label": "widget API", "value": f"UP @ {API}"})
    except Exception as e:
        notes.append(f"dashboard widget API not reachable at {API} ({e.__class__.__name__}). "
                     "Start it with dashboard.sh, then refresh this board. The console UI will "
                     "retry the catalog live when you open it.")

    if widgets:
        cards.insert(0, {"label": "widgets in registry", "value": str(len(widgets))})
        suites = sorted({w.get("suite", "?") for w in widgets})
        cats = sorted({w.get("category", "?") for w in widgets})
        cards.append({"label": "suites", "value": ", ".join(suites)})
        cards.append({"label": "categories", "value": f"{len(cats)}"})

    rows = []
    for w in sorted(widgets, key=lambda x: (x.get("suite", ""), x.get("slug", ""))):
        inputs = w.get("inputs") or {}
        inp_bits = [k for k in ("ticker", "expiry", "basket") if inputs.get(k)]
        rows.append([w.get("name", "?"), w.get("slug", "?"), w.get("suite", ""),
                     w.get("category", ""), ", ".join(inp_bits) or "-"])
    tables.append({"id": "catalog", "title": f"Widget catalog ({len(rows)}) — snapshot at refresh; console re-fetches live",
                   "columns": ["name", "slug", "suite", "category", "inputs"], "rows": rows})

    return {"summary": cards[:8], "tables": tables, "charts": [], "notes": notes,
            "source": {"repo": str(repo_path), "collector": "widget-console",
                       "note": f"live catalog from {API}/api/widgets/catalog"}}
