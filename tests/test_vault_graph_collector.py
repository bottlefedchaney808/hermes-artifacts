"""Collector tests for the vault-graph wikilink scan."""
from __future__ import annotations

from pathlib import Path
import sys

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import collectors  # noqa: E402
import collectors.vault_graph_collector as vg  # noqa: E402


def test_collect_reads_wikilinks(tmp_path: Path):
    (tmp_path / "Development").mkdir()
    (tmp_path / "Home.md").write_text("See [[Development]] and [[Missing]].\n", encoding="utf-8")
    (tmp_path / "Development.md").write_text("# Development\n", encoding="utf-8")
    payload = vg.collect(tmp_path)
    assert payload["summary"][0]["label"] == "notes"
    ids = {n["id"] for n in payload["graph"]["nodes"]}
    assert "Home.md" in ids
    assert "Development.md" in ids
    assert any(n.startswith("dangling:") for n in ids)
    assert payload["graph"]["edges"]
    assert payload["charts"][0]["type"] == "doughnut"
