"""VaR Simulations Digest — reads VaR_Tools_Simulations/var_context_run_latest.json."""
from __future__ import annotations

import json
from pathlib import Path

from collectors import json_to_payload, register

DEFAULT_REPO = Path("C:/Users/bottl/FinancialDevelopment")


@register("var-sim")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    src = repo_path / "VaR_Tools_Simulations" / "var_context_run_latest.json"
    if not src.exists():
        return {
            "summary": [{"label": "source", "value": "missing", "tone": "bad"}],
            "tables": [], "charts": [],
            "notes": [f"{src} not found — run the VaR context mode first."],
            "source": {"repo": str(repo_path), "collector": "var-sim",
                       "note": "var_context_run_latest.json"},
        }
    payload = json_to_payload(json.loads(src.read_text(encoding="utf-8")))
    payload["source"] = {"repo": str(repo_path), "collector": "var-sim",
                         "note": "var_context_run_latest.json"}
    return payload
