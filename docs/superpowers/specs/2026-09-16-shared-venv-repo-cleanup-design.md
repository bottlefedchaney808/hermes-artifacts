# hermes-artifacts: Shared venv + repo cleanup — Design

Date: 2026-09-16 · Repo: `C:/Users/bottl/hermes-artifacts` (origin = `bottlefedchaney808/hermes-artifacts`)

## Goal

Make the repo self-contained: one shared `.venv` at the repo root that runs
**all** suites and all refreshes, fix the two dead boards (broken E: path),
land the uncommitted board reorg, move root-level scratch into `scratch/`,
and make the GitHub copy current (push).

## Audit findings (evidence in plan doc)

1. No dependency manifest, no venv; runtime is the external
   `C:/Users/bottl/FinancialDevelopment/.venv` (Py 3.12.10) — referenced by
   README and `plugin_api.py`/`_core.py`. Three interpreters have written
   `__pycache__` (3.10/3.11/3.12).
2. `tools/collectors/kalshi_desk_collector.py` line 10 and
   `polymarket_desk_collector.py` line 14 point at
   `E:/BlackHole Investments/BlackHole/Event_Desk` (space). The real folder is
   `E:/BlackHole_Investments/BlackHole/Event_Desk` (underscore). Both boards
   render zero data; kalshi-desk/tiferet-bid-board are new and uncommitted.
3. `daily_plays_collector.py` line 102 hardcodes the repo artifact dir
   (`C:/Users/bottl/hermes-artifacts/...`) instead of deriving from `__file__`.
4. The installed desktop plugin (`C:/Users/bottl/.hermes/plugins/interactive-artifacts/`,
   multi-root with `roots.json` + `_core.py`, 2026-09-09) is NEWER than the
   repo's `plugin/` (single-root, 2026-09-03). Repo copy is stale.
5. Uncommitted reorg: 8 board folders deleted, `sentiment-scanner-board` →
   `daily-plays` rename staged, 3 new collectors + `tests/test_refresh_bid_desk.py`
   untracked. GitHub `main` still has the pre-reorg tree.
6. ~47 untracked scratch artifacts at repo root (~30 MB; `resume_ocr/` 11 MB,
   `odyssey-achilles/` 14 MB incl. an mp4).
7. Baseline (pre-change): `pytest tests -q` → 33 passed (FD venv);
   `tools/refresh.py --all` → all 6 boards OK.

## Design

### 1. Shared venv — `./.venv` (single interpreter for the whole repo)

- Python **3.12.10** (`C:/Users/bottl/AppData/Local/Programs/Python/Python312/python.exe`),
  already created at `.venv/`.
- Deps pinned in `requirements.txt` (installed via pip, then frozen):
  `pytest`, `python-docx`, `fastapi`, `pydantic`.
  - `pytest` — all suites.
  - `python-docx` — `resume_ocr/build_resume_docx.py`.
  - `fastapi` + `pydantic` — the in-repo plugin (`plugin/dashboard/plugin_api.py`).
    The desktop gateway runs the *installed* copy under its own interpreter, so
    these are for repo-side loading/testing only; including them keeps the venv
    the single interpreter that can import everything in the repo.
- `.gitignore`: add `.venv/` and `scratch/`.
- `Makefile` with `test` target:
  `".venv/Scripts/python.exe" -m pytest tests -q`
- README: every `python …` / FD-venv command replaced with `.venv/Scripts/python.exe`;
  new **Setup** section (`python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt`).
- `.hermes.md`: update the "FinancialDevelopment venv" line to the shared venv.
- `FinancialDevelopment` stays as the *data source repo* for collectors
  (that is data, not an interpreter). It is NOT replaced.

### 2. Collector path fixes (stdlib-only collectors, behavior-preserving)

- `kalshi_desk_collector.py`: `KALSHI_DESK = E:/BlackHole_Investments/BlackHole/Event_Desk`
  (primary), fallback `C:/Users/bottl/BlackHole_Investments/BlackHole/Event_Desk`
  if present.
- `polymarket_desk_collector.py`: same primary path; fallback
  `C:/Users/bottl/EventTrading` (existing dir with `data/fills.json` +
  `data/_hist_parsed.json`) when the E: path is absent.
- `daily_plays_collector.py`: `artifact_dir` default becomes
  `Path(__file__).resolve().parents[2] / "artifacts" / "daily-plays"`
  (repo-relative), overridable by param as today.
- New test `tests/test_board_paths.py`: asserts each collector's data path
  resolves to a real file on this machine and `collect()` returns a payload
  with non-degenerate data (kalshi: settlements or perps rows > 0; polymarket:
  fills/history loaded, summary present).

### 3. Scratch consolidation

- Create `scratch/` (gitignored). Move all root-level untracked scratch
  artifacts into it: `copper_*`, `fl_*`, `freelancer_*`, `spy_*`, `eval*.js`,
  `amazon_job.txt`, `bid_calendar.json`, `bid_desk_template.html`,
  `dashboard_*.json`, `fv_login.txt`, `funnel_ever.json`, `jason_*.json`,
  `job_*.txt`, `monthly.log`, `ph_stats.json`, `side.json`, `snap*.txt`,
  `split_*.log`, `submitted_by_month.json`, `watch_t_8fd742eb.sh`,
  `browseros/`, `browseros_mcp.py`, `browseros_neo_mcp.py`,
  `browseros_*_session.txt`, `resume_ocr/`, `odyssey-achilles/`, `state/`,
  `Tiferet Bid Desk v1.html`, `Tiferet Bid Desk.html`.
- `refresh_bid_desk.py` + `tests/test_refresh_bid_desk.py` are real tooling
  (offline-tested Gmail bid desk) — they stay at repo root and get committed.
- `artifacts/daily-plays/history/`, `artifacts/kalshi-desk/`,
  `artifacts/tiferet-bid-board/` stay (live boards) and get committed.
- No files are deleted; moves only.

### 4. Plugin sync (installed → repo, then back)

- Copy the installed multi-root plugin into the repo:
  `__init__.py`, `_core.py`, `dashboard/plugin_api.py`,
  `dashboard/manifest.json`, `desktop/plugin.js`, `desktop/deploy.cmd`,
  `plugin.yaml`, `roots.json` (replace the stale single-root files; keep
  `plugin/plugin.yaml` content aligned).
- In the synced `_core.py`: `PY = <repo>/.venv/Scripts/python.exe` (shared venv),
  with the existing `sys.executable` fallback kept.
- `roots.json` keeps both roots (`hermes` = this repo, `findev` =
  `C:/Users/bottl/FinancialDevelopment`, boards `artifact-boards`).
- After the repo is the source of truth, re-copy to the installed location
  (`C:/Users/bottl/.hermes/plugins/interactive-artifacts/`) so the desktop
  Refresh button uses the shared venv. Desktop app restart required for the
  swap to take effect (noted in plan; restart is user-actioned).

### 5. Board reorg commit (landed after fixes so committed data is real)

- Commit the reorg: 8 deleted board folders, `sentiment-scanner-board` →
  `daily-plays` rename, `daily-plays/history/`, new `kalshi-desk/` +
  `tiferet-bid-board/` boards, the 3 new collectors,
  `tests/test_refresh_bid_desk.py`, `refresh_bid_desk.py`.
- Before committing: run `refresh` for kalshi-desk and polymarket-desk with
  the fixed paths so committed `data.json`/`index.html` carry real data.

### 6. Push

- `git push origin main` — replaces the stale GitHub copy with the current
  Windows working tree (user-confirmed: the GitHub copy is the "older adapted
  one" to be replaced).

## Verification (must all hold at the end)

1. `.venv/Scripts/python.exe -m pytest tests -q` → all pass (33 baseline +
   `test_refresh_bid_desk.py` + new `test_board_paths.py`).
2. `.venv/Scripts/python.exe tools/refresh.py --all` → 6/6 refreshed.
3. `artifacts/kalshi-desk/data.json` → real settlements/perps (nonzero).
   `artifacts/polymarket-desk/data.json` → real W/L record (51W–15L from
   `act=Won/Lost` on the E: data).
4. `git status --porcelain` → clean (after final commit); `git ls-files` has
   no scratch files; `.venv/` and `scratch/` ignored.
5. `.venv/Scripts/python.exe -c "import fastapi, pydantic, docx, pytest"` OK.
6. `git log origin/main..main` empty after push.

## Out of scope

- `FinancialDevelopment` repo internals (data source only).
- Cloud/Linux layout (`/opt/data/...`) — keep as fallbacks.
- Hermes gateway's own venv (`C:\Users\bottl\.hermes\hermes-agent\venv`) —
  the repo venv is for repo code; the gateway keeps its environment.
- No deletions of user data; scratch = moves only.
