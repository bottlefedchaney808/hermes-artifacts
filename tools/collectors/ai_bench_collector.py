"""AI bench scorecard — reads the ai-bench suite's results + run history.

Source repo layout (repo_path from the manifest, `--repo` overrides):
  results/results.json   latest run: [ {name, tasks: {task: {metric, score, correct/total,...}}}, ... ]
  results/history.jsonl  one line per bench.py run: {ts, models: {name: {task: score, overall}}}
  models.json            endpoint metadata (base_url per model name)

Read-only, stdlib only.
"""
from __future__ import annotations

import json
from pathlib import Path

from collectors import register

TASK_ORDER = ["gsm8k", "hellaswag", "mmlu", "humaneval", "ifeval"]
TASK_LABEL = {
    "gsm8k": "GSM8K (math)",
    "hellaswag": "HellaSwag (stories)",
    "mmlu": "MMLU (knowledge)",
    "humaneval": "HumanEval (code)",
    "ifeval": "IFEval (instructions)",
}
MAX_RUNS = 40          # history charts/tables keep at most this many runs


def _load(root: Path, rel: str):
    p = root / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _load_history(root: Path):
    p = root / "results" / "history.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _pct(x, nd=1):
    try:
        return f"{float(x) * 100:.{nd}f}%"
    except (TypeError, ValueError):
        return "–"


def _num(x):
    try:
        return round(float(x) * 100, 2)
    except (TypeError, ValueError):
        return None


def _detail_cell(task, res):
    if not isinstance(res, dict):
        return "–"
    if "correct" in res:
        return f"{res.get('correct', '?')}/{res.get('total', '?')}"
    if "passed" in res:
        denom = res.get("total") or (res.get("passed", 0) + res.get("failed", 0))
        return f"{res.get('passed', '?')}/{denom}"
    if task == "ifeval":
        return f"{res.get('passed', '?')}p / {res.get('failed', '?')}f / {res.get('na', '?')}na"
    return "–"


def _run_label(i, ts):
    ts = (ts or "").strip()
    short = ts[5:16].replace("-", "-").replace("T", " ")
    return f"#{i + 1} {short}"


@register("ai-bench")
def collect(repo_path=None) -> dict:
    root = Path(repo_path) if repo_path else Path("/home/zinko83/ai-bench")
    results = _load(root, "results/results.json")
    history = _load_history(root)
    models_cfg = _load(root, "models.json") or []
    endpoints = {m.get("name"): m.get("base_url", "?") for m in models_cfg if isinstance(m, dict)}

    if not results:
        return {
            "summary": [{"label": "State", "value": "no runs yet", "tone": "bad"}],
            "tables": [],
            "charts": [],
            "notes": [f"Run the bench first: .venv/bin/python bench.py  (in {root})"],
            "source": {"repo": str(root), "collector": "ai-bench"},
        }

    names = [m.get("name", "?") for m in results]
    tasks_present = [t for t in TASK_ORDER
                     if any(t in m.get("tasks", {}) for m in results)]

    # ---- summary cards -------------------------------------------------
    latest_overall = {}
    for m in results:
        vals = [m["tasks"][t]["score"] for t in tasks_present
                if t in m.get("tasks", {}) and isinstance(m["tasks"][t].get("score"), (int, float))]
        if vals:
            latest_overall[m["name"]] = sum(vals) / len(vals)
    best = max(latest_overall.items(), key=lambda kv: kv[1]) if latest_overall else None
    last_ts = history[-1].get("ts", "?") if history else "?"

    summary = [
        {"label": "Models (latest run)", "value": str(len(results))},
        {"label": "Tasks", "value": f"{len(tasks_present)} / {len(TASK_ORDER)}"},
        {"label": "Runs recorded", "value": str(len(history) or 1),
         "tone": "ok" if history else None},
        {"label": "Last run", "value": last_ts.split(" ")[0] if last_ts != "?" else "–"},
    ]
    if best:
        summary.insert(2, {"label": f"Best overall", "value": _pct(best[1]), "tone": "ok"})
        summary.insert(3, {"label": "Leader", "value": best[0], "tone": "accent"})

    # ---- tables ---------------------------------------------------------
    scorecard = {
        "title": "Scorecard — latest run",
        "columns": ["model"] + [TASK_LABEL[t] for t in tasks_present] + ["overall"],
        "rows": [],
    }
    for m in results:
        row = [m["name"]]
        for t in tasks_present:
            row.append(_pct(m.get("tasks", {}).get(t, {}).get("score")))
        ov = [m["tasks"][t]["score"] for t in tasks_present
              if t in m.get("tasks", {}) and isinstance(m.get("tasks", {}).get(t, {}).get("score"), (int, float))]
        row.append(_pct(sum(ov) / len(ov)) if ov else "–")
        scorecard["rows"].append(row)

    detail = {
        "title": "Latest run — detail",
        "columns": ["model", "task", "metric", "score", "right/wrong", "seconds", "endpoint"],
        "rows": [],
    }
    for m in results:
        ep = endpoints.get(m["name"], "?")
        for t in tasks_present:
            res = m.get("tasks", {}).get(t)
            if not isinstance(res, dict):
                continue
            detail["rows"].append([
                m["name"], TASK_LABEL.get(t, t), res.get("metric", ""),
                _pct(res.get("score")), _detail_cell(t, res),
                str(res.get("n_seconds", "–")), ep,
            ])

    hist_table = {
        "title": "Run history",
        "columns": ["run", "time", "model", "task", "score"],
        "rows": [],
    }
    runs = history[-MAX_RUNS:]
    for i, rec in enumerate(runs):
        for name, per in rec.get("models", {}).items():
            for t in tasks_present:
                if t in per:
                    hist_table["rows"].append(
                        [_run_label(i, rec.get("ts")), rec.get("ts", "?"), name,
                         TASK_LABEL.get(t, t), _pct(per.get(t))])
    hist_table["rows"] = hist_table["rows"][-400:]

    # ---- charts ---------------------------------------------------------
    charts = []
    if len(results) > 0:
        # One horizontal bar per model, sorted by overall — a 16-series
        # grouped chart is unreadable; per-task scores stay in the scorecard.
        ranked = sorted(latest_overall.items(), key=lambda kv: (-kv[1], kv[0]))
        # Truncate the value axis so sub-point differences are visible;
        # the title states where the scale starts so it isn't misleading.
        axis_min = max(0, round(ranked[-1][1] * 100) - 4) if ranked else 0
        charts.append({
            "id": "ranking",
            "title": f"Overall score — latest run, best at top (scale from {axis_min}%)",
            "type": "bar",
            "indexAxis": "y",
            "min": axis_min,
            "labels": [name for name, _ in ranked],
            "series": [
                {"label": "overall", "data": [round(v * 100, 2) for _, v in ranked]}
            ],
        })

    if len(runs) >= 2:
        labels = [_run_label(i, rec.get("ts")) for i, rec in enumerate(runs)]
        all_names = sorted({n for rec in runs for n in rec.get("models", {})})
        overall = []
        per_task = {t: [] for t in tasks_present}
        for name in all_names:
            ov_data = []
            for rec in runs:
                per = rec.get("models", {}).get(name, {})
                a = _avg([per.get(t) for t in tasks_present])
                ov_data.append(round(a * 100, 2) if a is not None else None)
            overall.append({"label": name, "data": ov_data})
            for t in tasks_present:
                per_task[t].append({"label": name,
                                    "data": [_num(rec.get("models", {}).get(name, {}).get(t))
                                             for rec in runs]})
        charts.append({"id": "overall-trend", "title": "Overall across runs",
                       "type": "line", "labels": labels, "series": overall})
        for t in tasks_present:
            charts.append({"id": f"trend-{t}", "title": f"{TASK_LABEL[t]} across runs",
                           "type": "line", "labels": labels, "series": per_task[t]})

    # ---- notes ----------------------------------------------------------
    n_examples = {"gsm8k": 50, "hellaswag": 50, "mmlu": 50, "humaneval": 30, "ifeval": 30}
    notes = [
        "Scores: accuracy / pass@1 / constraint pass-rate per task; overall = mean of available tasks.",
        f"Run history keeps the last {MAX_RUNS} runs (source: results/history.jsonl, appended by bench.py).",
        "The board refreshes automatically at the end of every bench.py run.",
    ]
    if any(t == "ifeval" for t in tasks_present):
        notes.append("IFEval 'na' = constraints not implemented by the scorer (excluded from the rate).")
    if not history:
        notes.append("No history records yet — trends appear after the first real run.")

    return {
        "summary": summary,
        "tables": [scorecard, detail, hist_table],
        "charts": charts,
        "notes": notes,
        "source": {"repo": str(root), "collector": "ai-bench",
                   "note": f"{len(history)} run(s) recorded"},
    }


def _avg(vals):
    vals = [v for v in vals if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None
