"""Dev Knowledge Roadmap — newest markdown knowledge in ANY repo (mtime-ranked)."""
from __future__ import annotations

import time
from pathlib import Path

from collectors import register

DEFAULT_REPO = Path("C:/Users/bottl/FinancialDevelopment")
SCAN_DIRS = ("trading_journal", "docs", ".hermes/plans")


@register("dev-roadmap")
def collect(repo_path: Path = DEFAULT_REPO) -> dict:
    md = []
    for sub in SCAN_DIRS:
        base = repo_path / sub
        if base.exists():
            md += [p for p in base.rglob("*.md") if p.is_file()]
    if not md:
        # Universality fallback: the repo doesn't have our SCAN_DIRS —
        # take newest *.md anywhere in it (capped for huge trees).
        md = sorted(repo_path.rglob("*.md"), key=lambda p: p.stat().st_mtime,
                    reverse=True)[:200]
        if ".git" in str(repo_path):
            md = [p for p in md if ".git" not in p.parts]
    md.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    rows = []
    for p in md[:20]:
        head = ""
        try:
            for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("# "):
                    head = line[2:].strip()
                    break
        except OSError:
            head = "(unreadable)"
        st = p.stat()
        rows.append([p.relative_to(repo_path).as_posix(),
                     time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                     f"{st.st_size:,} B", head])
    return {"summary": [{"label": "tracked markdown", "value": str(len(md))}],
            "tables": [{"id": "recent", "title": "Newest notes",
                        "columns": ["file", "mtime", "size", "title"], "rows": rows}],
            "charts": [],
            "notes": ["Top 20 newest .md across trading_journal/, docs/, "
                      ".hermes/plans/ of the source repo."],
            "source": {"repo": str(repo_path), "collector": "dev-roadmap",
                       "note": "mtime-ranked"}}
