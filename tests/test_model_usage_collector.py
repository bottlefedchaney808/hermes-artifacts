"""Collector tests for the model-usage board."""
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import collectors  # noqa: E402
import collectors.model_usage_collector as mu  # noqa: E402

COLS = ["session_id","model","billing_provider","billing_base_url","billing_mode",
        "task","api_call_count","input_tokens","output_tokens","cache_read_tokens",
        "cache_write_tokens","reasoning_tokens","estimated_cost_usd","actual_cost_usd",
        "cost_status","cost_source","first_seen","last_seen"]


def mkdb(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.execute("create table session_model_usage(%s)" % ",".join(
        f"{c_} {'real' if c_ in ('estimated_cost_usd','actual_cost_usd','first_seen','last_seen') else ('int' if 'tokens' in c_ or c_=='api_call_count' else 'text')}"
        for c_ in COLS))
    c.commit()
    return c


def row(**kw):
    base = dict(session_id="s", model="m", billing_provider="", billing_base_url="",
                billing_mode="", task="", api_call_count=0, input_tokens=0, output_tokens=0,
                cache_read_tokens=0, cache_write_tokens=0, reasoning_tokens=0,
                estimated_cost_usd=0.0, actual_cost_usd=0.0, cost_status=None,
                cost_source=None, first_seen=1788700000.0, last_seen=1788703600.0)
    base.update(kw)
    return base


def insert(conn, **kw):
    r = row(**kw)
    conn.execute("insert into session_model_usage values(%s)" % ",".join("?") * len(COLS),
                 [r[c] for c in COLS])


def test_collect_returns_valid_envelope_body(tmp_path):
    p = mu.collect(tmp_path)                 # no state.db -> empty but valid
    for key in ("summary", "tables", "charts", "notes"):
        assert isinstance(p[key], list), f"{key} must be a list"
    assert p["charts"] == []                 # custom layer renders; no Chart.js
    assert all("label" in c and "value" in c for c in p["summary"])
    assert isinstance(p["viz"], dict)
