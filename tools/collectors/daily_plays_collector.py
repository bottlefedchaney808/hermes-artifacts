"""Daily Plays — full market scan interpreted into scored cards with history."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from collectors import register, default_findev_repo

DEFAULT_REPO = default_findev_repo()


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_history(artifact_dir: Path, data: dict) -> Path:
    """Save scan to history directory."""
    history_dir = artifact_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc)
    fname = f"{ts.strftime('%Y%m%d_%H%M%S')}.json"
    path = history_dir / fname
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return path


def load_history(artifact_dir: Path, max_entries=50) -> list[dict]:
    """Load history entries, newest first."""
    history_dir = artifact_dir / "history"
    if not history_dir.exists():
        return []
    entries = []
    for f in sorted(history_dir.glob("*.json"), reverse=True):
        try:
            data = load_json(f)
            if data:
                data["_filename"] = f.name
                entries.append(data)
        except Exception:
            pass
        if len(entries) >= max_entries:
            break
    return entries


def get_sentiment_data(repo: Path) -> dict:
    """Get latest sentiment scanner data."""
    # Try sentiment-scanner exports
    src = repo / "sentiment-scanner/data/exports" / "highlighted_ticker_packs/latest_manifest.json"
    data = load_json(src)
    if data:
        return data
    
    # Try trading journal x_buzz
    x_buzz_dir = repo / "trading_journal" / "x_buzz"
    if x_buzz_dir.exists():
        for f in sorted(x_buzz_dir.glob("*.md"), reverse=True):
            if f.name == "LATEST_power-hour.md" or f.name.startswith("2026"):
                return {"type": "x_buzz", "file": str(f), "content": f.read_text(encoding="utf-8")[:5000]}
    
    return {}


def build_cards_from_sentiment(sentiment_data: dict) -> list[dict]:
    """Build scored cards from sentiment data."""
    cards = []
    
    if isinstance(sentiment_data, dict) and "packs" in sentiment_data:
        for pack in sentiment_data["packs"][:10]:
            name = pack.get("name", "UNKNOWN")
            sentiment = pack.get("sentiment", 0)
            cards.append({
                "symbol": name,
                "score": 50 + int(sentiment * 10),
                "lean": "long" if sentiment >= 0 else "short",
                "event": "sentiment scan",
                "meta": name,
                "thesis": pack.get("summary", "")[:200],
                "evidence": pack.get("sources", "")[:200],
                "risk": pack.get("risks", "")[:200],
                "delta": sentiment
            })
    
    return cards


@register("daily-plays")
def collect(repo_path: Path = DEFAULT_REPO, artifact_dir: Path | None = None) -> dict:
    """Collect full market scan data and build scored cards with history."""
    sentiment_data = get_sentiment_data(repo_path)
    cards = build_cards_from_sentiment(sentiment_data)
    
    # Save to history — repo-relative (collector lives in tools/collectors/).
    if artifact_dir is None:
        artifact_dir = Path(__file__).resolve().parents[2] / "artifacts" / "daily-plays"
    
    scan_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cards": cards,
        "sources": list(sentiment_data.keys()) if sentiment_data else []
    }
    save_history(artifact_dir, scan_data)
    
    history = load_history(artifact_dir)
    
    return {
        "summary": [
            {"label": "cards", "value": str(len(cards))},
            {"label": "history scans", "value": str(len(history))},
            {"label": "last updated", "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
        ],
        "cards": cards,
        "history": history,
        "source": {
            "repo": str(repo_path),
            "collector": "daily-plays",
            "note": "full market scan with history"
        }
    }
