"""Network-free unit tests for the Hermes Interactive Artifacts refresh tool."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import refresh  # noqa: E402

VALID = {
    "schema_version": 1,
    "artifact_id": "demo",
    "title": "Demo",
    "generated_at": "2026-09-02 23:00 UTC",
    "summary": [{"label": "rows", "value": "42"}],
    "tables": [{"id": "t", "title": "T", "columns": ["a", "b"], "rows": [["1", "x"]]}],
    "charts": [{"id": "c", "title": "C", "type": "bar",
                "labels": ["a"], "series": [{"label": "s", "data": [1]}]}],
    "notes": [],
}

TEMPLATE = """<!DOCTYPE html>
<html><head><title>T</title>
<!--HERMES-ARTIFACT:CSS-->
<!--/HERMES-ARTIFACT:CSS-->
</head><body><div id="app"></div>
<!--HERMES-ARTIFACT:DATA-->
<!--/HERMES-ARTIFACT:DATA-->
<!--HERMES-ARTIFACT:JS-->
<!--/HERMES-ARTIFACT:JS-->
</body></html>
"""


def test_validate_accepts_valid_payload():
    assert refresh.validate_payload(VALID) == []


def test_validate_rejects_bad_chart_type():
    bad = dict(VALID, charts=[{"id": "c", "title": "C", "type": "pie",
                               "labels": [], "series": []}])
    assert any("type" in e for e in refresh.validate_payload(bad))


def test_validate_rejects_row_wider_than_columns():
    bad = json.loads(json.dumps(VALID))
    bad["tables"][0]["rows"] = [["1", "x", "extra"]]
    assert refresh.validate_payload(bad)


def test_validate_rejects_bad_schema_version():
    bad = dict(VALID, schema_version=2)
    assert refresh.validate_payload(bad)


def test_build_index_inlines_assets_and_data(tmp_path):
    tpl = tmp_path / "template.html"
    tpl.write_text(TEMPLATE, encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "hermes-artifact.css").write_text("body{}", encoding="utf-8")
    (assets / "hermes-artifact.js").write_text("window.HermesArtifact={};", encoding="utf-8")
    html = refresh.build_index(tpl, VALID, assets)
    assert "<style>" in html and "body{}" in html
    assert 'id="hermes-artifact-data"' in html
    embedded = html.split('type="application/json">', 1)[1].split("</script>", 1)[0]
    assert json.loads(embedded) == VALID
    assert "window.HermesArtifact" in html


def test_build_index_escapes_closing_tag_in_data(tmp_path):
    tpl = tmp_path / "template.html"
    tpl.write_text(TEMPLATE, encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "hermes-artifact.css").write_text("", encoding="utf-8")
    (assets / "hermes-artifact.js").write_text("", encoding="utf-8")
    payload = dict(VALID, notes=["evil </script> string"])
    html = refresh.build_index(tpl, payload, assets)
    # the evil string survives only in escaped form; the two real closers
    # are the structural ones (data block + js block)
    assert "<\\/script> string" in html
    assert html.count("</script>") == 2


def test_build_index_rejects_missing_marker(tmp_path):
    tpl = tmp_path / "template.html"
    tpl.write_text("<html></html>", encoding="utf-8")
    with pytest.raises(ValueError):
        refresh.build_index(tpl, VALID, tmp_path)


def test_cli_list(tmp_path, capsys):
    (tmp_path / "artifacts" / "a").mkdir(parents=True)
    assert refresh.main(["--list"], root=tmp_path) == 0
    assert "a" in capsys.readouterr().out


def test_json_to_payload_flattens_scalars():
    import collectors
    payload = collectors.json_to_payload({"spot": 6650.5, "flags": ["a", "b"]})
    assert payload["summary"][0]["label"] == "spot"
    assert ["spot", "6650.5"] in payload["tables"][0]["rows"]
