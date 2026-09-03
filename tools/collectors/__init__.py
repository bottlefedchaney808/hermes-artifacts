"""Collector registry for Hermes Interactive Artifacts.

A collector is `collect(repo_path: Path) -> dict` returning a payload body
WITHOUT the envelope fields (schema_version / artifact_id / title /
generated_at) — refresh.py stamps those. Include a "source" dict and, when
useful, "notes": [str].
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

COLLECTORS = {}


def register(name: str):
    def deco(fn):
        COLLECTORS[name] = fn
        return fn
    return deco


def json_to_payload(raw: dict) -> dict:
    """Generic adapter: flatten a nested JSON blob into cards + one table."""
    rows = []

    def walk(prefix, obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(f"{prefix}{k}." if prefix else f"{k}.", v)
        elif isinstance(obj, list):
            rows.append([prefix.rstrip("."), f"list[{len(obj)}]"])
        else:
            rows.append([prefix.rstrip("."), str(obj)])

    walk("", raw)
    return {
        "summary": [{"label": r[0], "value": r[1]} for r in rows[:8]],
        "tables": [{"id": "fields", "title": "Fields",
                    "columns": ["field", "value"], "rows": rows}],
        "charts": [],
        "notes": [],
    }
