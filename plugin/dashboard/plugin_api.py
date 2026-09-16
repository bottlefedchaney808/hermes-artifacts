"""Allow-listed read + refresh for the hermes-artifacts boards.

Serves only files under ROOT/artifacts/<id>/index.html. No secrets, no
arbitrary paths, no shell interpolation.

The id validation, containment check and refresh logic live in the plugin's
``_core`` module so the agent tools in ``__init__.py`` enforce exactly the same
rules. This file is loaded standalone by the web server (no package context),
so ``_core`` is loaded by explicit path rather than imported relatively.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter()

_CORE_MODULE = "hermes_interactive_artifacts_core"


def _load_core():
    """Import the sibling ``_core.py`` by path (cached in sys.modules)."""
    existing = sys.modules.get(_CORE_MODULE)
    if existing is not None:
        return existing
    core_path = Path(__file__).resolve().parent.parent / "_core.py"
    spec = importlib.util.spec_from_file_location(_CORE_MODULE, core_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load interactive-artifacts core from {core_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_CORE_MODULE] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(_CORE_MODULE, None)
        raise
    return mod


core = _load_core()

ROOT = core.ROOT
ID_RE = core.ID_RE

# HTTP status for each _core.run_refresh failure code.
_REFRESH_STATUS = {"bad_id": 400, "tool_missing": 503, "timeout": 504,
                   "failed": 503, "no_index": 503}


def _id_ok(artifact_id: str) -> str:
    if not core.id_ok(artifact_id):
        raise HTTPException(400, "invalid artifact id")
    return artifact_id


@router.get("/items")
def items():
    # `root` is kept for older callers that read it; `roots` is the real answer now.
    return {
        "root": str(ROOT),
        "roots": [
            {"name": r["name"], "path": str(r["path"]), "boards": r["boards"]}
            for r in core.roots()
        ],
        "items": core.list_items(),
    }


@router.get("/artifact")
def artifact_by_key(key: str):
    """Qualified lookup: ``?key=findev/spy-flow``. A path parameter cannot carry the
    '/' in a key, so the multi-root door is a query parameter and
    ``/artifact/{id}`` stays as the bare-id form it always was."""
    row = core.item(_id_ok(key))
    if not row:
        raise HTTPException(404, "artifact not found")
    return row


@router.get("/artifact/{artifact_id}")
def artifact(artifact_id: str):
    row = core.item(_id_ok(artifact_id))
    if not row:
        raise HTTPException(404, "artifact not found")
    return row


class RefreshBody(BaseModel):
    # `id` accepts a bare id (default root) or a qualified "<root>/<id>" key; the
    # name stays `id` so existing callers' bodies keep validating.
    id: str = Field(..., min_length=1, max_length=100)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not core.id_ok(v):
            raise ValueError("invalid artifact id")
        return v


@router.post("/refresh")
def refresh(body: RefreshBody):
    aid = body.id
    ok, code, detail = core.run_refresh(aid)
    if not ok:
        # Surface the collector's stderr tail — a bare 503 is undebuggable from the UI.
        message = f"refresh {code}" if not detail else f"refresh {code}: {detail}"
        raise HTTPException(_REFRESH_STATUS.get(code, 503), message)
    row = core.item(aid)
    if not row:
        raise HTTPException(503, "refresh produced no index")
    return {"ok": True, "item": row}
