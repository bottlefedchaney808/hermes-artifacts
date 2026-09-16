"""Board collectors must resolve real data paths (E: folder was renamed)."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import collectors  # noqa: E402
import collectors.kalshi_desk_collector as kalshi  # noqa: E402
import collectors.polymarket_desk_collector as poly  # noqa: E402


def test_kalshi_data_paths_exist():
    assert kalshi.BUCKET_LOG.is_file(), f"missing {kalshi.BUCKET_LOG}"
    assert kalshi.PERPS_TAPE.is_file(), f"missing {kalshi.PERPS_TAPE}"


def test_kalshi_collect_has_data():
    payload = kalshi.collect()
    tables = {t["title"]: t for t in payload.get("tables", [])}
    rows = sum(len(t.get("rows", [])) for t in tables.values())
    assert rows > 0, "kalshi board rendered zero rows — data path broken"


def test_polymarket_data_paths_exist():
    assert poly.POLY_FILLS.is_file(), f"missing {poly.POLY_FILLS}"
    assert poly.HIST_PARSED.is_file(), f"missing {poly.HIST_PARSED}"


def test_polymarket_collect_has_record():
    payload = poly.collect()
    summary = {s["label"].lower(): s["value"] for s in payload.get("summary", [])}
    assert "record" in summary, f"no record summary: {summary}"
    # the E: history has settled Won/Lost trades — record must not be 0W–0L
    assert summary["record"] != "0W–0L", f"zeroed record: {payload.get('summary')}"
