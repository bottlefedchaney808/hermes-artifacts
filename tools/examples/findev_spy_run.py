#!/usr/bin/env python3
"""Real FinDev job for livestream.py: SPY dealer-exposure run, streaming prints.

Repo-agnostic example: point --repo at any FinancialDevelopment checkout with
a .venv. Run via livestream so each line lands in the live artifact:

  python tools/livestream.py --id findev-live \
      --title "FinDev — SPY dealer exposure (live)" \
      --cwd /opt/data/FinancialDevelopment \
      -- .venv/bin/python /opt/data/hermes-artifacts/tools/examples/findev_spy_run.py
"""
from __future__ import annotations

import os
import sys
import time

REPO = os.environ.get("FINDEV_REPO", "/opt/data/FinancialDevelopment")
sys.path.insert(0, REPO)
os.chdir(REPO)


def log(msg: str) -> None:
    print(msg, flush=True)
    time.sleep(0.05)


def main() -> int:
    import shared.module_execution as me  # noqa: E402

    log(f"repo: {REPO}")
    log("minting run via shared.module_execution (widget-native engine)")
    context = {"ticker": "SPY", "expiry": "auto"}
    t0 = time.time()
    out = me.run_selected_modules(["dealer_exposure"], context)
    log(f"engine order: {out['order']}")
    for slug, r in out["results"].items():
        log(f"  {slug:16s} status={r.status} metrics={len(r.metrics or {})} "
            f"artifacts={len(r.artifacts or [])}")
    de = out["results"].get("dealer_exposure")
    if de is not None and de.metrics:
        m = de.metrics
        for key in ("spot", "gex_reference", "book_gamma", "charm_1d",
                    "residual_vanna_inventory", "structural_status"):
            if key in m:
                log(f"  {key}: {m[key]}")
    log(f"run_id: {context.get('run_id')}")
    log(f"run_dir: {context.get('output_dir')}")
    log(f"total elapsed: {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
