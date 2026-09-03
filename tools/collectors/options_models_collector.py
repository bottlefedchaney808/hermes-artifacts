"""Options Model Tracker — newest Options_Suite comparison_*.csv (Option-9 output)."""
from __future__ import annotations

import csv
from pathlib import Path

from collectors import register, default_findev_repo

DEFAULT_REPO = default_findev_repo()
SHOW = ("Model", "Price", "Delta", "Gamma", "Vega", "Theta", "Vanna", "Charm", "Sigma")


@register("options-models")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    suite = repo_path / "Options_Suite"
    files = sorted(suite.glob("comparison_*.csv")) if suite.exists() else []
    if not files:
        return {"summary": [{"label": "comparison CSVs", "value": "none", "tone": "bad"}],
                "tables": [], "charts": [],
                "notes": ["No Options_Suite/comparison_*.csv found — run Option 9 "
                          "(Run all models & compare) in the Options Suite CLI."],
                "source": {"repo": str(repo_path), "collector": "options-models",
                           "note": "comparison_*.csv"}}
    src = files[-1]
    with src.open(encoding="utf-8", errors="replace", newline="") as fh:
        rows = list(csv.DictReader(fh))
    market = next((r for r in rows if r.get("Model") == "Market"), None)
    table_rows = []
    for r in rows:
        cells = [(r.get(c) or "").strip()[:14] for c in SHOW]
        if market and r is not market:
            try:
                err = (float(r["Price"]) - float(market["Price"])) / float(market["Price"]) * 100
                cells.append(f"{err:+.2f}%")
            except (ValueError, ZeroDivisionError, KeyError):
                cells.append("")
        elif r is market:
            cells.append("baseline")
        else:
            cells.append("")
        table_rows.append(cells)
    columns = list(SHOW) + (["PriceErr%"] if market else [])
    first = rows[0] if rows else {}
    cards = [
        {"label": "newest run", "value": src.stem.replace("comparison_", "")},
        {"label": "underlying", "value": f"{first.get('Ticker', '?')} "
         f"{first.get('Strike', '?')} {first.get('OptionType', '?')}"},
        {"label": "expiry", "value": first.get("Expiry", "?")},
        {"label": "models compared", "value": str(len(rows))},
    ]
    return {"summary": cards,
            "tables": [{"id": "models", "title": f"Model comparison — {src.name}",
                        "columns": columns, "rows": table_rows}],
            "charts": [],
            "notes": ([f"Spot {first.get('Spot', '?')}, {first.get('T_years', '?')}y, "
                       f"r={first.get('Rate', '?')}, q={first.get('DivYield', '?')}. "
                       "Older runs: " + ", ".join(f.name for f in files[-4:-1])]
                      if len(files) > 1 else []),
            "source": {"repo": str(repo_path), "collector": "options-models",
                       "note": src.name}}
