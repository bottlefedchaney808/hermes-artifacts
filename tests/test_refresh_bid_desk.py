"""Offline unit tests for refresh_bid_desk.py — no Gmail, no network."""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

SCRIPT = Path(r"C:\Users\bottl\hermes-artifacts\refresh_bid_desk.py")


def load():
    spec = importlib.util.spec_from_file_location("refresh_bid_desk", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture
def m():
    return load()


def test_main_is_importable_without_running(m):
    assert callable(m.main)
    assert callable(m.build_payload)
    assert callable(m.inject)


def test_classify(m):
    assert m.classify("You have a new pipeline record: Troost 75") == "new_opportunity"
    assert m.classify("Opportunity moved forward to Takeoff: Troost 75") == "stage_move"
    assert m.classify("You have a new task: Review and Start Bid") == "task"
    assert m.classify("Hi Jason, you have 1 meeting and 0 tasks due today.") == "digest"


def test_clean_strips_copy_and_html(m):
    assert m.clean("MacArthur Court (Copy)") == "MacArthur Court"
    assert m.clean("Manchester &amp; La Tijera") == "Manchester & La Tijera"


def test_build_payload_jason_only(m):
    recs = [
        {
            "date": "2026-09-01",
            "iso": "2026-09-01T12:00:00-05:00",
            "kind": "new_opportunity",
            "subject": "You have a new pipeline record: Troost 75",
            "snippet": "Pipeline Record: Troost 75 has been assigned to you. It's due on: September 4",
        },
        {
            "date": "2026-09-02",
            "iso": "2026-09-02T12:00:00-05:00",
            "kind": "stage_move",
            "subject": "Opportunity moved forward to Takeoff: Troost 75",
            "snippet": "moved opportunity Troost 75 forward to stage: Takeoff.",
        },
        {
            "date": "2026-08-01",
            "iso": "2026-08-01T12:00:00-05:00",
            "kind": "stage_move",
            "subject": "Opportunity moved forward to Assigned Bids: Fairchild",
            "snippet": "moved opportunity Fairchild forward to stage: Assigned Bids.",
        },
        {
            "date": "2026-08-15",
            "iso": "2026-08-15T12:00:00-05:00",
            "kind": "stage_move",
            "subject": "Opportunity moved forward to Submitted: Fairchild",
            "snippet": "moved opportunity Fairchild forward to stage: Submitted.",
        },
        {
            "date": "2026-08-01",
            "iso": "2026-08-01T10:00:00-05:00",
            "kind": "new_opportunity",
            "subject": "You have a new pipeline record: Fairchild",
            "snippet": "Pipeline Record: Fairchild has been assigned to you. It's due on: August 17",
        },
    ]
    live = [
        {
            "name": "Troost 75",
            "gc": "LV Construction LLC",
            "bid_due": "2026-09-04",
            "stage": "Takeoff",
            "tasks": 2,
            "source": "live Copper · Jason filter",
            "owner": "Jason Chaney",
        }
    ]
    db = {
        "kpi": {"pipeline_total": 1, "sf": 1, "units": 1, "records": 1, "sf_total_n": 1, "projects": 1, "final_db": 1},
        "pricing": {
            "n": 0, "per_sf": {"n": 0, "min": 0, "p25": 0, "med": 0, "p75": 0, "p90": 0, "max": 0},
            "buckets": {}, "buckets_pct": {},
            "per_unit": {"n": 0, "p25": 0, "med": 0, "p75": 0},
            "unit_hist": {}, "unit_hist_pct": {},
        },
        "top": [],
        "intum": {"n_proposals": 0, "combined": 0, "note": ""},
    }
    now = datetime(2026, 9, 3, tzinfo=timezone.utc)
    p = m.build_payload(recs, live, db, now)
    assert p["jason_live"] == live
    assert p["jason_n_assigned"] == 2  # Troost + Fairchild
    assert p["jason_ever_submitted"] == 1  # Fairchild
    assert p["speed"]["n"] == 1
    assert p["speed"]["med"] == 14  # Aug 1 -> Aug 15
    assert any(r["name"] == "Fairchild" for r in p["jason_hist_past"])
    assert not any(r["name"] == "Troost 75" for r in p["jason_hist_up"])  # live, not hist


def test_inject_requires_placeholder(m, tmp_path):
    with pytest.raises(RuntimeError, match="placeholder"):
        m.inject("<html></html>", {"a": 1})
    out = m.inject("const D = __PAYLOAD__;", {"a": 1})
    assert out == 'const D = {"a":1};'


def test_load_live_reads_list(m, tmp_path, monkeypatch):
    snap = tmp_path / "jason_live.json"
    snap.write_text(json.dumps([{"name": "X"}]), encoding="utf-8")
    monkeypatch.setattr(m, "LIVE_SNAP", snap)
    assert m.load_live() == [{"name": "X"}]
