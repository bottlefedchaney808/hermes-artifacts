# Shared venv + repo cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One repo-local `.venv` runs all suites and refreshes; dead boards fixed; reorg committed; scratch moved to `scratch/`; GitHub updated.

**Architecture:** Repo-local Python 3.12.10 venv + `requirements.txt` + `Makefile` as the single runtime. Collectors get corrected source paths (E: folder renamed to `BlackHole_Investments`). Installed desktop plugin (newer, multi-root) is synced back into the repo as the source of truth, with its interpreter pointer switched to the shared venv.

**Tech Stack:** Python 3.12.10, pytest, python-docx, fastapi, pydantic, git.

**Spec:** `docs/superpowers/specs/2026-09-16-shared-venv-repo-cleanup-design.md`

## Global Constraints

- Repo root: `C:/Users/bottl/hermes-artifacts`. All commands run from there.
- Shared interpreter: `.venv/Scripts/python.exe` (created from
  `C:/Users/bottl/AppData/Local/Programs/Python/Python312/python.exe` → 3.12.10).
- No deletions of user data — scratch files are MOVED to `scratch/`, never deleted.
- Collectors stay **stdlib-only** and **read-only** against source repos.
- `FinancialDevelopment` remains the FD *data* source; its venv is NOT the repo runtime anymore.
- E: drive real path: `E:/BlackHole_Investments/BlackHole/Event_Desk` (underscore, NOT space).
- Every git commit ends with a green `.venv/Scripts/python.exe -m pytest tests -q`.

---

### Task 1: Shared venv, manifest, Makefile, docs

**Files:**
- Create: `requirements.txt`, `Makefile`
- Modify: `.gitignore`, `README.md`, `.hermes.md`
- (`.venv/` already exists, created 2026-09-16 from Python 3.12.10)

**Interfaces:**
- Consumes: Python 3.12.10 at `C:/Users/bottl/AppData/Local/Programs/Python/Python312/python.exe`
- Produces: `.venv/Scripts/python.exe` usable for pytest + refresh + all imports; `make test` target.

- [ ] **Step 1: Install deps into the existing venv**

Run:
```
cd C:/Users/bottl/hermes-artifacts
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install pytest python-docx fastapi pydantic
```
Expected: all four install or already satisfied.

- [ ] **Step 2: Write `requirements.txt`**

```
# Shared runtime for hermes-artifacts: all suites + refresh + in-repo plugin.
# Create: .venv (Python 3.12) —  .venv/Scripts/python.exe -m pip install -r requirements.txt
pytest>=9
python-docx>=1.1
fastapi>=0.115
pydantic>=2.7
```

- [ ] **Step 3: Verify every import the repo uses resolves in the venv**

Run:
```
.venv/Scripts/python.exe -c "import pytest, docx, fastapi, pydantic; import sys; print(sys.version)"
```
Expected: no ImportError; prints 3.12.10.

- [ ] **Step 4: Update `.gitignore`**

Append to existing `.gitignore` (currently `__pycache__/` and `*.pyc`):
```
.venv/
scratch/
```

- [ ] **Step 5: Create `Makefile`**

```make
PY := .venv/Scripts/python.exe

.PHONY: test refresh

test:
	$(PY) -m pytest tests -q

refresh:
	$(PY) tools/refresh.py --all
```

- [ ] **Step 6: Run the full suite from the shared venv**

Run:
```
.venv/Scripts/python.exe -m pytest tests -q
```
Expected: 33 passed (baseline before new tests land).

- [ ] **Step 7: Update `README.md`**

Replace the Tests section (currently line ~103–105):
```markdown
## Tests

```bash
.venv/Scripts/python.exe -m pytest tests -q
```
```
Add a Setup section before it:
```markdown
## Setup

```bash
python -m venv .venv                      # Python 3.12
.venv/Scripts/python.exe -m pip install -r requirements.txt
```

All suites and refreshes run from the repo-local `.venv` — never from a
sibling repo's venv.
```
In the Live streaming section (line ~75), replace
`/opt/data/FinancialDevelopment/.venv/bin/python` with
`.venv/Scripts/python.exe` and note the Linux equivalent in a comment.

- [ ] **Step 8: Update `.hermes.md`**

Replace the line
`Refresh: `tools/refresh.py` using the FinancialDevelopment venv when a collector needs FD data.`
with
`Refresh: `tools/refresh.py`, run from the repo-local `.venv` (`make test` / `make refresh`). FinancialDevelopment is a data source, not an interpreter.`

- [ ] **Step 9: Commit**

```
git add requirements.txt Makefile .gitignore README.md .hermes.md
git commit -m "chore: single shared .venv for all suites (requirements, Makefile, docs)"
```

---

### Task 2: Fix dead board paths (kalshi + polymarket) with tests

**Files:**
- Modify: `tools/collectors/kalshi_desk_collector.py:10`
- Modify: `tools/collectors/polymarket_desk_collector.py:13-16`
- Test: `tests/test_board_paths.py` (create)

**Interfaces:**
- Consumes: real data at `E:/BlackHole_Investments/BlackHole/Event_Desk/kalshi_btc15m/data/{bucket_clip_log.jsonl,perps_tape.jsonl}` and `.../data/{fills.json,_hist_parsed.json}`; fallback `C:/Users/bottl/EventTrading/data/{fills.json,_hist_parsed.json}`.
- Produces: `kalshi_desk_collector.collect()` → payload with nonzero settlements/perps; `polymarket_desk_collector.collect()` → payload with real W/L record.

- [ ] **Step 1: Write the failing test**

Create `tests/test_board_paths.py`:
```python
"""Board collectors must resolve real data paths (E: folder was renamed)."""
from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))

import collectors  # noqa: E402
import collectors.kalshi_desk_collector as kalshi  # noqa: E402
import collectors.polymarket_desk_collector as poly  # noqa: E402


def test_kalshi_data_paths_exist():
    assert kalshi.BUCKET_LOG.is_file(), f"missing {kalshi.BUCKET_LOG}"
    assert kalshi.PERPS_TAPE.is_file(), f"missing {kalshi.PERPS_TAPE}"


def test_kalshi_collect_has_data():
    payload = kalshi.collect()
    tables = {t["title"]: t for t in payload.get("tables", [])}
    rows = sum(len(t.get("rows", [])) for t in tables.values())
    assert rows > 0, "kalshi board rendered zero rows — data path broken"


def test_polymarket_data_paths_exist():
    assert poly.POLY_FILLS.is_file(), f"missing {poly.POLY_FILLS}"
    assert poly.HIST_PARSED.is_file(), f"missing {poly.HIST_PARSED}"


def test_polymarket_collect_has_record():
    payload = poly.collect()
    summary = {s["label"].lower(): s["value"] for s in payload.get("summary", [])}
    assert "record" in summary, f"no record summary: {summary}"
    # the E: history has settled Won/Lost trades — record must not be 0W–0L
    assert summary["record"] != "0W–0L", f"zeroed record: {payload.get('summary')}"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_board_paths.py -v`
Expected: `test_kalshi_data_paths_exist` FAIL (path with space missing);
`test_polymarket_data_paths_exist` FAIL (same).

- [ ] **Step 3: Fix `kalshi_desk_collector.py`**

Replace line 10:
```python
KALSHI_DESK = Path("E:/BlackHole Investments/BlackHole/Event_Desk")
```
with:
```python
def _find_desk() -> Path:
    for p in (Path("E:/BlackHole_Investments/BlackHole/Event_Desk"),
              Path("C:/Users/bottl/BlackHole_Investments/BlackHole/Event_Desk")):
        if p.exists():
            return p
    return Path("E:/BlackHole_Investments/BlackHole/Event_Desk")

KALSHI_DESK = _find_desk()
```

- [ ] **Step 4: Fix `polymarket_desk_collector.py`**

Replace lines 13–16:
```python
# New E: drive layout: EventTrading is nested inside BlackHole monorepo
POLY_REPO = Path("E:/BlackHole Investments/BlackHole/Event_Desk")
POLY_FILLS = POLY_REPO / "data" / "fills.json"
HIST_PARSED = POLY_REPO / "data" / "_hist_parsed.json"
```
with:
```python
# E: drive layout (2026-09): folder renamed BlackHole Investments -> BlackHole_Investments.
# Falls back to the C: EventTrading clone if the E: volume is absent.
def _find_poly() -> Path:
    for p in (Path("E:/BlackHole_Investments/BlackHole/Event_Desk"),
              Path("C:/Users/bottl/EventTrading")):
        if (p / "data" / "_hist_parsed.json").is_file():
            return p
    return Path("E:/BlackHole_Investments/BlackHole/Event_Desk")

POLY_REPO = _find_poly()
POLY_FILLS = POLY_REPO / "data" / "fills.json"
HIST_PARSED = POLY_REPO / "data" / "_hist_parsed.json"
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_board_paths.py -v`
Expected: 4 passed. (If kalshi `collect()` still shows 0 rows, the bucket
log entries exist but none are settled — then assert perps rows > 0 instead
of total rows; adjust `test_kalshi_collect_has_data` to check
`"Perps Prices (by 24h Volume)"` table rows > 0.)

- [ ] **Step 6: Full suite green**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: 37 passed (33 baseline + 4 new).

- [ ] **Step 7: Commit**

```
git add tools/collectors/kalshi_desk_collector.py tools/collectors/polymarket_desk_collector.py tests/test_board_paths.py
git commit -m "fix(collectors): E: desk path renamed to BlackHole_Investments (kalshi + polymarket boards were dead)"
```

---

### Task 3: Repo-relative artifact dir in daily_plays collector

**Files:**
- Modify: `tools/collectors/daily_plays_collector.py:99-103`

**Interfaces:**
- Produces: `collect(repo_path, artifact_dir=None)` → history saved under `<repo>/artifacts/daily-plays/history/` derived from `__file__`, not a hardcoded C: path.

- [ ] **Step 1: Replace the hardcoded path**

Replace:
```python
    # Save to history
    if artifact_dir is None:
        artifact_dir = Path("C:/Users/bottl/hermes-artifacts/artifacts/daily-plays")
```
with:
```python
    # Save to history — repo-relative (collector lives in tools/collectors/).
    if artifact_dir is None:
        artifact_dir = Path(__file__).resolve().parents[2] / "artifacts" / "daily-plays"
```

- [ ] **Step 2: Verify refresh still works and suite is green**

Run:
```
.venv/Scripts/python.exe tools/refresh.py daily-plays
.venv/Scripts/python.exe -m pytest tests -q
```
Expected: `refreshed daily-plays`; 37 passed.

- [ ] **Step 3: Commit**

```
git add tools/collectors/daily_plays_collector.py
git commit -m "fix(daily-plays): derive history dir from __file__ instead of hardcoded path"
```

---

### Task 4: Move root-level scratch into `scratch/`

**Files:**
- Create: `scratch/` (gitignored via Task 1)
- Move: ~47 untracked root files/dirs (see list below). No deletions.

**Interfaces:**
- Produces: clean repo root — only tracked content + committed tooling + `scratch/`.

- [ ] **Step 1: Move scratch artifacts**

From the repo root:
```bash
mkdir -p scratch
# data blobs
mv copper_err.txt copper_events.json copper_new_opps.json copper_opp_stages.json \
   copper_raw.json copper_velocity.json funnel_ever.json ph_stats.json \
   dashboard_data.json dashboard_payload.json dashboard_payload_v2.json \
   fl_detail.json fl_fullscope.json fl_jobs.json fl_login.txt fl_login2.png \
   fl_ranked.json fl_scrape.json fl_shortlist.json fl_sweep.json fl_sweep2.json \
   2>/dev/null
mv freelancer_detail_2026-09-06b.json freelancer_proposals_2026-09-06.md \
   freelancer_sweep_2026-09-06b.json fv_login.txt jason_bids.json jason_live.json \
   spy_dealer_exposure.json spy_run_20260905.err spy_run_20260905.json \
   spy_suite_run_20260905.html submitted_by_month.json side.json 2>/dev/null
# job notes / evals / logs
mv amazon_job.txt bid_calendar.json bid_desk_template.html eval.js eval2.js eval3.js \
   eval4.js job_excel.txt job_py.txt monthly.log snap.txt snap2.txt \
   split_dryrun.log split_run.log watch_t_8fd742eb.sh \
   "Tiferet Bid Desk v1.html" "Tiferet Bid Desk.html" 2>/dev/null
# dirs
mv browseros browseros_mcp.py browseros_neo_mcp.py browseros_neo_session.txt \
   browseros_session.txt resume_ocr odyssey-achilles state 2>/dev/null
```
(If any name differs on disk, `git status --porcelain | grep '^??'` is the source of truth — move exactly those, minus the items in Step 2.)

- [ ] **Step 2: Keep real tooling at root**

Do NOT move: `refresh_bid_desk.py`, `tests/`, `tools/`, `artifacts/`,
`templates/`, `assets/`, `plugin/`, `docs/`, `.venv/`, `Makefile`,
`requirements.txt`, `.gitignore`, `.hermes.md`, `README.md`.

- [ ] **Step 3: Verify**

Run: `git status --porcelain`
Expected: no `??` entries except `scratch/`-adjacent nothing (scratch/ is
gitignored → invisible), plus the still-uncommitted reorg items (Task 5).

- [ ] **Step 4: Commit (gitignore already covers scratch/; nothing to add)**

Nothing to commit in this task if `scratch/` is ignored — verify
`git check-ignore scratch` prints `scratch`. No commit needed; the next task
commits the reorg.

---

### Task 5: Commit the board reorg with real board data

**Files:**
- Commit: staged rename (sentiment-scanner-board → daily-plays), 8 deleted board
  folders, `artifacts/daily-plays/history/`, `artifacts/kalshi-desk/`,
  `artifacts/tiferet-bid-board/`, `tools/collectors/{daily_plays,kalshi_desk,tiferet_bid_board}_collector.py`,
  `tests/test_refresh_bid_desk.py`, `refresh_bid_desk.py`

**Interfaces:**
- Consumes: Tasks 2–3 (fixed collectors).
- Produces: `main` containing the 6-board set with live data.

- [ ] **Step 1: Refresh all boards so committed data is real**

Run: `.venv/Scripts/python.exe tools/refresh.py --all`
Expected: 6/6 `refreshed …`; kalshi-desk and polymarket-desk now carry real data.

- [ ] **Step 2: Sanity-check the two previously-dead boards**

Run:
```
.venv/Scripts/python.exe -c "
import json
for b in ('kalshi-desk','polymarket-desk'):
    d = json.load(open(f'artifacts/{b}/data.json', encoding='utf-8'))
    print(b, '->', [s['value'] for s in d['summary'][:3]],
          'tables:', {t['title']: len(t['rows']) for t in d.get('tables', [])})
"
```
Expected: kalshi has nonzero perps/settlements rows; polymarket record ≠ 0W–0L.

- [ ] **Step 3: Stage and commit the reorg**

```
git add -A artifacts tools tests refresh_bid_desk.py
git commit -m "feat(boards): land 6-board reorg (daily-plays, kalshi-desk, tiferet-bid-board) with fixed data paths"
```

- [ ] **Step 4: Verify suite + status**

Run:
```
.venv/Scripts/python.exe -m pytest tests -q
git status --porcelain
```
Expected: 37 passed; porcelain shows only ignored/nothing or the pending Task 6 files.

---

### Task 6: Sync plugin (installed multi-root → repo), point it at the shared venv

**Files:**
- Create/replace: `plugin/__init__.py`, `plugin/_core.py`, `plugin/dashboard/plugin_api.py`,
  `plugin/dashboard/manifest.json`, `plugin/desktop/plugin.js`,
  `plugin/desktop/deploy.cmd`, `plugin/roots.json`
- Modify: `plugin/plugin.yaml`
- Modify (installed copy): `C:/Users/bottl/.hermes/plugins/interactive-artifacts/_core.py`

**Interfaces:**
- Produces: repo `plugin/` = installed multi-root plugin; `PY` in `_core.py` =
  `<repo>/.venv/Scripts/python.exe` (with `sys.executable` fallback retained).

- [ ] **Step 1: Copy installed plugin into the repo**

```
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/__init__.py plugin/__init__.py
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/_core.py plugin/_core.py
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/dashboard/plugin_api.py plugin/dashboard/plugin_api.py
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/dashboard/manifest.json plugin/dashboard/manifest.json
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/desktop/plugin.js plugin/desktop/plugin.js
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/desktop/deploy.cmd plugin/desktop/deploy.cmd
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/roots.json plugin/roots.json
cp /c/Users/bottl/.hermes/plugins/interactive-artifacts/plugin.yaml plugin/plugin.yaml
```

- [ ] **Step 2: Point `PY` at the shared venv in the repo copy**

In `plugin/_core.py`, replace:
```python
PY = Path(r"C:/Users/bottl/FinancialDevelopment/.venv/Scripts/python.exe")
```
with:
```python
PY = Path(__file__).resolve().parents[1] / ".venv/Scripts/python.exe"
```
(`_core.py` lives at `<repo>/plugin/_core.py` after the copy; adjust to
`parents[1]` so it resolves to the repo root. If the plugin loads `_core.py`
from the *installed* dir at runtime, the installed copy keeps its own path
logic — Step 4 handles that.)

- [ ] **Step 3: Update the installed copy's `PY` the same way, but resolved from roots**

In `C:/Users/bottl/.hermes/plugins/interactive-artifacts/_core.py`, replace the
hardcoded PY line with logic that prefers the hermes-artifacts repo venv:
```python
_PY_REPO = Path(r"C:/Users/bottl/hermes-artifacts/.venv/Scripts/python.exe")
PY = _PY_REPO if _PY_REPO.is_file() else Path(sys.executable)
```
(`sys` is already imported in `_core.py`; if not, add `import sys`.)

- [ ] **Step 4: Verify the plugin still imports and the venv it points at runs refresh**

Run:
```
.venv/Scripts/python.exe -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('ia_core', 'plugin/_core.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print('PY ->', m.PY, m.PY.is_file())
assert m.PY.is_file()
"
.venv/Scripts/python.exe tools/refresh.py model-usage
```
Expected: `PY -> C:\Users\bottl\hermes-artifacts\.venv\Scripts\python.exe True`; `refreshed model-usage`.

- [ ] **Step 5: Commit**

```
git add plugin
git commit -m "feat(plugin): sync multi-root plugin from install, point refresh at shared .venv"
```

- [ ] **Step 6: Note for the user**

The desktop app must be restarted (or plugins reloaded) for the installed
`_core.py` change to take effect. Tell the user: "restart Hermes desktop once
so the Refresh button uses the repo venv."

---

### Task 7: Push + final verification

**Files:** none (git ops + checks)

- [ ] **Step 1: Full verification suite**

Run:
```
.venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe tools/refresh.py --all
.venv/Scripts/python.exe -c "import fastapi, pydantic, docx, pytest; print('imports ok')"
git status --porcelain
```
Expected: 37 passed; 6/6 refreshed; imports ok; clean tree (nothing but ignored).

- [ ] **Step 2: Push**

Run: `git push origin main`
Expected: `main` updated on GitHub (replaces the stale adapted copy — user confirmed).

- [ ] **Step 3: Verify remote parity**

Run: `git log --oneline origin/main..main`
Expected: empty output.
