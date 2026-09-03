#!/usr/bin/env python3
"""Hermes Interactive Artifacts — refresh tool.

Refresh one artifact or all: writes data.json and rebuilds a fully
self-contained index.html (CSS/JS/data inlined; Chart.js stays CDN).
Collectors are stdlib-only and read their source repo read-only.

Usage:
  python tools/refresh.py --list
  python tools/refresh.py var-simulations-digest
  python tools/refresh.py --all
  python tools/refresh.py var-simulations-digest --repo C:/path/to/other/repo
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import collectors  # noqa: E402

for _mod in sorted(p.name for p in (ROOT / "tools" / "collectors").glob("*_collector.py")):
    __import__(f"collectors.{_mod[:-3]}")

LINUX_FINDEV = Path("/opt/data/FinancialDevelopment")


def _resolve_repo(manifest_repo, override=None) -> Path:
    if override:
        return Path(override)
    p = Path(manifest_repo)
    if p.exists():
        return p
    if LINUX_FINDEV.exists():
        return LINUX_FINDEV
    return p


CSS_MARKER = ("<!--HERMES-ARTIFACT:CSS-->", "<!--/HERMES-ARTIFACT:CSS-->")
DATA_MARKER = ("<!--HERMES-ARTIFACT:DATA-->", "<!--/HERMES-ARTIFACT:DATA-->")
JS_MARKER = ("<!--HERMES-ARTIFACT:JS-->", "<!--/HERMES-ARTIFACT:JS-->")
CHART_TYPES = {"line", "bar", "doughnut"}


def validate_payload(p: dict) -> list:
    """Return a list of human-readable errors; empty list = valid."""
    errors = []

    def need(cond, msg):
        if not cond:
            errors.append(msg)

    need(isinstance(p, dict), "payload must be an object")
    if not isinstance(p, dict):
        return errors
    need(p.get("schema_version") == 1, "schema_version must be 1")
    for key in ("artifact_id", "title", "generated_at"):
        need(isinstance(p.get(key), str), f"{key} must be a string")
    for name in ("summary", "tables", "charts", "notes"):
        need(isinstance(p.get(name, []), list), f"{name} must be a list")
    for i, c in enumerate(p.get("summary", [])):
        need(isinstance(c, dict) and "label" in c and "value" in c,
             f"summary[{i}] needs label+value")
    for i, t in enumerate(p.get("tables", [])):
        need(isinstance(t, dict) and isinstance(t.get("title"), str),
             f"tables[{i}] needs a string title")
        cols = t.get("columns", []) if isinstance(t, dict) else []
        need(isinstance(cols, list) and all(isinstance(c, str) for c in cols),
             f"tables[{i}].columns must be list[str]")
        need(isinstance(t.get("rows"), list), f"tables[{i}].rows must be a list")
        for j, r in enumerate(t.get("rows", [])):
            need(isinstance(r, list) and len(r) <= len(cols),
                 f"tables[{i}].rows[{j}] must have <= {len(cols)} cells")
    for i, c in enumerate(p.get("charts", [])):
        need(isinstance(c, dict) and c.get("type") in CHART_TYPES,
             f"charts[{i}].type must be one of {sorted(CHART_TYPES)}")
        need(isinstance(c.get("labels"), list), f"charts[{i}].labels must be a list")
        series = c.get("series", []) if isinstance(c, dict) else []
        need(isinstance(series, list) and all(
            isinstance(s, dict) and isinstance(s.get("data"), list) for s in series),
            f"charts[{i}].series must be a list of {{label, data}}")
    return errors


def _inject(html: str, marker, content: str) -> str:
    start, end = marker
    if start not in html or end not in html:
        raise ValueError(f"marker {start!r} missing from template")
    head = html.split(start, 1)[0] + start
    tail = html.split(end, 1)[1]
    return head + "\n" + content + "\n" + end + tail


def build_index(template: Path, payload: dict, assets_dir: Path) -> str:
    html = template.read_text(encoding="utf-8")
    for marker in (CSS_MARKER, DATA_MARKER, JS_MARKER):
        if marker[0] not in html or marker[1] not in html:
            raise ValueError(f"marker {marker[0]!r} missing from template")
    css = (assets_dir / "hermes-artifact.css").read_text(encoding="utf-8")
    js = (assets_dir / "hermes-artifact.js").read_text(encoding="utf-8")
    assert "</script>" not in js, "hermes-artifact.js must not contain </script>"
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = _inject(html, CSS_MARKER, "<style>\n" + css + "\n</style>")
    html = _inject(html, DATA_MARKER,
                   '<script id="hermes-artifact-data" type="application/json">\n'
                   + data + "\n</script>")
    html = _inject(html, JS_MARKER, "<script>\n" + js + "\n</script>")
    return html


def refresh_one(artifact_id: str, repo_override=None, root: Path = ROOT) -> dict:
    artifact_dir = root / "artifacts" / artifact_id
    manifest = json.loads((artifact_dir / "artifact.json").read_text(encoding="utf-8"))
    collector_name = manifest["collector"]
    if collector_name not in collectors.COLLECTORS:
        raise SystemExit(f"unknown collector {collector_name!r} for {artifact_id}")
    repo = _resolve_repo(manifest["repo"], repo_override)
    payload = collectors.COLLECTORS[collector_name](repo)
    payload.update({
        "schema_version": 1,
        "artifact_id": artifact_id,
        "title": manifest.get("title", artifact_id),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    })
    errors = validate_payload(payload)
    if errors:
        raise SystemExit(f"{artifact_id}: invalid payload:\n"
                         + "\n".join("  - " + e for e in errors))
    (artifact_dir / "data.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html = build_index(artifact_dir / "template.html", payload, root / "assets")
    (artifact_dir / "index.html").write_text(html, encoding="utf-8")
    return payload


def main(argv=None, root: Path = ROOT) -> int:
    ap = argparse.ArgumentParser(description="Refresh Hermes interactive artifacts")
    ap.add_argument("artifact", nargs="?", help="artifact id (folder under artifacts/)")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--repo", help="override the source repo path for this refresh")
    args = ap.parse_args(argv)
    ids = sorted(p.name for p in (root / "artifacts").iterdir() if p.is_dir())
    if args.list:
        print("\n".join(ids))
        return 0
    if args.all:
        for aid in ids:
            refresh_one(aid, args.repo, root=root)
            print(f"refreshed {aid}")
        return 0
    if not args.artifact:
        ap.error("give an artifact id, --all, or --list")
    refresh_one(args.artifact, args.repo, root=root)
    print(f"refreshed {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
