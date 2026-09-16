"""Polymarket desk collector — fills, positions, P&L from EventTrading repo.

Updated for new E: drive layout where EventTrading is inside BlackHole monorepo.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from collectors import register, default_findev_repo

# E: drive layout (2026-09): folder renamed "BlackHole Investments" ->
# "BlackHole_Investments". Falls back to the C: EventTrading clone when the
# E: volume is absent.
def _find_poly() -> Path:
    for p in (Path("E:/BlackHole_Investments/BlackHole/Event_Desk"),
              Path("C:/Users/bottl/EventTrading")):
        if (p / "data" / "_hist_parsed.json").is_file():
            return p
    return Path("E:/BlackHole_Investments/BlackHole/Event_Desk")

POLY_REPO = _find_poly()
POLY_FILLS = POLY_REPO / "data" / "fills.json"
HIST_PARSED = POLY_REPO / "data" / "_hist_parsed.json"


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def parse_fills(fills_data):
    """Parse fills.json into open/closed positions."""
    if not fills_data or "fills" not in fills_data:
        return [], []
    
    fills = fills_data["fills"]
    open_positions = [f for f in fills if not f.get("closed")]
    closed_positions = [f for f in fills if f.get("closed")]
    
    return open_positions, closed_positions


def parse_history(hist_data):
    """Parse _hist_parsed.json for historical trades."""
    if not hist_data:
        return []
    
    if isinstance(hist_data, dict):
        trades = []
        for day_data in hist_data.values():
            if isinstance(day_data, list):
                trades.extend(day_data)
        return trades
    
    if isinstance(hist_data, list):
        return hist_data
    
    return []


def compute_pnl(open_positions):
    """Calculate current portfolio value from open positions."""
    total_cost = sum(f.get("cost", 0) for f in open_positions)
    total_value = sum(f.get("value", f.get("cost", 0)) for f in open_positions)
    return total_cost, total_value


def parse_money(s):
    """Parse '+$33.08' / '-$20' / '$19.99' -> float. Returns 0.0 on garbage."""
    if not isinstance(s, str):
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0
    t = s.replace("$", "").replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return 0.0


def compute_wl(closed_positions, history_trades):
    """Compute win/loss stats from closed positions + history.

    History trades (_hist_parsed.json) use act: Won/Lost/Bought/Deposit
    and value: '+$33.08' / '-$20'. Only Won/Lost are settled results;
    Bought (open) and Deposit are not trades.
    """
    wins = 0
    losses = 0
    total_pnl = 0.0
    settled = 0

    # From closed fills
    for f in closed_positions:
        pnl = f.get("pnl", 0)
        if pnl > 0:
            wins += 1
        else:
            losses += 1
        settled += 1
        total_pnl += pnl

    # From history (already settled)
    for trade in history_trades:
        act = trade.get("act", "")
        if act == "Won":
            wins += 1
            settled += 1
            total_pnl += parse_money(trade.get("value"))
        elif act == "Lost":
            losses += 1
            settled += 1
            total_pnl += parse_money(trade.get("value"))

    total = wins + losses
    win_rate = wins / total if total > 0 else 0

    return {
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_rate": win_rate,
        "settled": settled,
        "total_pnl": total_pnl
    }


def build_cards(positions, limit=10):
    """Build scored cards from positions."""
    cards = []
    for f in positions[:limit]:
        cards.append({
            "symbol": f.get("market", "unknown")[:15],
            "score": 50,
            "lean": "long",
            "event": "position",
            "meta": f"entry ${f.get('entry', 0):.2f} · cost ${f.get('cost', 0):.2f}",
            "thesis": f"Open on {f.get('side', '?')}",
            "evidence": f"Market: {f.get('market', '')}",
            "risk": "",
            "delta": 0
        })
    return cards


@register("polymarket-desk")
def collect(repo_path=None) -> dict:
    """Collect Polymarket trading data."""
    # Load fills and history
    fills_data = load_json(POLY_FILLS)
    hist_data = load_json(HIST_PARSED)
    
    open_positions, closed_positions = parse_fills(fills_data)
    history_trades = parse_history(hist_data)
    
    # Compute stats
    total_cost, total_value = compute_pnl(open_positions)
    wl = compute_wl(closed_positions, history_trades)
    
    # Build cards
    cards = build_cards(open_positions)
    
    # Build positions table
    positions_rows = []
    for f in open_positions:
        positions_rows.append([
            f.get("market", "?")[:20],
            f.get("side", "?"),
            f"${f.get('entry', 0):.2f}",
            f"${f.get('cost', 0):.2f}",
            "open"
        ])
    
    # Build recent history table
    history_rows = []
    for trade in history_trades[-15:]:
        pnl = parse_money(trade.get("value"))
        history_rows.append([
            trade.get("name", "?")[:20],
            trade.get("event", "?")[:20],
            trade.get("act", "?"),
            f"${pnl:+.2f}" if trade.get("act") in ("Won", "Lost") else (trade.get("value") or "")
        ])
    
    return {
        "summary": [
            {"label": "record", "value": f"{wl['wins']}W–{wl['losses']}L"},
            {"label": "win rate", "value": f"{wl['win_rate']*100:.1f}%"},
            {"label": "open positions", "value": str(len(open_positions))},
            {"label": "deployed", "value": f"${total_cost:,.2f}"},
            {"label": "portfolio value", "value": f"${total_value:,.2f}"},
            {"label": "total history trades", "value": str(len(history_trades))},
            {"label": "settled (W+L)", "value": str(wl.get("settled", 0)), "tone": "ok" if wl["wins"] >= wl["losses"] else "bad"},
            {"label": "history pnl", "value": f"${wl['total_pnl']:+,.2f}", "tone": "ok" if wl["total_pnl"] >= 0 else "bad"},
        ],
        "cards": cards,
        "tables": [
            {
                "id": "positions",
                "title": "Open Positions",
                "columns": ["Market", "Side", "Entry", "Cost", "Status"],
                "rows": positions_rows
            },
            {
                "id": "history",
                "title": "Recent History",
                "columns": ["Name", "Event", "Result", "PnL"],
                "rows": history_rows
            }
        ],
        "charts": [],
        "notes": [f"As of {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
        "source": {
            "fills": str(POLY_FILLS),
            "history": str(HIST_PARSED),
            "collector": "polymarket-desk"
        }
    }
