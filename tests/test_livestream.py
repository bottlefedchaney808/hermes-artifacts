"""Tests for tools/livestream.py — the streaming engine (no subprocess runs)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import livestream  # noqa: E402
from refresh import _inject  # noqa: E402

DATA_MARKER = livestream.DATA_MARKER


def _make_streamer(tmp_path, monkeypatch):
    # Redirect the artifact root + template at a tmp sandbox.
    root = tmp_path / "repo"
    (root / "templates").mkdir(parents=True)
    (root / "templates" / "live.html").write_text(
        "<html><head><!--HERMES-ARTIFACT:LIVE-->"
        '<meta id="live-refresh" http-equiv="refresh" content="2.5">'
        "<!--/HERMES-ARTIFACT:LIVE--></head><body>"
        "<!--HERMES-ARTIFACT:DATA-->"
        '<script id="hermes-artifact-data" type="application/json">{}</script>'
        "<!--/HERMES-ARTIFACT:DATA--></body></html>"
    )
    monkeypatch.setattr(livestream, "ROOT", root)
    monkeypatch.setattr(livestream, "LIVE_TEMPLATE", root / "templates" / "live.html")
    st = livestream.Streamer("t1", "T1", ["echo", "hi"], None,
                             [{"label": "k", "value": "v"}])
    return st, root


def test_build_running_injects_data_and_keeps_refresh(tmp_path, monkeypatch):
    st, root = _make_streamer(tmp_path, monkeypatch)
    st.feed("line one")
    st.build("running", live=True)
    html = (root / "artifacts" / "t1" / "index.html").read_text()
    assert 'http-equiv="refresh"' in html  # live -> reload tag present
    payload = json.loads(html.split('type="application/json">\n')[1]
                         .split("\n</script>")[0].replace("<\\/", "</"))
    assert payload["live"] is True and payload["status"] == "running"
    assert payload["log"] == ["line one"]
    assert (root / "artifacts" / "t1" / "data.json").exists()


def test_build_final_strips_refresh_and_is_static(tmp_path, monkeypatch):
    st, root = _make_streamer(tmp_path, monkeypatch)
    st.feed("done step")
    st.build("complete", live=False, exit_code=0)
    html = (root / "artifacts" / "t1" / "index.html").read_text()
    assert 'http-equiv="refresh"' not in html  # final -> no reload
    payload = json.loads(html.split('type="application/json">\n')[1]
                         .split("\n</script>")[0].replace("<\\/", "</"))
    assert payload["live"] is False and payload["exit_code"] == 0
    # data.json agrees
    data = json.loads((root / "artifacts" / "t1" / "data.json").read_text())
    assert data["status"] == "complete"


def test_log_truncates_to_max(tmp_path, monkeypatch):
    st, root = _make_streamer(tmp_path, monkeypatch)
    for i in range(livestream.MAX_LOG_LINES + 50):
        st.log.append(f"line {i}")
    st.build("running", live=True)
    assert len(st.payload("running", True)["log"]) == livestream.MAX_LOG_LINES


def test_manifest_written(tmp_path, monkeypatch):
    st, root = _make_streamer(tmp_path, monkeypatch)
    manifest = json.loads((root / "artifacts" / "t1" / "artifact.json").read_text())
    assert manifest == {"id": "t1", "title": "T1", "collector": "livestream"}


def test_atomic_writes_leave_no_tmp(tmp_path, monkeypatch):
    st, root = _make_streamer(tmp_path, monkeypatch)
    st.feed("x")
    st.build("complete", live=False, exit_code=0)
    leftovers = list((root / "artifacts" / "t1").glob("*.tmp"))
    assert leftovers == []
