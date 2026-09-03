# hermes-artifacts

Universal, repo-agnostic **interactive artifacts**: single-file HTML dashboards
that render in the Hermes desktop app (`::preview`), any browser, or anywhere.
Replaces the static mockups that lived in `C:/Users/bottl/Claude/Artifacts/`.

## What an artifact is

One folder under `artifacts/` containing:

| File | Role |
|---|---|
| `artifact.json` | manifest: `id`, `title`, `collector`, `repo`, `description` |
| `template.html` | skeleton with `<!--HERMES-ARTIFACT:CSS/DATA/JS-->` markers |
| `data.json` | written by refresh — the canonical payload |
| `index.html` | written by refresh — fully self-contained (CSS/JS/data inlined) |

**No sibling fetches, no build step.** The only external dependency is the
Chart.js CDN; offline it degrades to tables/notes with a note instead of blank
boxes.

## Data contract (schema v1)

A collector returns a dict; `refresh.py` stamps `schema_version`,
`artifact_id`, `title`, `generated_at` on top:

```json
{
  "summary": [{"label": "rows", "value": "42", "tone": "ok|bad"}],
  "tables":  [{"id": "t", "title": "T", "columns": ["a"], "rows": [["1"]]}],
  "charts":  [{"id": "c", "title": "C", "type": "line|bar|doughnut",
               "labels": ["Mon"], "series": [{"label": "s", "data": [1]}]}],
  "notes":   ["plain strings"],
  "source":  {"repo": "...", "collector": "...", "note": "file used"}
}
```

## Adding an artifact for ANY repo

1. `mkdir artifacts/<id>` — add `artifact.json` (+ copy a `template.html`,
   change the `<title>`).
2. Write `tools/collectors/<name>_collector.py` — a `@register("<name>")
   collect(repo_path)` returning the payload body (stdlib only, read-only).
3. `python tools/refresh.py <id>` — done.

The shell renders whatever fits the schema; anything that doesn't fit becomes
a table row or a note. `--repo <path>` points any artifact at a different
repository for a one-off refresh.

## Refresh

```bash
python tools/refresh.py --list                 # show artifact ids
python tools/refresh.py var-simulations-digest # one
python tools/refresh.py --all                  # every artifact
python tools/refresh.py dev-knowledge-roadmap --repo C:/path/to/other/repo
```

In chat: **ask Hermes to "refresh <artifact-id>"** — it runs the command and
delivers `::preview{file="artifacts/<id>/index.html"}`.

## Tests

```bash
C:/Users/bottl/FinancialDevelopment/.venv/Scripts/python.exe -m pytest tests -q
```

## Conventions

- Collectors are **stdlib-only** and strictly **read-only** against their
  source repo (`sqlite3 mode=ro`, index-only counts on huge tables).
- Charts: vivid, full-opacity series (palette in `hermes-artifact.js`).
- Styling uses the Hermes `::preview` theme vars (`--foreground`, `--card`,
  `--border`, `--muted-foreground`) with fallbacks so standalone rendering
  stays readable; never hardcode frame backgrounds.
