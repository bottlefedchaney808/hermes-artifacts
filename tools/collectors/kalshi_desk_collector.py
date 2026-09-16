"""Kalshi Trading Desk — bucket clips, perps tape, and account stats."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from collectors import register

def _find_desk() -> Path:
    # 2026-09: E: folder renamed "BlackHole Investments" -> "BlackHole_Investments".
    for p in (Path("E:/BlackHole_Investments/BlackHole/Event_Desk"),
              Path("C:/Users/bottl/BlackHole_Investments/BlackHole/Event_Desk")):
        if p.exists():
            return p
    return Path("E:/BlackHole_Investments/BlackHole/Event_Desk")

KALSHI_DESK = _find_desk()
BUCKET_LOG = KALSHI_DESK / "kalshi_btc15m" / "data" / "bucket_clip_log.jsonl"
PERPS_TAPE = KALSHI_DESK / "kalshi_btc15m" / "data" / "perps_tape.jsonl"
POLY_FILLS = KALSHI_DESK / "data" / "fills.json"


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def load_jsonl(path, limit=None):
    """Load JSONL file, return list of dicts. limit = max lines from end."""
    if not path.exists():
        return []
    lines = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit:
        lines = lines[-limit:]
    return lines


def parse_bucket_log(entries):
    """Parse bucket clip log into fills/settlements/unfilled."""
    fills = []
    settlements = []
    unfilled = []
    
    for e in entries:
        if e.get("type") == "fill":
            fills.append(e)
        elif e.get("type") == "settle":
            settlements.append(e)
        elif e.get("type") == "unfilled":
            unfilled.append(e)
    
    return fills, settlements, unfilled


def compute_wl_stats(settlements):
    """Compute win/loss stats from settlements."""
    wins = [s for s in settlements if s.get("result") == "yes"]
    losses = [s for s in settlements if s.get("result") == "no"]
    
    total_pnl = sum(s.get("pnl_usd", 0) for s in settlements)
    win_pnl = sum(s.get("pnl_usd", 0) for s in wins)
    loss_pnl = sum(s.get("pnl_usd", 0) for s in losses)
    
    # Stats by series
    series_stats = {}
    for s in settlements:
        series = s.get("series", "unknown")
        if series not in series_stats:
            series_stats[series] = {"wins": 0, "losses": 0, "pnl": 0}
        if s.get("result") == "yes":
            series_stats[series]["wins"] += 1
        else:
            series_stats[series]["losses"] += 1
        series_stats[series]["pnl"] += s.get("pnl_usd", 0)
    
    return {
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(settlements) if settlements else 0,
        "total_pnl": total_pnl,
        "win_pnl": win_pnl,
        "loss_pnl": loss_pnl,
        "avg_win": win_pnl / len(wins) if wins else 0,
        "avg_loss": loss_pnl / len(losses) if losses else 0,
        "series_stats": series_stats
    }


def build_recent_cards(settlements, fills, n=10):
    """Build scored cards from recent activity."""
    cards = []
    recent = settlements[-n:]
    
    for s in recent:
        pnl = s.get("pnl_usd", 0)
        score = 50 + int(pnl)
        cards.append({
            "symbol": s.get("series", "unknown"),
            "score": score,
            "lean": "long" if pnl > 0 else "short",
            "event": "settlement",
            "meta": f"{s.get('result', '?')} · ${pnl:+.2f}",
            "thesis": f"Bucket clip settled {s.get('result', '?')}",
            "evidence": f"Ticker: {s.get('ticker', '')}",
            "risk": "",
            "delta": pnl
        })
    
    # Add open fills as cards
    for f in fills[-5:]:
        if not f.get("closed"):
            cards.append({
                "symbol": f.get("market", "unknown")[:12],
                "score": 50,
                "lean": "long",
                "event": "open position",
                "meta": f"entry ${f.get('entry', 0):.2f} · cost ${f.get('cost', 0):.2f}",
                "thesis": f"Open on {f.get('side', '?')}",
                "evidence": f"Market: {f.get('market', '')}",
                "risk": "",
                "delta": 0
            })
    
    return cards[:n]


def parse_perps_tape(entries, limit=20):
    """Latest snapshot per ticker: last price/OI + last known 24h volume.

    The tape writer changed schema mid-file (recent lines dropped
    volume_24h_notional and never had a 'type' field), so scan every entry:
    keep the newest entry per ticker for price/OI, and the newest entry that
    carries volume for the 24h figure.
    """
    latest = {}
    vol_latest = {}
    oi_latest = {}
    for e in entries:
        ticker = e.get("ticker", "")
        if not ticker.endswith("PERP"):
            continue
        latest[ticker] = e
        if e.get("volume_24h_notional"):
            vol_latest[ticker] = e
        if float(e.get("open_interest") or 0) > 0:
            oi_latest[ticker] = e

    top = []
    for ticker, e in latest.items():
        ve = vol_latest.get(ticker, {})
        oe = oi_latest.get(ticker, {})
        top.append({
            "ticker": ticker,
            "price": float(e.get("price", 0) or 0),
            "oi": float(oe.get("open_interest", 0) or 0),
            "vol_24h": float(ve.get("volume_24h_notional", 0) or 0),
            "leverage": float(e.get("leverage_estimate", 0) or 0),
            "ts": e.get("ts", ""),
        })

    top.sort(key=lambda x: -x["vol_24h"])
    return top[:limit]


@register("kalshi-desk")
def collect(repo_path=None) -> dict:
    """Collect Kalshi trading data."""
    # Load bucket clip log
    bucket_entries = load_jsonl(BUCKET_LOG)
    fills, settlements, unfilled = parse_bucket_log(bucket_entries)
    
    # Compute stats
    wl = compute_wl_stats(settlements)
    
    # Load full perps tape — volume fields appear only in some entries,
    # so a tail slice misses them; full scan is one pass over ~580k lines.
    perps_entries = load_jsonl(PERPS_TAPE)
    perps_top = parse_perps_tape(perps_entries)
    
    # Build cards from recent activity
    cards = build_recent_cards(settlements, fills)
    
    # Build recent activity table
    recent_rows = []
    for s in settlements[-15:]:
        recent_rows.append([
            s.get("ts", "")[-8:],  # Just time portion
            s.get("series", "?"),
            s.get("result", "?"),
            f"${s.get('pnl_usd', 0):+.2f}"
        ])
    
    # Series stats table
    series_rows = []
    for series, stats in sorted(wl["series_stats"].items(), key=lambda x: -x[1]["pnl"]):
        wr = stats["wins"] / (stats["wins"] + stats["losses"]) * 100
        series_rows.append([
            series,
            f"{stats['wins']}/{stats['wins']+stats['losses']}",
            f"{wr:.0f}%",
            f"${stats['pnl']:+.2f}"
        ])
    
    # Perps table
    perps_rows = []
    for p in perps_top[:10]:
        perps_rows.append([
            p["ticker"].replace("KX", "").replace("PERP", ""),
            f"${p['price']:,.2f}",
            f"{p['oi']:,.0f}",
            f"${p['vol_24h']:,.0f}"
        ])
    
    tables = [
        {
            "id": "recent",
            "title": "Recent Settlements",
            "columns": ["Time", "Series", "Result", "PnL"],
            "rows": recent_rows
        },
        {
            "id": "series-stats",
            "title": "Stats by Series",
            "columns": ["Series", "W/L", "Win Rate", "PnL"],
            "rows": series_rows
        },
        {
            "id": "perps-prices",
            "title": "Perps Prices (by 24h Volume)",
            "columns": ["Ticker", "Price", "Open Interest", "24h Volume"],
            "rows": perps_rows
        }
    ]
    
    return {
        "summary": [
            {"label": "record", "value": f"{wl['wins']}W–{wl['losses']}L"},
            {"label": "win rate", "value": f"{wl['win_rate']*100:.1f}%"},
            {"label": "total pnl", "value": f"${wl['total_pnl']:+.2f}"},
            {"label": "avg win", "value": f"${wl['avg_win']:+.2f}"},
            {"label": "avg loss", "value": f"${wl['avg_loss']:+.2f}"},
            {"label": "open positions", "value": str(len([f for f in fills if not f.get('closed')]))},
            {"label": "settled", "value": str(len(settlements))},
        ],
        "cards": cards,
        "tables": tables,
        "charts": [],
        "notes": [
            f"Data from {BUCKET_LOG.name} and {PERPS_TAPE.name}",
            f"As of {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        ],
        "source": {
            "bucket_log": str(BUCKET_LOG),
            "perps_tape": str(PERPS_TAPE),
            "collector": "kalshi-desk"
        }
    }
