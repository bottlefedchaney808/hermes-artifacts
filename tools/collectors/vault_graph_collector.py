"""Vault graph — wikilink force-graph of an Obsidian (or any markdown) vault."""
from __future__ import annotations

import collections
import re
from pathlib import Path

from collectors import register

DEFAULT_REPO = Path("C:/Users/bottl/obsidian-vault")
LINK_RE = re.compile(r"\[\[([^\]]+?)\]\]")
SKIP_DIRS = {".git", ".obsidian", ".trash", "__pycache__"}


def _leg(rel: str) -> str:
    p = rel.replace("\\", "/")
    if p.startswith("Construction/") or p == "Construction.md":
        return "construction"
    if p.startswith("Development/") or p == "Development.md":
        return "development"
    if p.startswith("Trading/") or p == "Trading.md":
        return "trading"
    if p.startswith("Daily/"):
        return "daily"
    if p.startswith("Inbox") or p == "Inbox.md":
        return "inbox"
    if p.startswith("Home") or p == "Home.md" or p == "Jason.md":
        return "hub"
    if p.startswith("Templates/"):
        return "templates"
    if p.startswith("Attachments/"):
        return "attachments"
    return "hub"


def _md_files(repo: Path) -> list[Path]:
    out = []
    for p in repo.rglob("*.md"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


@register("vault-graph")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    repo = Path(repo_path)
    files = _md_files(repo) if repo.is_dir() else []
    by_stem: dict[str, list[Path]] = collections.defaultdict(list)
    by_rel: dict[str, Path] = {}
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    for f in files:
        rel = f.relative_to(repo).as_posix()
        by_rel[rel[:-3] if rel.endswith(".md") else rel] = f
        by_stem[f.stem].append(f)
        nodes[rel] = {"id": rel, "label": f.stem, "group": _leg(rel), "size": 1}

    def resolve(target: str) -> str:
        t = target.replace("\\", "/").strip()
        if t.endswith(".md"):
            t = t[:-3]
        if t in by_rel:
            return by_rel[t].relative_to(repo).as_posix()
        stem = Path(t).name
        hits = by_stem.get(stem, [])
        if len(hits) == 1:
            return hits[0].relative_to(repo).as_posix()
        if hits:
            return hits[0].relative_to(repo).as_posix()
        dang = "dangling:" + t
        if dang not in nodes:
            nodes[dang] = {"id": dang, "label": t, "group": "dangling", "size": 1}
        return dang

    for f in files:
        src = f.relative_to(repo).as_posix()
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        seen = set()
        for m in LINK_RE.finditer(text):
            raw = m.group(1)
            target = raw.split("|", 1)[0].split("#", 1)[0].strip()
            if not target or target in seen:
                continue
            seen.add(target)
            dst = resolve(target)
            edges.append({"source": src, "target": dst})

    deg: collections.Counter[str] = collections.Counter()
    for e in edges:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    for n in nodes.values():
        n["size"] = int(deg[n["id"]])

    legs = collections.Counter(n["group"] for n in nodes.values())
    hub_rows = sorted(nodes.values(), key=lambda n: -n["size"])[:25]
    dangling_n = legs.get("dangling", 0)

    return {
        "summary": [
            {"label": "notes", "value": str(len(files))},
            {"label": "nodes", "value": str(len(nodes))},
            {"label": "links", "value": str(len(edges))},
            {"label": "dangling", "value": str(dangling_n),
             "tone": "bad" if dangling_n else "ok"},
        ],
        "tables": [{
            "id": "hubs",
            "title": "Highest degree",
            "columns": ["note", "leg", "degree"],
            "rows": [[r["label"], r["group"], str(r["size"])] for r in hub_rows],
        }],
        "charts": [{
            "id": "legs",
            "title": "Notes by leg",
            "type": "doughnut",
            "labels": list(legs.keys()),
            "series": [{"label": "count", "data": [int(legs[k]) for k in legs]}],
        }],
        "notes": [
            "Force graph is live [[wikilinks]] in this vault. Color = leg. Size = degree.",
            "Dangling nodes are links that do not resolve to a note.",
        ],
        "graph": {
            "nodes": list(nodes.values()),
            "edges": edges,
        },
        "source": {
            "repo": str(repo),
            "collector": "vault-graph",
            "note": repo.name,
        },
    }
