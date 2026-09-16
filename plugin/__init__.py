"""Interactive artifacts — dashboard + desktop plugin, plus two agent tools.

Boards live in any repo named by ``roots.json`` and are addressed by the key
``"<root>/<id>"``; a bare id resolves in the default (first) root.

The dashboard router (``dashboard/plugin_api.py``) and the desktop pane
(``desktop/plugin.js``) let a human browse the boards; these tools let the agent
see and refresh them too. All three share the id validation and containment
check in ``_core`` — no path handling is duplicated here.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from . import _core

logger = logging.getLogger(__name__)

TOOLSET = "interactive_artifacts"


def _json(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _err(message: str, **extra: Any) -> str:
    return _json({"success": False, "error": message, **extra})


def check_artifacts_available() -> bool:
    """True when ANY configured root has a boards directory — otherwise the tools
    stay hidden. One missing repo must not hide the boards you do have."""
    for row in _core.roots():
        boards = _core.boards_dir(row)
        if boards is not None and boards.is_dir():
            return True
    return False


LIST_ARTIFACTS_SCHEMA = {
    "name": "list_artifacts",
    "description": (
        "List the interactive artifact boards (single-file HTML dashboards) across "
        "every configured repo. Returns each board's key ('<root>/<id>', e.g. "
        "'hermes/vault-graph'), title, description, root and generated_at timestamp "
        "so you can tell which boards are stale. Pass the key to refresh_artifact."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}

REFRESH_ARTIFACT_SCHEMA = {
    "name": "refresh_artifact",
    "description": (
        "Re-run the collector for one interactive artifact board, regenerating its "
        "data and index.html. Each repo refreshes its own boards with its own "
        "tools/refresh.py. Takes up to 120 seconds. Use list_artifacts first to get "
        "valid keys."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "string",
                "description": (
                    "Board key '<root>/<id>', e.g. 'findev/spy-flow'. A bare id "
                    "('vault-graph') resolves in the default root. Lowercase "
                    "letters, digits and hyphens only in each half."
                ),
            }
        },
        "required": ["id"],
        "additionalProperties": False,
    },
}


def handle_list_artifacts(args: Dict[str, Any], **_kw) -> str:
    try:
        rows = _core.list_items()
    except OSError as e:
        return _err(f"could not read artifacts root: {e}")
    items = [
        {
            "key": r["key"],
            "id": r["id"],
            "root": r["root"],
            "title": r["title"],
            "description": r["description"],
            "generated_at": r["generated_at"],
            "refreshable": r["refreshable"],
        }
        for r in rows
    ]
    return _json({
        "success": True,
        "roots": [{"name": r["name"], "path": str(r["path"])} for r in _core.roots()],
        "count": len(items),
        "items": items,
    })


def handle_refresh_artifact(args: Dict[str, Any], **_kw) -> str:
    artifact_id = (args.get("id") or "").strip()
    if not artifact_id:
        return _err("id is required")
    if not _core.id_ok(artifact_id):
        known = ", ".join(r["name"] for r in _core.roots())
        return _err(
            "invalid artifact key — expected '<root>/<id>' or a bare id, lowercase "
            f"letters, digits and hyphens only. Configured roots: {known}"
        )
    try:
        ok, code, detail = _core.run_refresh(artifact_id)
    except OSError as e:
        return _err(f"refresh could not start: {e}", id=artifact_id)
    if not ok:
        return _err(detail or code, id=artifact_id, code=code)
    row = _core.item(artifact_id)
    return _json({
        "success": True,
        "key": (row or {}).get("key", artifact_id),
        "id": (row or {}).get("id", artifact_id),
        "root": (row or {}).get("root", ""),
        "generated_at": (row or {}).get("generated_at", ""),
        "title": (row or {}).get("title", artifact_id),
    })


_TOOLS = (
    ("list_artifacts", LIST_ARTIFACTS_SCHEMA, handle_list_artifacts, "🧩"),
    ("refresh_artifact", REFRESH_ARTIFACT_SCHEMA, handle_refresh_artifact, "🔄"),
)


def register(ctx) -> None:
    """Register the agent-facing tools (called once by the plugin loader)."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(name=name, toolset=TOOLSET, schema=schema, handler=handler,
                          check_fn=check_artifacts_available, emoji=emoji)
