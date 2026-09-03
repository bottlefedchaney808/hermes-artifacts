"""Vol Suite Dashboard — vol_suite_result.json + latest orchestrator_output runs."""
from __future__ import annotations

import json
from pathlib import Path

from collectors import json_to_payload, register

DEFAULT_REPO = Path("C:/Users/bottl/FinancialDevelopment")


@register("vol-suite")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    notes, cards, tables = [], [], []
    result = repo_path / "Vol_Suite" / "vol_suite_result.json"
    if result.exists():
        payload = json_to_payload(json.loads(result.read_text(encoding="utf-8")))
        cards += payload["summary"]
        tables += payload["tables"]
    else:
        notes.append(f"{result} not found — run Vol_Suite first.")
    runs_dir = repo_path / "orchestrator_output"
    if runs_dir.exists():
        runs = sorted(p.name for p in runs_dir.iterdir() if p.is_dir())
        if runs:
            cards.insert(0, {"label": "latest unified run", "value": runs[-1]})
        tables.append({"id": "runs", "title": "Recent unified runs",
                       "columns": ["run"], "rows": [[r] for r in runs[-10:]]})
    return {"summary": cards[:8], "tables": tables, "charts": [], "notes": notes,
            "source": {"repo": str(repo_path), "collector": "vol-suite",
                       "note": "vol_suite_result.json + orchestrator_output/"}}
