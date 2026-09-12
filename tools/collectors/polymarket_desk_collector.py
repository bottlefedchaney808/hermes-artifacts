"""Polymarket desk board — W/L record, equity curve, entry/sleeve breakdowns.

Source of truth: EventTrading/data/fills.json (every clip ever logged: cost +
entry price). Realized P&L is joined from data/_hist_parsed.json (the Polymarket
history export) via side-name containment; trades that don't join are reported
honestly as 'open' or 'unsettled', never guessed.

collect(repo_path) treats repo_path as the EventTrading repo root (manifest
supplies it; --repo overrides). Read-only, stdlib only. Returns schema-v1 with
charts: [] — all visuals live in the template's custom ECharts layer reading viz.trades.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from collectors import register

REPO = Path("C:/Users/bottl/EventTrading")


def _load(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _toks(s: str) -> set:
    s = re.sub(r"\(reg\.? time\)", "", (s or "").lower())
    return set(re.findall(r"[a-z0-9]+", s)) - {"vs", "the", "of"}


def _age_hours(when: str):
    m = re.match(r"(\d+)(h|d) ago", when or "")
    if not m:
        return None
    n = int(m.group(1))
    return float(n * (24 if m.group(2) == "d" else 1))


def _money(v):
    try:
        return round(float(str(v).replace("$", "").replace(",", "")), 2)
    except Exception:
        return None


def _category(market: str, side: str = "") -> str:
    m = (market or "").lower() + " " + (side or "").lower()
    for key, lab in [
        ("nfl", "NFL"), ("mlb", "MLB"), ("npb", "NPB"), ("kbo", "KBO"),
        ("wta", "WTA/ITF"), ("atp", "ATP/Challenger"), ("ufc", "UFC/MMA"),
        ("emmy", "Emmys"), ("fed", "Fed/FOMC"), ("talent", "AGT/Culture"),
    ]:
        if key in m:
            return lab
    if any(t in m for t in ["fc ", "cf ", "united", "city fc", "real ", "baystars",
                            "hawks", "lions", "giants", "wiz", "tigers", "carp"]):
        return "Soccer/Club"
    if any(t in m for t in [" vs. ", " vs "]):
        return "Other Sports"
    return "Events"


def _join_settled(fills, settled):
    """Attach realized outcome/P&L from the history export onto CLOSED fills via
    side-name containment (longest name first), cost as tiebreaker. Open fills are
    never candidates — they can't have a settlement row."""
    order = sorted(settled, key=lambda y: -len(y.get("name", "")))
    used_fill = set()
    out = {}  # id(fill) -> settled row
    for y in order:
        nt = _toks(y["name"])
        if not nt:
            continue
        best_i, best_score = None, 0.0
        cost_y = _money(re.sub(r"[^0-9.\-]", "", (y.get("value") or "").replace("+", ""))) \
            if y["act"] == "Lost" else None
        for i, x in enumerate(fills):
            if not x.get("closed"):  # open positions never join a settlement row
                continue
            if i in used_fill:
                continue
            st = _toks(x.get("side", "")) | _toks(x.get("market", ""))
            hit = len(nt & st) / max(1, len(nt))
            # require the side name to be a real subset of fill tokens (containment),
            # not just overlap with an unrelated market string
            if hit < 0.5:
                continue
            score = hit + (0.2 if cost_y is not None and abs((x.get("cost") or 0) - cost_y) < 1 else 0)
            if score > best_score:
                best_i, best_score = i, score
        if best_i is not None:
            used_fill.add(best_i)
            out[best_i] = y
    return out


@register("polymarket-desk")
def collect(repo_path=None) -> dict:
    root = Path(repo_path) if repo_path else REPO
    fills_doc = _load(root / "data" / "fills.json") or {}
    hist = _load(root / "data" / "_hist_parsed.json") or []

    fills = list(fills_doc.get("fills", []))  # newest-first in file
    settled = [x for x in hist if x.get("act") in ("Won", "Lost")]
    joined = _join_settled(fills, settled)

    trades = []
    for orig_i, x in reversed(list(enumerate(fills))):  # oldest first; orig_i keys `joined`
        cost = round(float(x.get("cost") or 0), 2)
        entry = x.get("entry")
        y = joined.get(orig_i)
        outcome, pnl = "open", None
        when_h = _age_hours(x.get("when")) or (None if not y else _age_hours(y["when"]))
        # fills.json `closed` flag is authoritative for open/closed; history only supplies P&L.
        if x.get("closed") and y is not None:
            outcome = "won" if y["act"] == "Won" else "lost"
            v = _money((y.get("value") or "").replace("+", ""))
            pnl = round(v, 2) if v is not None else (-cost if outcome == "lost" else cost * (1 / max(entry, 0.01) - 1) if entry else None)
        elif x.get("closed"):
            outcome = "unsettled"
        trades.append({
            "market": x.get("market", "?"),
            "side": x.get("side", ""),
            "cost": cost,
            "entry": round(float(entry), 3) if entry else None,
            "outcome": outcome,          # won | lost | open | unsettled
            "pnl": pnl,                  # realized $ (won: +net, lost: -cost); null otherwise
            "cat": _category(x.get("market", ""), x.get("side", "")),
            "sleeve": x.get("sleeve") or "",
            "age_h": when_h,              # hours before export snapshot; None = unknown
        })

    won = [t for t in trades if t["outcome"] == "won"]
    lost = [t for t in trades if t["outcome"] == "lost"]
    open_t = [t for t in trades if t["outcome"] == "open"]
    unsettled = [t for t in trades if t["outcome"] == "unsettled"]

    closed_pnl = sum(t["pnl"] or 0 for t in won + lost)
    deployed = sum(t["cost"] for t in trades)
    open_exposure = sum(t["cost"] for t in open_t)
    avg_entry = round(sum(t["entry"] for t in trades if t["entry"]) / max(1, len([t for t in trades if t["entry"]])), 3)

    # current streak (most recent settled first)
    streak_n, streak_dir = 0, ""
    for t in reversed(trades):
        if t["outcome"] not in ("won", "lost"):
            continue
        d = "W" if t["outcome"] == "won" else "L"
        if streak_dir and d != streak_dir:
            break
        streak_dir, streak_n = d, streak_n + 1

    # equity curve: cumulative realized P&L in chronological order; deposits as markers
    eq_x, eq_y, dep_marks = [], 0.0, []
    for t in trades:
        if t["pnl"] is not None:
            eq_y += t["pnl"]
        label = f"{t['market'][:26]}" + ("…" if len(t["market"]) > 26 else "")
        eq_x.append(round(eq_y, 2))
    # deposits from history export (best-effort)
    for x in hist:
        if x.get("act") == "Deposit" and _money(x.get("name")):
            dep_marks.append(_money(x["name"]))

    summary = [
        {"label": "Record", "value": f"{len(won)}W–{len(lost)}L"},
        {"label": "Win rate (settled)", "value": f"{100*len(won)/max(1,len(won)+len(lost)):.1f}%"},
        {"label": "Closed P&L", "value": f"${closed_pnl:,.2f}", "tone": "ok" if closed_pnl >= 0 else "bad"},
        {"label": "Clips logged", "value": str(len(trades)), "sub": f"${deployed:,.0f} deployed all-time"},
        {"label": "Open exposure", "value": f"{len(open_t)} pos / ${open_exposure:,.2f}"},
        {"label": "Avg entry", "value": f"{avg_entry*100:.0f}¢"},
        {"label": "Streak (current)", "value": (streak_dir + str(streak_n)) if streak_dir else "—"},
    ]

    tables = [
        {
            "title": "Open positions",
            "columns": ["Market", "Side", "Entry", "Cost"],
            "rows": [[t["market"][:48], t["side"], f"{int(t['entry']*100)}¢" if t["entry"] else "?",
                     f"${t['cost']:.2f}"] for t in reversed(open_t)],
        },
        {
            "title": "Latest settled trades (realized P&L)",
            "columns": ["Market", "Side", "Entry", "Cost", "P&L"],
            "rows": [[t["market"][:48], t["side"], f"{int(t['entry']*100)}¢" if t["entry"] else "?",
                     f"${t['cost']:.2f}", (f"+${t['pnl']:,.2f}" if (t['pnl'] or 0) >= 0 else f"-${abs(t['pnl']):,.2f}")]
                    for t in list(reversed([t for t in trades if t["outcome"] in ("won", "lost")]))[:15]],
        },
    ]

    notes = [
        f"fills.json is the all-time clip log ({len(trades)} clips). Realized P&L joins from the Polymarket history export; {len(unsettled)} closed fills have no matching settlement row yet (P&L not reconciled) and are shown as 'unsettled', never guessed.",
        f"Account SoT at last verification: cash ${fills_doc.get('cash_last_verified')}, portfolio ${fills_doc.get('portfolio_last_verified')} ({len(open_t)} open).",
    ]

    return {
        "summary": summary,
        "tables": tables,
        "charts": [],  # custom ECharts layer in template reads viz.trades
        "notes": notes,
        "source": {"note": f"EventTrading fills.json + _hist_parsed.json @ {root}"},
        "viz": {
            "trades": trades,
            "deposits": dep_marks or [],
            "totals": {
                "won": len(won), "lost": len(lost), "open": len(open_t),
                "unsettled": len(unsettled), "closed_pnl": round(closed_pnl, 2),
                "deployed": round(deployed, 2), "open_exposure": round(open_exposure, 2),
            },
        },
    }
