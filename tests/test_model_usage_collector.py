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
    cols = ",".join(COLS)
    qms = ",".join("?" for _ in COLS)
    conn.execute(f"insert into session_model_usage ({cols}) values ({qms})",
                 [r[c] for c in COLS])


def test_collect_returns_valid_envelope_body(tmp_path):
    p = mu.collect(tmp_path)                 # no state.db -> empty but valid
    for key in ("summary", "tables", "charts", "notes"):
        assert isinstance(p[key], list), f"{key} must be a list"
    assert p["charts"] == []                 # custom layer renders; no Chart.js
    assert all("label" in c and "value" in c for c in p["summary"])
    assert isinstance(p["viz"], dict)


def test_reads_all_dbs_and_tags_profile(tmp_path):
    root = tmp_path / "hermes"
    c = mkdb(root / "state.db"); insert(c, billing_provider="zai"); c.commit(); c.close()
    c = mkdb(root / "profiles" / "local-agent" / "state.db")
    insert(c, billing_provider="custom", billing_base_url="http://127.0.0.1:18434/v1")
    c.commit(); c.close()
    c = mkdb(root / "profiles" / "coder1" / "state.db"); insert(c, billing_provider="nous"); c.commit(); c.close()

    rows = mu._read_all(root)
    assert len(rows) == 3
    assert {r["profile"] for r in rows} == {"(root)", "local-agent", "coder1"}


def test_missing_root_is_empty(tmp_path):
    assert mu._read_all(tmp_path / "nope") == []


def test_unreadable_db_is_skipped(tmp_path):
    root = tmp_path / "hermes"
    (root / "profiles" / "broken").mkdir(parents=True)
    (root / "profiles" / "broken" / "state.db").write_text("not a database", encoding="utf-8")
    c = mkdb(root / "state.db"); insert(c); c.commit(); c.close()
    assert len(mu._read_all(root)) == 1          # broken profile skipped, no crash


def test_lane_local_by_provider_and_loopback():
    assert mu._lane(row(billing_provider="custom", billing_base_url="http://127.0.0.1:18434/v1")) == "local"
    assert mu._lane(row(billing_provider="llamacpp")) == "local"
    assert mu._lane(row(billing_provider="", billing_base_url="http://localhost:8080/v1")) == "local"


def test_lane_moa_and_cloud():
    assert mu._lane(row(billing_provider="moa", model="default")) == "moa"
    assert mu._lane(row(billing_provider="nous", billing_base_url="https://inference-api.nousresearch.com/v1")) == "nous"
    assert mu._lane(row(billing_provider="")) == "unknown"


def test_metrics_split_fresh_cached_reasoning():
    r = row(input_tokens=100, output_tokens=50, cache_read_tokens=9000, reasoning_tokens=7)
    assert mu._fresh(r) == 150          # cache must NOT inflate the primary metric
    assert mu._cached(r) == 9000
    assert mu._reasoning(r) == 7
