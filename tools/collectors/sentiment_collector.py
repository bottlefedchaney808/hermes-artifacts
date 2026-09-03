"""Sentiment Scanner Board — highlighted ticker packs manifest."""
from __future__ import annotations

import json
from pathlib import Path

from collectors import json_to_payload, register, default_findev_repo

DEFAULT_REPO = default_findev_repo()


@register("sentiment")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    src = (repo_path / "sentiment-scanner/data/exports"
                      / "highlighted_ticker_packs/latest_manifest.json")
    if not src.exists():
        return {"summary": [{"label": "manifest", "value": "missing", "tone": "bad"}],
                "tables": [], "charts": [], "notes": [f"{src} not found"],
                "source": {"repo": str(repo_path), "collector": "sentiment",
                           "note": "latest_manifest.json"}}
    payload = json_to_payload(json.loads(src.read_text(encoding="utf-8")))
    payload["source"] = {"repo": str(repo_path), "collector": "sentiment",
                         "note": "latest_manifest.json"}
    return payload
