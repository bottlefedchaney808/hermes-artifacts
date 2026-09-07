"""Model usage board — aggregate session_model_usage across all Hermes profiles.

collect(repo_path) treats repo_path as the HERMES ROOT directory (the manifest
supplies it; `--repo` overrides). Read-only, stdlib only.
"""
from __future__ import annotations

import datetime as _dt
import glob as _glob
import sqlite3
from pathlib import Path

from collectors import register

HERMES_ROOT = Path("C:/Users/bottl/AppData/Local/hermes")


@register("model-usage")
def collect(repo_path=None) -> dict:
    return {"summary": [], "tables": [], "charts": [],
            "notes": ["No usage data found."],
            "source": {"note": "no state.db scanned"},
            "viz": {}}
