"""Shared artifact logic for the dashboard API and the agent tools.

Stdlib only — no FastAPI. ``dashboard/plugin_api.py`` is loaded standalone by the web
server (``spec_from_file_location``, no package context) while ``__init__.py`` is loaded
as a package by the plugin loader, so this module is the one place both can reach without
duplicating the id validation or the containment check.

Nothing here raises HTTPException; callers translate the ``(ok, code, detail)`` results
into whatever their transport needs.

── multi-root ───────────────────────────────────────────────────────────────────
Boards no longer have to live in hermes-artifacts. ``roots.json`` (beside this file)
names any number of repos:

    {"roots": [
       {"name": "hermes", "path": "C:/Users/bottl/hermes-artifacts"},
       {"name": "findev", "path": "C:/Users/bottl/FinancialDevelopment",
        "boards": "artifact-boards"}
    ]}

Per root, all optional except ``name``/``path``:

    boards   subdirectory holding the board folders   (default "artifacts")
    refresh  collector script, relative to the root   (default "tools/refresh.py")
    python   interpreter to run that collector with   (default the shared PY below)

``boards`` exists because a repo may already use ``artifacts/`` for something else —
FinancialDevelopment keeps PNGs, DBs and zips there — and quietly scanning a directory
that means something different to its owner is how you get phantom boards.

Boards are addressed by a **key**, ``"<root>/<id>"``. Both halves are regex-validated
and the root half only ever indexes into the configured table — it is never joined into
a path — so the allow-list posture is unchanged: no arbitrary paths, no traversal, no
shell interpolation. A BARE id (no slash) resolves against the default (first) root,
which is what keeps already-stored ids and existing agent calls working untouched.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# The original single root. Still the default when roots.json is absent, so a fresh
# checkout or a deleted config behaves exactly as it did before multi-root.
LEGACY_ROOT = Path(r"C:/Users/bottl/hermes-artifacts").resolve()
DEFAULT_ROOT_NAME = "hermes"

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
# Deliberately the same shape as an id but shorter: a root name is a label in a table,
# never a path segment, and keeping it boring makes the key unambiguous to split.
ROOT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")

PY = Path(__file__).resolve().parents[1] / ".venv/Scripts/python.exe"

REFRESH_TIMEOUT_S = 120
STDERR_TAIL_CHARS = 800

_ROOTS_FILE = Path(__file__).resolve().parent / "roots.json"

# (mtime_ns, parsed) — reparsing on every list_items() call would stat-and-read the
# config for every board row; caching on mtime keeps an edit picked up without a
# restart while costing one stat.
_roots_cache: tuple[int, list[dict]] | None = None


DEFAULT_BOARDS_DIR = "artifacts"
DEFAULT_REFRESH_REL = "tools/refresh.py"


def _fallback_roots() -> list[dict]:
    return [{
        "name": DEFAULT_ROOT_NAME,
        "path": LEGACY_ROOT,
        "boards": DEFAULT_BOARDS_DIR,
        "refresh": DEFAULT_REFRESH_REL,
        "python": None,
    }]


def _contained(base: Path, relative: str) -> Path | None:
    """``base / relative`` when it stays inside *base*, else None.

    roots.json is local config, not user input off the wire, but it is edited by
    agents as well as humans — so an absolute path or a '..' in ``boards``/``refresh``
    is rejected here rather than trusted to be well-meant."""
    raw = (relative or "").strip().replace("\\", "/")
    # Reject an absolute path OUTRIGHT rather than stripping it into a relative one.
    # Both orders stay inside the root, but silently reading "/etc/passwd" as
    # "<root>/etc/passwd" is a config value that does something other than it says.
    if not raw or raw.startswith("/") or Path(raw).is_absolute():
        return None
    candidate = Path(raw.strip("/"))
    if not candidate.parts:
        return None
    resolved = (base / candidate).resolve()
    if base != resolved and base not in resolved.parents:
        return None
    return resolved


def boards_dir(row: dict) -> Path | None:
    return _contained(row["path"], row.get("boards") or DEFAULT_BOARDS_DIR)


def refresh_script(row: dict) -> Path | None:
    return _contained(row["path"], row.get("refresh") or DEFAULT_REFRESH_REL)


def _parse_roots(raw: object) -> list[dict]:
    """Validate a parsed roots.json body into rows. Invalid entries are dropped, not
    fatal: one bad line in the config must not take every board offline."""
    entries = raw.get("roots") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip().lower()
        path = str(entry.get("path") or "").strip()
        if not ROOT_NAME_RE.match(name) or name in seen or not path:
            continue
        try:
            resolved = Path(path).resolve()
        except (OSError, ValueError):
            continue
        py = str(entry.get("python") or "").strip()
        out.append({
            "name": name,
            "path": resolved,
            "boards": str(entry.get("boards") or DEFAULT_BOARDS_DIR).strip() or DEFAULT_BOARDS_DIR,
            "refresh": str(entry.get("refresh") or DEFAULT_REFRESH_REL).strip() or DEFAULT_REFRESH_REL,
            "python": Path(py) if py else None,
        })
        seen.add(name)
    return out


def roots() -> list[dict]:
    """Configured roots, always at least one. Never raises."""
    global _roots_cache
    try:
        mtime = _ROOTS_FILE.stat().st_mtime_ns
    except OSError:
        _roots_cache = None
        return _fallback_roots()
    if _roots_cache is not None and _roots_cache[0] == mtime:
        return _roots_cache[1]
    try:
        parsed = _parse_roots(json.loads(_ROOTS_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        parsed = []
    rows = parsed or _fallback_roots()
    _roots_cache = (mtime, rows)
    return rows


def default_root_name() -> str:
    return roots()[0]["name"]


def root_row(name: str) -> dict | None:
    for row in roots():
        if row["name"] == name:
            return row
    return None


# ``ROOT`` is kept as a module attribute because plugin_api.py and __init__.py both
# read it, and an agent reading old docs will reach for it. It now means "the default
# root" rather than "the only root".
ROOT = roots()[0]["path"]


def split_key(key: str) -> tuple[str, str] | None:
    """``"findev/bid-desk"`` -> ``("findev", "bid-desk")``; a bare id resolves to the
    default root. Returns None when either half fails validation or the root is not
    configured — so a caller can never address a path that is not in the table."""
    raw = (key or "").strip()
    if not raw:
        return None
    if "/" in raw:
        root_name, _, artifact_id = raw.partition("/")
        root_name = root_name.strip().lower()
    else:
        root_name, artifact_id = default_root_name(), raw
    if not ROOT_NAME_RE.match(root_name) or not ID_RE.match(artifact_id):
        return None
    if root_row(root_name) is None:
        return None
    return root_name, artifact_id


def id_ok(key: str) -> bool:
    """True when *key* is a safe, configured board address (bare id or ``root/id``)."""
    return split_key(key) is not None


def index_path(key: str) -> Path | None:
    """Resolved ``index.html`` for *key*, or None when the key is invalid or the
    resolved path escapes its root's artifacts directory."""
    parts = split_key(key)
    if parts is None:
        return None
    root_name, artifact_id = parts
    row = root_row(root_name)
    if row is None:
        return None
    arts = boards_dir(row)
    if arts is None:
        return None
    path = (arts / artifact_id / "index.html").resolve()
    # Containment is re-checked AFTER resolve() so a symlinked board directory cannot
    # smuggle the read outside the root even though the id itself was well-formed.
    if arts not in path.parents and path.parent != arts:
        return None
    return path


def item(key: str) -> dict | None:
    """Board row for *key*, or None when it is not a complete board."""
    parts = split_key(key)
    if parts is None:
        return None
    root_name, artifact_id = parts
    row = root_row(root_name)
    if row is None:
        return None
    arts = boards_dir(row)
    if arts is None:
        return None
    d = arts / artifact_id
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
        "key": f"{root_name}/{artifact_id}",
        "root": root_name,
        "root_path": str(row["path"]),
        "refreshable": bool(refresh_script(row) and refresh_script(row).is_file()),
        "title": man.get("title") or artifact_id,
        "description": man.get("description") or "",
        "collector": man.get("collector") or "",
        "generated_at": generated,
        "index_path": str(index_p.resolve()),
        "file_url": "file:///" + posix.lstrip("/"),
    }


def list_items() -> list[dict]:
    """Every complete board across every configured root, sorted by (root, id).

    A root that does not exist on this machine contributes nothing rather than
    raising — roots.json is shared config, and a repo you have not cloned yet is a
    normal state, not an error."""
    out: list[dict] = []
    for row in roots():
        arts = boards_dir(row)
        if arts is None or not arts.is_dir():
            continue
        try:
            children = sorted(arts.iterdir())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and ID_RE.match(child.name):
                board = item(f"{row['name']}/{child.name}")
                if board:
                    out.append(board)
    return out


def run_refresh(key: str) -> tuple[bool, str, str]:
    """Re-run the collector for *key*.

    Returns ``(ok, code, detail)``. ``code`` is one of ``bad_id``, ``tool_missing``,
    ``timeout``, ``failed``, ``no_index`` or ``""`` on success; ``detail`` carries the
    stderr tail on failure so a caller can surface why rather than a bare status.

    The collector is resolved PER ROOT: each repo refreshes its own boards with its own
    ``tools/refresh.py`` (and optionally its own interpreter), so a board in
    FinancialDevelopment is never regenerated by hermes-artifacts' collector.
    """
    parts = split_key(key)
    if parts is None or index_path(key) is None:  # id + containment even if index missing
        return False, "bad_id", "invalid artifact id"
    root_name, artifact_id = parts
    row = root_row(root_name)
    if row is None:
        return False, "bad_id", "unknown root"
    script = refresh_script(row)
    if script is None or not script.is_file():
        return False, "tool_missing", f"refresh tool missing at {script or row['refresh']}"
    candidates = [row.get("python"), PY]
    py = next((p for p in candidates if p and p.is_file()), Path(sys.executable))
    try:
        proc = subprocess.run(
            [str(py), str(script), artifact_id],
            cwd=str(row["path"]),
            capture_output=True,
            text=True,
            timeout=REFRESH_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout", f"refresh exceeded {REFRESH_TIMEOUT_S}s"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-STDERR_TAIL_CHARS:]
        return False, "failed", tail or f"exit code {proc.returncode}"
    if item(key) is None:
        return False, "no_index", "refresh produced no index"
    return True, "", ""
