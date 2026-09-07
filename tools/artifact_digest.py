#!/usr/bin/env python3
"""
artifact_digest.py — Render any hermes-artifacts data.json as a Discord-native message.

Reads the data contract (schema v1: summary/tables/charts/notes) and emits text
formatted for Discord markdown: bold cards, code-block tables (Discord renders
monospace cleanly on desktop AND mobile), tone emoji, chart fallbacks.

Usage:
  python3 artifact_digest.py <artifact_id_or_path.json> [--max-chars 1900]

With an artifact id, reads /opt/data/hermes-artifacts/artifacts/<id>/data.json.
Exit 0 always on valid input; prints the formatted message to stdout.
"""
import json
import sys
from pathlib import Path

ARTIFACTS_DIR = Path("/opt/data/hermes-artifacts/artifacts")

# Discord hard limit is 2000 chars; leave margin for subject lines prepended later.
DEFAULT_MAX = 1900

TONE_EMOJI = {
    "ok": "🟢", "good": "🟢", "pass": "🟢",
    "bad": "🔴", "fail": "🔴", "error": "🔴",
    "warn": "🟡", "warning": "🟡",
    "info": "🔵", "neutral": "🔵",
}


def _tone_emoji(tone):
    if not tone:
        return ""
    return TONE_EMOJI.get(str(tone).lower(), "▫️")


def _truncate_cell(value, width):
    s = str(value) if value is not None else ""
    return s if len(s) <= width else s[: width - 1] + "…"


def _render_table_md(table, max_width=24):
    """Render one table as a Discord code block with padded columns."""
    cols = table.get("columns", [])
    rows = table.get("rows", [])
    if not cols:
        return None

    # Cap rows/cols for readability; Discord is a chat surface, not a data explorer
    rows = rows[:10]
    cols = cols[:8]

    grid = [cols] + [[_truncate_cell(c, max_width) for c in r] for r in rows]
    widths = [max(len(str(row[i])) if i < len(row) else 0 for row in grid) for i in range(len(cols))]

    def fmt(row):
        return " | ".join(str(row[i]).ljust(widths[i]) if i < len(row) else " " * widths[i]
                          for i in range(len(cols)))

    sep = "-+-".join("-" * w for w in widths)
    body = "\n".join([fmt(grid[0]), sep] + [fmt(r) for r in grid[1:]])
    title = table.get("title") or table.get("id") or ""
    header = f"**{title}**\n" if title else ""
    return f"{header}```\n{body}\n```"


def _render_chart_fallback(chart):
    """Charts can't render in Discord text — show a compact inline bar if numeric."""
    labels = chart.get("labels", [])
    series = chart.get("series", [])
    if not labels or not series:
        return None
    title = chart.get("title") or chart.get("id") or "chart"
    out = [f"**{title}**"]
    data = series[0].get("data", [])
    nums = [v for v in data if isinstance(v, (int, float))]
    if nums:
        peak = max(abs(v) for v in nums) or 1
        for label, val in list(zip(labels, data))[:8]:
            bar = ""
            if isinstance(val, (int, float)):
                width = max(1, int(round(abs(val) / peak * 10)))
                bar = "█" * width
            out.append(f"{_truncate_cell(label, 14)} `{bar}` {val}")
    else:
        out.append("_(chart: non-numeric data, view in Interactive tab)_")
    return "\n".join(out)


def render_digest(data, max_chars=DEFAULT_MAX):
    parts = []

    title = data.get("title") or data.get("artifact_id") or "report"
    status = data.get("status")
    live = data.get("live")

    header = f"## 📊 {title}"
    if live:
        header += " 🟡 LIVE"
    elif status:
        header += f" — {status}"
    gen = data.get("generated_at", "")
    if gen:
        header += f"\n-# {gen}"
    parts.append(header)

    # Summary cards → one compact line each
    for item in data.get("summary", []):
        label = item.get("label", "?")
        value = item.get("value", "")
        emoji = _tone_emoji(item.get("tone"))
        parts.append(f"{emoji} **{label}:** {value}")

    # Log tail for livestream-style artifacts
    log = data.get("log")
    if isinstance(log, list) and log:
        tail = [line for line in log[-5:] if str(line).strip()]
        if tail:
            parts.append("**Log (tail)**\n```\n" + "\n".join(str(t) for t in tail) + "\n```")

    # Tables
    for table in data.get("tables", [])[:3]:
        rendered = _render_table_md(table)
        if rendered:
            parts.append(rendered)

    # Charts → ASCII bars
    for chart in data.get("charts", [])[:3]:
        rendered = _render_chart_fallback(chart)
        if rendered:
            parts.append(rendered)

    # Notes
    for note in data.get("notes", [])[:5]:
        parts.append(f"> {note}")

    # Enforce Discord limit — keep the head (summary always survives), trim tail
    msg = "\n".join(p for p in parts if p)
    if len(msg) > max_chars:
        msg = msg[: max_chars - 1] + "…"
    return msg


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    max_chars = DEFAULT_MAX
    for a in sys.argv[1:]:
        if a.startswith("--max-chars"):
            max_chars = int(a.split("=")[1])

    if not args:
        print("usage: artifact_digest.py <artifact_id | data.json path>", file=sys.stderr)
        sys.exit(2)

    target = args[0]
    if target.endswith(".json"):
        path = Path(target)
    else:
        path = ARTIFACTS_DIR / target / "data.json"

    try:
        data = json.loads(path.read_text())
    except Exception as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        sys.exit(1)

    print(render_digest(data, max_chars))


if __name__ == "__main__":
    main()
