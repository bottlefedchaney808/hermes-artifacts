"""Allow-listed read + refresh for the hermes-artifacts boards.

Serves only files under ROOT/artifacts/<id>/index.html. No secrets, no
arbitrary paths, no shell interpolation.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

router = APIRouter()

ROOT = Path(r"C:/Users/bottl/hermes-artifacts").resolve()
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
PY = Path(r"C:/Users/bottl/FinancialDevelopment/.venv/Scripts/python.exe")


def _id_ok(artifact_id: str) -> str:
    if not ID_RE.match(artifact_id or ""):
        raise HTTPException(400, "invalid artifact id")
    return artifact_id


def _index_path(artifact_id: str) -> Path:
    aid = _id_ok(artifact_id)
    path = (ROOT / "artifacts" / aid / "index.html").resolve()
    root = ROOT / "artifacts"
    if root not in path.parents and path.parent != root:
        raise HTTPException(400, "path outside artifacts root")
    return path


def _item(artifact_id: str) -> dict | None:
    d = ROOT / "artifacts" / artifact_id
    manifest_p = d / "artifact.json"
    index_p = d / "index.html"
    data_p = d / "data.json"
    if not manifest_p.is_file() or not index_p.is_file():
        return None
    try:
        man = json.loads(manifest_p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        man = {}
    generated = ""
    if data_p.is_file():
        try:
            generated = json.loads(data_p.read_text(encoding="utf-8")).get("generated_at") or ""
        except (OSError, json.JSONDecodeError):
            generated = ""
    posix = index_p.resolve().as_posix()
    return {
        "id": artifact_id,
        "title": man.get("title") or artifact_id,
        "description": man.get("description") or "",
        "collector": man.get("collector") or "",
        "generated_at": generated,
        "index_path": str(index_p.resolve()),
        "file_url": "file:///" + posix.lstrip("/"),
    }


@router.get("/items")
def items():
    arts = ROOT / "artifacts"
    out = []
    if arts.is_dir():
        for child in sorted(arts.iterdir()):
            if child.is_dir() and ID_RE.match(child.name):
                row = _item(child.name)
                if row:
                    out.append(row)
    return {"root": str(ROOT), "items": out}


@router.get("/artifact/{artifact_id}")
def artifact(artifact_id: str):
    row = _item(_id_ok(artifact_id))
    if not row:
        raise HTTPException(404, "artifact not found")
    return row


class RefreshBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError("invalid artifact id")
        return v


@router.post("/refresh")
def refresh(body: RefreshBody):
    aid = body.id
    _index_path(aid)  # id + containment check even if index missing
    py = PY if PY.is_file() else Path(sys.executable)
    script = ROOT / "tools" / "refresh.py"
    if not script.is_file():
        raise HTTPException(503, "refresh tool missing")
    try:
        proc = subprocess.run(
            [str(py), str(script), aid],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "refresh timed out") from None
    if proc.returncode != 0:
        raise HTTPException(503, "refresh failed")
    row = _item(aid)
    if not row:
        raise HTTPException(503, "refresh produced no index")
    return {"ok": True, "item": row}
