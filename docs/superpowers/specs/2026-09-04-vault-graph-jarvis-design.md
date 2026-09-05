# Vault Graph v2 — "Jarvis" mode

Date: 2026-09-04 · Status: ready to act on (MOA review folded in)
Repo: `hermes-artifacts` (board id `vault-graph`)

## Goal

Make the vault-graph board look and feel like a cinematic holographic brain map —
dark background, glowing group-colored nodes in organic clusters, faint edges —
matching/exceeding the Obsidian graph-view reference screenshot. Add real
interactivity: zoom/pan, neighborhood highlight on hover, click-to-open note in
Obsidian.

## Grounded facts (measured 2026-09-04)

From `artifacts/vault-graph/data.json` and the collector source — these fix the
performance section to reality instead of a guess:

- **345 nodes, 269 edges.** Group split: trading 267, development 39, dangling 19,
  construction 14, hub 3, templates 2, inbox 1. Canvas + glow is trivially cheap at
  this scale; no perf engineering needed now (see §Risks for the future guard).
- **Node `id` = vault-relative path WITH `.md`** (`Construction.md`, `Development.md`).
  Dangling nodes are prefixed: `dangling:<raw target>` and carry **no** `.md`.
  The click handler keys off this field directly — no new payload fields.

## Non-goals (YAGNI)

- No new board id; no collector changes; no payload schema change (`graph.nodes` / `graph.edges` stay as-is).
- No search box, no legend toggles, no minimap, no export.
- No build step — still a single-file HTML artifact with CDN scripts and inline JSON.

## Architecture

All work lives in the universal renderer + CSS:

| File | Change |
|---|---|
| `assets/hermes-artifact.js` → `renderGraph()` | Full rewrite of graph section only (lines ~131–290). Everything else (`renderCards`, `renderChart`, `renderTable`) untouched. |
| `artifacts/vault-graph/template.html` | Add one `<script>` tag for d3 v7 CDN before the JS marker block. Keep all three `HERMES-ARTIFACT` markers intact (refresh.py validates their presence — a missing marker raises). |
| `assets/hermes-artifact.css` | Graph-stage styles: vignette background, tooltip restyle, legend swatch glow, click toast. |

No changes to `tools/refresh.py`, collectors, or the desktop plugin.

## Components

### 1. Physics — d3-force (CDN)

- Load `https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js` in template.html.
- Replace hand-rolled O(n²) sim with:
  - **Precompute a degree map** (`id → out+in count`) from edges at init — reused by both the link-strength function and hover adjacency, so it's built once.
  - `d3.forceLink(links).id(d => d.id)` with `.distance(46)` and
    `.strength(l => { const s = idOf(l.source), t = idOf(l.target); return 0.5 / Math.max(deg[s], deg[t]); })` — hub links pull less so hubs don't collapse into a ball. `idOf(x) = typeof x === 'object' ? x.id : x` because d3 resolves string endpoints to node objects only after init; the strength fn must survive both forms.
  - `d3.forceManyBody().theta(0.9)` with per-node charge `-18 * (1 + Math.sqrt(size) * 0.4)` — bigger nodes push harder → organic spacing.
  - `d3.forceCollide(r => radius(n) + 2).iterations(2)`.
  - **Group cohesion**: each group gets an angle on a circle of radius ~260; apply weak `forceX/forceY` toward that point (strength ~0.03). Preserves leg clustering without rigid pinning — clusters form organically like the reference instead of sitting in fixed circles.
- Simulation ticks drive a canvas draw loop via `requestAnimationFrame`; sim alpha decays naturally and re-heats on drag (`sim.alphaTarget(0.3)` during, back to 0 on release).

> **Tuning note:** charge magnitude, link distance (46), cohesion radius (~260) and
> strength (0.03) are *initial* values — force constants are empirical. Tune them in
> the manual gate against the reference screenshot until clusters read as organic;
> don't treat these numbers as final.

### 2. Rendering — canvas (not SVG)

Canvas for performance:

- Background fill `#05070c` + radial vignette gradient (slightly lighter center, darker edges); faint dot grid at low alpha for hologram depth.
- Edges first: stroke `rgba(148,163,184,alpha)`, base alpha 0.10; boosted to 0.5 when an endpoint is in the hovered neighborhood (see §4).
- Nodes two-pass — (a) glow pass with `ctx.shadowBlur = 12 + size`, shadowColor = group color; (b) core fill at full opacity. Radius `r = 3 + Math.sqrt(size) * 1.8`.
- **Labels kept sparse to match the reference** (the screenshot is almost all dots): draw a label only when the node is hovered / in the lit neighborhood, OR it's among the top ~8 by degree at rest, OR zoom scale > 2 (then label everything visible). Font 11px, color `#e5e7eb`, alpha per dim state.

### 3. Zoom / pan — d3.zoom on canvas + event arbitration

`d3.zoom().scaleExtent([0.25, 8])`; the draw loop maps world→screen through the current transform (translate + scale). **Pointer ownership is explicit** so zoom and node-drag don't fight over events:

- **Pointer down ON a node → node drag.** `stopPropagation()` so canvas pan does not also start. Drag repositions that node (`sim.alphaTarget(0.3)` while held, 0 on release).
- **Pointer down on EMPTY canvas → pan** (d3.zoom default behavior).
- **Click = pointer up with negligible movement:** on a node → open note (§5); on empty space → no-op. A real drag suppresses the click so dragging a node never accidentally opens it.

### 4. Hover — neighborhood isolation ("Jarvis point")

On hover of node N:
- Neighbor set = {N} ∪ direct-link endpoints (from the precomputed adjacency map).
- Nodes in set: full brightness + glow; all others dimmed to alpha 0.08.
- Edges touching N brightened (alpha ~0.5); all others dropped to 0.03.
- Tooltip follows cursor: `label · group · degree` (existing tooltip element, restyled).

### 5. Click — open note in Obsidian

A browser **cannot detect** whether a custom-scheme navigation succeeded, and opening arbitrary `file://` paths from an artifact may be blocked by the host security model — so there is **no silent fallback**. Behavior:

- On click of a real node (id not starting with `dangling:`), navigate to
  ```text
  obsidian://open?vault=<encodeURIComponent(OBSIDIAN_VAULT)>&file=<encodeURIComponent(node.id)>
  ```
  via hidden `<a>`. Use **`node.id` verbatim** — it already carries the vault-relative path *with* `.md`, which Obsidian accepts. (If manual gate shows Obsidian wants no extension, strip a trailing `.md` in one place.)
- `OBSIDIAN_VAULT = 'obsidian-vault'` is an explicit config constant at top of `renderGraph`. It must equal the vault's **registered name** in Obsidian settings (the folder-name default; this machine's registry file exposes no display override to read programmatically). If it doesn't match, the URI opens nothing — so:
- On every click also show a brief non-fatal toast naming what was attempted (`Opening '<note>' in vault 'obsidian-vault'…`) and, if the note didn't visibly open, the user knows the constant must be corrected. This is honest feedback instead of pretending detection works.
- **Dangling nodes** (group `dangling`): no click action; tooltip reads "unresolved link".

### 6. Fallbacks / error handling

- **CDN unreachable** (`typeof d3 === 'undefined'`): render a static one-shot layout using the existing hand-rolled sim kept as an internal fallback function (same look, minus zoom/neighborhood-dim; tooltip + drag still work). Same pattern as Chart.js today.
- **Empty graph**: show "no links found" note in stage instead of starting the canvas loop.
- Renderer must not throw if `graph` key absent — current guard stays (`if (d.graph && ...)`).

## Data flow (unchanged)

```
vault_graph_collector.py → refresh.py → inline JSON payload (schema v1 + graph extra)
→ template.html markers inject CSS/JS/DATA → hermes-artifact.js renderGraph()
```

Collector output contract: `graph.nodes[] {id, label, group, size}`, `graph.edges[] {source, target}`. No new fields required.

## Testing / verification

1. **Unit**: run existing suite to prove zero collector regression (`python -m pytest tests/`). Collector is untouched; no new unit cases expected — add one only if a behavior changes.
2. **Renderer smoke test** (new): assert `template.html` still contains all three markers and the d3 `<script>` tag, and that `node --check assets/hermes-artifact.js` passes syntax.
3. **Manual gate**: refresh board (`tools/refresh.py vault-graph`), open in Desktop Interactive pane:
   - [ ] Clusters form organically per leg within ~5s of load (no rigid circles) — tune force constants here if not
   - [ ] Wheel zoom + background pan smooth at 60fps with the full 345-node / 269-edge vault
   - [ ] Hover dims non-neighbors; tooltip correct
   - [ ] Click a real note → Obsidian opens it (fix `OBSIDIAN_VAULT` here if not); click dangling node → no-op + "unresolved link"
   - [ ] Drag a node repositions it without triggering an open; drag on empty space pans
   - [ ] Block CDN in devtools → fallback layout still renders, page doesn't error

## Risks

- **d3.zoom + d3.drag event conflict** — the fiddliest part. Mitigation: explicit pointer ownership per §3 (node-drag stops propagation; pan only on empty space) and one shared `transform.invert()` helper for all screen↔world mapping used by pick, hover, and drag.
- **Performance at current scale is a non-issue** (345/269). Future guard: if the vault grows past ~1500 nodes, drop the glow pass below zoom scale 2 and skip the grid — add only when measured slow, not now.
- **Obsidian vault name mismatch → click opens nothing.** Mitigation: explicit `OBSIDIAN_VAULT` constant + honest toast (§5) + verify in manual gate on Jason's machine where Obsidian runs.

## Out of scope for this spec (future, if wanted)

Legend-as-filter toggles, search-to-focus, "open all neighbors" batch action, per-note metadata coloring beyond leg.
