# Implementation Plan: Vault Graph v2 "Jarvis" mode

Spec: `docs/superpowers/specs/2026-09-04-vault-graph-jarvis-design.md` (approved, MOA-reviewed)
Repo: `C:/Users/bottl/hermes-artifacts` · Branch: `vault-graph-jarvis` (off `main`)

## Global Constraints (bind every task — copy verbatim into reviewer prompts)

- **No collector changes.** `tools/collectors/vault_graph_collector.py`, `tools/refresh.py`, and the desktop plugin are untouched. Payload schema stays `{graph:{nodes[],edges[]}}` with node fields `{id,label,group,size}`; edge fields `{source,target}`.
- **Node `id` = vault-relative path WITH `.md`** (e.g. `Construction.md`). Dangling nodes are prefixed `dangling:` and have no `.md`. Click handler keys off this field directly — do not add payload fields.
- **Three markers must survive in template.html**: `<!--HERMES-ARTIFACT:CSS-->`, `DATA`, `JS` (and their `/.../` closes). refresh.py raises if any is missing.
- **No build step.** Single-file HTML artifact; CDN scripts + inline JSON only. No npm, no bundler.
- **Renderer must not throw** when the payload has no `graph` key — keep the existing guard `if (d.graph && ...)`.
- **CDN-failure fallback**: if `typeof d3 === 'undefined'`, render a static one-shot layout via an internal hand-rolled sim function; tooltip + node drag still work. Same pattern as Chart.js today.
- **No silent click fallback.** Click navigates ONLY to the obsidian:// URI (never file://). Show a non-fatal toast naming what was attempted. Dangling nodes: no click action, tooltip "unresolved link".

## Verification tooling available in this repo

- `node --check <file>` — JS syntax gate (Node v22 present).
- Marker check: grep the three markers + d3 `<script>` tag out of template.html and generated index.html.
- Live refresh: `C:/Users/bottl/FinancialDevelopment/.venv/Scripts/python.exe tools/refresh.py vault-graph --repo C:/Users/bottl/obsidian-vault` then open `artifacts/vault-graph/index.html`.
- Collector regression: `python -m pytest tests/test_vault_graph_collector.py` (must stay green — proves no collector drift).

No JS unit-test runner is configured; "tests" for the renderer are syntax + marker + live-render gates. This is a deliberate, documented choice, not an omission to fix in this plan.

---

## Task 1: Template d3 tag + Jarvis CSS scaffolding

**Files:** `artifacts/vault-graph/template.html`, `assets/hermes-artifact.css`
**Depends on:** nothing (first task)

Add the d3 v7 CDN `<script>` to template.html immediately before the JS marker block, keeping all three markers intact. Add/adjust CSS in hermes-artifact.css for: graph-stage vignette background (`#05070c` base + radial gradient), restyled `.ha-gtip` tooltip (dark hologram chip), a new `.ha-ghost-toast` element style for the click toast, and legend swatch glow. Do NOT touch renderGraph() yet — this task is scaffolding only; the existing renderer must still work after it lands.

**Verify:**
1. `node --check assets/hermes-artifact.js` passes (unchanged file, sanity).
2. template.html contains all three markers AND a `<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"`.
3. CSS parses (no stray braces) — eyeball + `node --check` not applicable; confirm the new class names are present: `.ha-gstage`, `.ha-ghost-toast`.
4. Collector suite still green: `python -m pytest tests/test_vault_graph_collector.py`.

**Commit:** `feat(vault-graph): add d3 CDN tag + Jarvis CSS scaffolding`

---

## Task 2: renderGraph() rewrite — d3-force physics, canvas render, zoom/pan, hover isolation, click-to-open

**Files:** `assets/hermes-artifact.js` (renderGraph section only)
**Depends on:** Task 1 (d3 loaded; CSS classes exist)

Rewrite ONLY the graph portion of hermes-artifact.js per spec §Components. Keep renderCards/renderChart/renderTable and the top-level render() guard untouched. Implement:

- **Init**: build degree map + adjacency set from edges once. Map payload nodes → sim node objects `{id,label,group,size,x,y,vx,vy}`; links reference by id.
- **Physics** (d3-force): `forceLink` with `.strength(l => 0.5/Math.max(degA,degB))` using an `idOf(x)=typeof x==='object'?x.id:x` helper so it survives d3's string→object endpoint resolution; `forceManyBody().theta(0.9)` charge `-18*(1+Math.sqrt(size)*0.4)`; `forceCollide(r=>radius(n)+2).iterations(2)`; weak per-group `forceX/forceY` toward a point on a ~260-radius circle (strength ~0.03) for organic leg clustering. These constants are initial — tune in the live gate, not here.
- **Render** (canvas): bg fill + radial vignette + faint dot grid; edges first (`rgba(148,163,184,alpha)` base 0.10); nodes two-pass glow (`shadowBlur=12+size`, shadowColor=group color) then core fill; radius `r=3+Math.sqrt(size)*1.8`. Labels sparse: hovered/neighborhood-lit OR top ~8 by degree at rest OR zoom scale > 2 (then all visible).
- **Zoom/pan** (d3.zoom, scaleExtent [0.25,8]): draw loop maps world→screen via current transform; one shared `transform.invert()` helper for pointer↔world used by pick/hover/drag. Pointer ownership: down-on-node → node drag + stopPropagation (reheat sim alphaTarget 0.3 while held); down-on-empty → pan; click = up-with-negligible-movement on a node only.
- **Hover isolation**: neighbor set from adjacency map; lit nodes full brightness+glow, others dimmed to alpha 0.08; edges touching hovered brightened (~0.5), rest dropped to 0.03; tooltip `label · group · degree`.
- **Click-to-open** (spec §5): real node → navigate hidden `<a>` to `obsidian://open?vault=<encodeURIComponent(OBSIDIAN_VAULT)>&file=<encodeURIComponent(node.id)>` with `OBSIDIAN_VAULT='obsidian-vault'`; show `.ha-ghost-toast` naming the attempt. Dangling nodes: no action, tooltip "unresolved link".
- **Fallback**: if d3 undefined → internal hand-rolled one-shot sim (keep a compact version of today's physics), same look minus zoom/neighborhood-dim; tooltip + drag still work. Empty graph → "no links found" note instead of canvas loop.

**Verify:**
1. `node --check assets/hermes-artifact.js` passes.
2. renderCards/renderChart/renderTable and the top-level guard are byte-identical to before (diff shows only the graph section changed).
3. Live: refresh board, open index.html — clusters form organically per leg within ~5s; wheel zoom + background pan smooth at 60fps on the full 345-node/269-edge vault; hover dims non-neighbors with correct tooltip; drag repositions without triggering an open; click a real note fires the obsidian:// toast (and opens Obsidian if running); dangling node no-ops.
4. Block d3 CDN in devtools → fallback layout renders, page doesn't error.

**Commit:** `feat(vault-graph): Jarvis renderGraph — d3-force physics, zoom/pan, hover isolation, click-to-open`

---

## Task 3: Whole-board integration + live "Jarvis brain" gate (PM-verified)

**Files:** none new; runs refresh + opens the board.
**Depends on:** Tasks 1 & 2 merged into branch.

Run the full manual gate from spec §Testing item 3 end-to-end and confirm every checkbox: organic clusters, 60fps zoom/pan at scale, hover isolation, click→Obsidian (fix `OBSIDIAN_VAULT` here if it doesn't match Jason's registered vault name), drag-vs-pan arbitration, CDN-blocked fallback. Capture a screenshot of the live board as evidence. This task is PM-executed verification + any one-line constant fix; no new code expected beyond possibly correcting OBSIDIAN_VAULT.

**Verify:** all spec §Testing item 3 checkboxes ticked with a saved screenshot at `artifacts/vault-graph/jarvis-live.png` (or equivalent) as evidence.

---

## Final whole-branch review

Independent reviewer subagent reviews the full branch diff (`main..vault-graph-jarvis`) against the Global Constraints + spec: confirm no collector/refresh/plugin drift, markers intact, fallback present, no silent file:// click path, sparse labels, and that only the three intended files changed. Triage any Minor findings before merge to `main`.

## Merge / closeout

On clean final review: merge branch → main (Jason's live artifacts repo), commit the spec + plan docs alongside, refresh once more so the board is current on disk. Report the live screenshot as proof Jarvis brain lives.
