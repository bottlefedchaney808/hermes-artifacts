#!/usr/bin/env python3
"""Rebuild Tiferet Bid Desk.html from Copper Gmail + company DB.

Live Copper cards (Jason saved filter) persist from the last confirmed
snapshot at jason_live.json — they are NOT scraped each tick (no Copper API).
History / velocity / stages rebuild from notifier@copper.com mail assigned
to jason@tiferetfinishes.com.

Exit 0 on success (prints a one-line status). Exit 1 on failure (prints error).
"""
from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

ART = Path(r"C:\Users\bottl\hermes-artifacts")
GMAIL_CLI = Path(
    r"C:\Users\bottl\AppData\Local\hermes\skills\productivity\google-workspace\scripts\google_api.py"
)
PY = Path(r"C:\Users\bottl\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe")
DB_DIR = Path(r"C:\Users\bottl\ConstructionDevelopment\pygtp-construction-budget\db")
TEMPLATE = ART / "bid_desk_template.html"
OUT_HTML = ART / "Tiferet Bid Desk.html"
LIVE_SNAP = ART / "jason_live.json"
PAYLOAD_PATH = ART / "dashboard_payload_v2.json"

MONTHS = {
    m: i + 1
    for i, m in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]
    )
}
STAGE_PALETTE = {
    "New": "#e8e3d8",
    "Assigned Bids": "#7fb4e8",
    "Bid Invitations": "#7fb4e8",
    "Takeoff": "#5ec8a8",
    "Madi Review": "#c9b458",
    "ROBIN APPROVAL": "#c9b458",
    "Approval Pending": "#c9b458",
    "Approved": "#8fd674",
    "READY TO SUBMIT": "#f0a24a",
    "Submitted": "#f0742a",
    "SUBMITTED": "#f0742a",
    "REBIDS": "#e85f8a",
    "Level 3 (Exec Level of Traction)": "#b48fe8",
    "Level 1 (No Traction)": "#6b7280",
    "Not Bidding": "#6b7280",
    "Lost": "#374151",
}


def clean(n: str) -> str:
    n = unescape(n or "")
    n = re.sub(r"\s*\(Copy\)", "", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def classify(subject: str) -> str:
    sl = (subject or "").lower()
    if "new pipeline record" in sl:
        return "new_opportunity"
    if "new task" in sl or "task due" in sl:
        return "task"
    if "meeting" in sl and "due today" in sl:
        return "digest"
    if "moved forward to" in sl:
        return "stage_move"
    if "marked" in sl:
        return "closed"
    if "new company" in sl or "new person" in sl:
        return "contact"
    if "note added" in sl:
        return "note"
    return "other"


def fetch_copper_emails(max_n: int = 500) -> list[dict]:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    r = subprocess.run(
        [str(PY), str(GMAIL_CLI), "gmail", "search", "from:notifier@copper.com", "--max", str(max_n)],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"gmail search failed rc={r.returncode}: {(r.stderr or '')[:400]}")
    raw = r.stdout or ""
    if not raw.strip() or raw.strip() == "No messages found.":
        return []
    return json.loads(raw, strict=False)


def parse_events(raw: list[dict]) -> list[dict]:
    recs = []
    for m in raw:
        try:
            d = parsedate_to_datetime(m["date"])
        except Exception:
            continue
        recs.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "iso": d.isoformat(),
                "kind": classify(m.get("subject", "")),
                "subject": m.get("subject", ""),
                "snippet": m.get("snippet", ""),
            }
        )
    recs.sort(key=lambda r: r["iso"])
    return recs


def build_timeline(recs: list[dict]) -> dict[str, list[tuple[str, str]]]:
    tl: dict[str, list[tuple[str, str]]] = {}
    for r in recs:
        if r["kind"] != "stage_move":
            continue
        s = unescape(r["subject"])
        m = re.match(r"(?:Opportunity|Project) moved forward to ([^:]+): (.+)$", s)
        if not m:
            continue
        stage, name = m.group(1).strip(), clean(m.group(2))
        tl.setdefault(name, []).append((r["iso"], stage))
    for k in tl:
        tl[k].sort()
    return tl


def jason_assignments(recs: list[dict]) -> dict[str, dict]:
    jason: dict[str, dict] = {}
    for r in recs:
        sl = unescape(r["snippet"] + " " + r["subject"])
        if "assigned to you" not in sl.lower() or "Pipeline Record:" not in sl:
            continue
        nm = re.search(r"Pipeline Record: (.+?) has been assigned", sl)
        dd = re.search(r"due on:?\s*([A-Z][a-z]+)\s+(\d{1,2})", sl)
        if not nm:
            continue
        name = clean(nm.group(1))
        rec = jason.setdefault(name, {"name": name, "dues": set()})
        if dd and dd.group(1) in MONTHS:
            rec["dues"].add(f"{r['date'][:4]}-{MONTHS[dd.group(1)]:02d}-{int(dd.group(2)):02d}")
    return jason


def canon(n: str, pool) -> str | None:
    if n in pool:
        return n
    nl = n.lower()
    for c in pool:
        if nl[:14] == c.lower()[:14] or nl in c.lower() or c.lower() in nl:
            return c
    return None


def is_jason_name(n: str, jason_names: set[str]) -> bool:
    nl = n.lower().rstrip(".")
    for j in jason_names:
        jl = j.lower().rstrip(".")
        if nl[:14] == jl[:14] or nl in jl or jl in nl:
            return True
    return False


def load_live() -> list[dict]:
    if not LIVE_SNAP.exists():
        return []
    data = json.loads(LIVE_SNAP.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "jason_live" in data:
        return data["jason_live"]
    if isinstance(data, list):
        return data
    return []


def company_db() -> dict:
    ph = json.loads((DB_DIR / "price_history.json").read_text(encoding="utf-8"))
    fdb = json.loads((DB_DIR / "final_db.json").read_text(encoding="utf-8"))
    both = [r for r in ph if r.get("total_sf") and r.get("grand_total")]
    per_sf = sorted(r["grand_total"] / r["total_sf"] for r in both)
    buckets: Counter = Counter()
    for v in per_sf:
        buckets[
            "0–3" if v < 3 else "3–6" if v < 6 else "6–10" if v < 10
            else "10–20" if v < 20 else "20–50" if v < 50 else "50+"
        ] += 1
    uh = {"$3-4k": 0, "$4-5k": 0, "$5-6k": 0, "$6-7k": 0, "$7k+": 0}
    pu: list[float] = []
    for r in ph:
        if r.get("unit_count") and r.get("grand_total"):
            p = r["grand_total"] / r["unit_count"]
            if 500 <= p <= 50000:
                pu.append(p)
                k = (
                    "$3-4k" if p < 4000 else "$4-5k" if p < 5000 else "$5-6k"
                    if p < 6000 else "$6-7k" if p < 7000 else "$7k+"
                )
                uh[k] += 1
    pu.sort()
    by: dict[str, list[float]] = defaultdict(list)
    for r in ph:
        if r.get("grand_total"):
            by[str(r.get("project_name") or "").strip()].append(r["grand_total"])
    top = sorted(
        ((n, len(v), sum(v), max(v)) for n, v in by.items() if n),
        key=lambda x: -x[2],
    )[:6]
    mxb = max(buckets.values()) if buckets else 1
    mxu = max(uh.values()) if uh else 1
    it = [r for r in fdb if (r.get("intumescent_total") or 0) > 0]
    return {
        "kpi": {
            "pipeline_total": int(sum(r["grand_total"] for r in ph if r.get("grand_total"))),
            "sf": int(sum(r["total_sf"] for r in ph if r.get("total_sf"))),
            "units": int(sum(r["unit_count"] for r in ph if r.get("unit_count"))),
            "records": len(ph),
            "sf_total_n": len(both),
            "projects": len(by),
            "final_db": len(fdb),
        },
        "pricing": {
            "n": len(per_sf),
            "per_sf": {
                "n": len(per_sf),
                "min": round(per_sf[0], 2) if per_sf else 0,
                "p25": round(per_sf[len(per_sf) // 4], 2) if per_sf else 0,
                "med": round(statistics.median(per_sf), 2) if per_sf else 0,
                "p75": round(per_sf[len(per_sf) * 3 // 4], 2) if per_sf else 0,
                "p90": round(per_sf[int(len(per_sf) * 0.9)], 2) if per_sf else 0,
                "max": round(per_sf[-1], 2) if per_sf else 0,
            },
            "buckets": dict(buckets),
            "buckets_pct": {k: round(v / mxb * 100) for k, v in buckets.items()},
            "per_unit": {
                "n": len(pu),
                "p25": round(pu[len(pu) // 4]) if pu else 0,
                "med": round(statistics.median(pu)) if pu else 0,
                "p75": round(pu[len(pu) * 3 // 4]) if pu else 0,
            },
            "unit_hist": uh,
            "unit_hist_pct": {k: round(v / mxu * 100) for k, v in uh.items()},
        },
        "top": [
            {"name": n, "n_proposals": c, "combined_total": int(s), "max_total": int(mx)}
            for n, c, s, mx in top
        ],
        "intum": {
            "n_proposals": len(it),
            "combined": int(sum(r.get("intumescent_total") or 0 for r in it)),
            "note": "Stuart & Eureka (9403) R1 + original — only 2 proposals carry intumescent pricing"
            if len(it) == 2
            else f"{len(it)} proposals carry intumescent pricing",
        },
    }


def assigned_to_submit_days(tl: dict, jason_names: set[str]) -> list[int]:
    durs = []
    for n, evs in tl.items():
        if not is_jason_name(n, jason_names):
            continue
        a = next((iso for iso, s in evs if s == "Assigned Bids"), None)
        sub = next((iso for iso, s in evs if s.lower() == "submitted"), None)
        if a and sub:
            d = (datetime.fromisoformat(sub) - datetime.fromisoformat(a)).days
            if d >= 0:
                durs.append(d)
    return sorted(durs)


def speed_hist(days: list[int]) -> dict:
    hist = {f"{lo}-{lo + 4}": sum(1 for x in days if lo <= x <= lo + 4) for lo in range(0, 25, 5)}
    return {
        "med": int(statistics.median(days)) if days else 0,
        "min": min(days) if days else 0,
        "max": max(days) if days else 0,
        "n": len(days),
        "hist": hist,
    }


def funnel(cur: dict[str, str]) -> list[dict]:
    order = [
        "New", "Assigned Bids", "Bid Invitations", "Takeoff", "Madi Review",
        "ROBIN APPROVAL", "Approval Pending", "Approved", "READY TO SUBMIT",
        "Submitted", "SUBMITTED", "REBIDS", "Level 3 (Exec Level of Traction)",
        "Level 1 (No Traction)", "Not Bidding", "Lost",
    ]
    counts = Counter(cur.values())
    return [{"stage": s, "n": counts[s]} for s in order if counts.get(s)]


def build_payload(recs: list[dict], live: list[dict], db: dict, now: datetime) -> dict:
    tl = build_timeline(recs)
    cur = {n: evs[-1][1] for n, evs in tl.items()}
    jason = jason_assignments(recs)
    jason_names = set(jason) | {r["name"] for r in live}

    today = now.strftime("%Y-%m-%d")
    gen = now.strftime("%b %-d, %Y") if os.name != "nt" else now.strftime("%b %#d, %Y")

    hist_rows = []
    seen = {r["name"].lower().rstrip(".") for r in live}
    for n, rec in jason.items():
        c = canon(n, cur)
        k = (c or n).lower().rstrip(".")
        if k in seen:
            continue
        seen.add(k)
        dues = sorted(rec["dues"])
        hist_rows.append(
            {
                "name": c or n,
                "gc": "",
                "bid_due": dues[-1] if dues else "",
                "stage": cur.get(c, "") if c else "",
                "tasks": 0,
                "source": "assigned to Jason (Copper email)",
                "owner": "Jason Chaney",
            }
        )
    hist_rows.sort(key=lambda r: r["bid_due"] or "9999")
    hist_up = [r for r in hist_rows if r["bid_due"] >= today]
    hist_past = [r for r in hist_rows if r["bid_due"] and r["bid_due"] < today]

    new_j: Counter = Counter()
    for r in recs:
        if r["kind"] != "new_opportunity":
            continue
        sl = unescape(r["snippet"] + " " + r["subject"])
        if "assigned to you" in sl.lower() and "Pipeline Record:" in sl:
            new_j[r["date"][:7]] += 1
    sub_j: Counter = Counter()
    ever_sub = 0
    for n, evs in tl.items():
        if not is_jason_name(n, jason_names):
            continue
        subs = [iso for iso, s in evs if s.lower() == "submitted"]
        if subs:
            ever_sub += 1
            sub_j[min(subs)[:7]] += 1

    days = assigned_to_submit_days(tl, jason_names)
    team_n = sum(1 for n in cur if not is_jason_name(n, jason_names))

    months_full = {"2026-05": "May", "2026-06": "Jun", "2026-07": "Jul", "2026-08": "Aug", "2026-09": "Sep"}
    all_new = Counter()
    all_sub = Counter()
    for r in recs:
        if r["kind"] == "new_opportunity":
            all_new[r["date"][:7]] += 1
    for n, evs in tl.items():
        subs = [iso for iso, s in evs if s.lower() == "submitted"]
        if subs:
            all_sub[min(subs)[:7]] += 1
    months = sorted(set(all_new) | set(all_sub))
    nmax = max(all_new.values()) if all_new else 1
    smax = max(all_sub.values()) if all_sub else 1
    velocity_all = [
        {
            "m": months_full.get(m, m),
            "new": all_new.get(m, 0),
            "sub": all_sub.get(m, 0),
            "new_pct": round(all_new.get(m, 0) / nmax * 100),
            "sub_pct": round(all_sub.get(m, 0) / smax * 100),
        }
        for m in months
    ]

    return {
        "meta": {
            "generated": gen,
            "default_owner": "Jason Chaney",
            "sources": "Live Copper snapshot (Jason saved filter) · Copper emails assigned-to-you · price_history.json · final_db.json",
        },
        "jason_live": live,
        "jason_hist_up": hist_up,
        "jason_hist_past": hist_past[-16:],
        "jason_hist_n": len(hist_past) + len(hist_up) + len(live),
        "jason_n_assigned": len(jason),
        "jason_ever_submitted": ever_sub,
        "jason_new_mo": dict(sorted(new_j.items())),
        "jason_sub_mo": dict(sorted(sub_j.items())),
        "team_cal": [],
        "team_n": team_n,
        "all_n": len(cur),
        "kpi_db": db["kpi"],
        "pricing": db["pricing"],
        "top": db["top"],
        "intum": db["intum"],
        "funnel_all": funnel(cur),
        "velocity_all": velocity_all,
        "speed": speed_hist(days),
        "stage_palette": STAGE_PALETTE,
    }


def inject(template: str, payload: dict) -> str:
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    if "__PAYLOAD__" not in template:
        raise RuntimeError("template missing __PAYLOAD__ placeholder")
    return template.replace("__PAYLOAD__", blob)


def main() -> int:
    now = datetime.now(timezone.utc).astimezone()
    try:
        raw = fetch_copper_emails()
        recs = parse_events(raw)
        live = load_live()
        if not live:
            # fall back to last payload so a first-run without snapshot doesn't blank My Bids
            if PAYLOAD_PATH.exists():
                live = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8")).get("jason_live") or []
        db = company_db()
        payload = build_payload(recs, live, db, now)
        tpl = TEMPLATE.read_text(encoding="utf-8")
        html = inject(tpl, payload)
        OUT_HTML.write_text(html, encoding="utf-8")
        PAYLOAD_PATH.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        n_live = len(payload["jason_live"])
        print(
            f"Bid Desk refreshed {payload['meta']['generated']} · "
            f"Jason live {n_live} · assigned {payload['jason_n_assigned']} · "
            f"submitted {payload['jason_ever_submitted']} · "
            f"{OUT_HTML}"
        )
        return 0
    except Exception as e:
        print(f"Bid Desk refresh FAILED: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
