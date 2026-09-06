#!/usr/bin/env python3
"""Hermes Interactive Artifacts — LIVE streaming engine.

Wrap ANY command; its results stream into an interactive artifact that
live-updates in the Hermes Interactive tab, chat ::preview, or any browser:

    python tools/livestream.py --id vol-suite-live --title "SPY dealer run" \
        --cwd /opt/data/FinancialDevelopment \
        -- .venv/bin/python -m some_runner --ticker SPY

Mechanics (no server, no app cooperation needed):
  - stdout/stderr lines stream into the artifact payload; after every line the
    engine rewrites data.json + index.html ATOMICALLY (tmp + os.replace).
  - index.html carries a <meta refresh> + JS that RELOADS ONLY WHILE
    payload.live is true; when the command ends the final build sets
    live=false and open viewers settle on the finished state.
  - Works for any repo/project: the payload schema is the artifact framework's
    schema v1 plus {live, status, command, log, exit_code, started/ended_at}.

Exit code mirrors the wrapped command's exit code (fails loudly).
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from refresh import _inject  # the framework's marker injector  # noqa: E402

LIVE_TEMPLATE = ROOT / "templates" / "live.html"
DATA_MARKER = ("<!--HERMES-ARTIFACT:DATA-->", "<!--/HERMES-ARTIFACT:DATA-->")
MAX_LOG_LINES = 400


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class Streamer:
    def __init__(self, artifact_id: str, title: str, command: list[str],
                 cwd: Path | None, summary_cards: list[dict] | None = None):
        self.dir = ROOT / "artifacts" / artifact_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.manifest = {"id": artifact_id, "title": title, "collector": "livestream"}
        (self.dir / "artifact.json").write_text(json.dumps(self.manifest, indent=2),
                                                encoding="utf-8")
        self.command = command
        self.cwd = str(cwd) if cwd else None
        self.base_cards = summary_cards or []
        self.log: list[str] = []
        self.started = time.time()
        self.started_at = _now()

    def payload(self, status: str, live: bool, exit_code: int | None = None) -> dict:
        elapsed = time.time() - self.started
        return {
            "schema_version": 1,
            "artifact_id": self.manifest["id"],
            "title": self.manifest["title"],
            "generated_at": _now(),
            "live": live,
            "status": status,
            "command": self.command,
            "cwd": self.cwd or "",
            "started_at": self.started_at,
            "ended_at": _now() if not live else "",
            "elapsed_sec": round(elapsed, 1),
            "exit_code": exit_code,
            "log": self.log[-MAX_LOG_LINES:],
            "summary": self.base_cards + [
                {"label": "status", "value": status,
                 "tone": "ok" if status == "complete" else ("bad" if status == "failed" else "")},
                {"label": "elapsed", "value": f"{elapsed:.0f}s"},
                {"label": "log lines", "value": str(len(self.log))},
            ],
            "tables": [],
            "charts": [],
            "notes": [],
            "source": {"repo": self.cwd or "", "collector": "livestream",
                       "note": "live stream of " + shlex.join(self.command)},
        }

    def build(self, status: str, live: bool, exit_code: int | None = None) -> None:
        payload = self.payload(status, live, exit_code)
        _atomic_write(self.dir / "data.json",
                      json.dumps(payload, ensure_ascii=False, indent=2))
        # The LIVE template is fully self-contained (own CSS/JS); only the data
        # payload is injected. build_index() would clobber the live JS with the
        # framework's static renderer, so inject just the DATA marker here.
        data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        template_html = LIVE_TEMPLATE.read_text(encoding="utf-8")
        if not live:
            # Final state = genuinely static: strip the whole LIVE block
            # (meta refresh) so finished artifacts never auto-reload.
            start, end = ("<!--HERMES-ARTIFACT:LIVE-->", "<!--/HERMES-ARTIFACT:LIVE-->")
            head = template_html.split(start, 1)[0]
            template_html = head + template_html.split(end, 1)[1]
        html = _inject(
            template_html, DATA_MARKER,
            '<script id="hermes-artifact-data" type="application/json">\n'
            + data + "\n</script>",
        )
        _atomic_write(self.dir / "index.html", html)

    def feed(self, line: str) -> None:
        self.log.append(line.rstrip("\n"))
        self.build("running", live=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Stream a command into a live artifact")
    ap.add_argument("--id", required=True, help="artifact id (folder under artifacts/)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--cwd", default=None, help="working dir for the command")
    ap.add_argument("--card", action="append", default=[],
                    help="summary card 'label=value' (repeatable)")
    ap.add_argument("--notify-target", default=None,
                    help="Discord/other target for digest on completion, e.g. discord:1545456249313824863")
    ap.add_argument("--notify-subject", default=None,
                    help="subject line for the completion digest")
    ap.add_argument("command", nargs="+", help="command to run (after --)")
    args = ap.parse_args()

    cards = []
    for c in args.card:
        k, _, v = c.partition("=")
        cards.append({"label": k, "value": v})

    st = Streamer(args.id, args.title or args.id, args.command,
                  Path(args.cwd) if args.cwd else None, cards)
    st.build("starting", live=True)

    rc = 1
    try:
        proc = subprocess.Popen(
            args.command, cwd=st.cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, errors="replace",
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            st.feed(line)
        rc = proc.wait()
    except FileNotFoundError as e:
        st.log.append(f"LIVESTREAM ERROR: {e}")
        st.build("failed", live=False, exit_code=127)
        return 127

    status = "complete" if rc == 0 else "failed"
    st.build(status, live=False, exit_code=rc)
    print(f"{args.id}: {status} (exit {rc}) — {st.dir / 'index.html'}")

    # Completion digest → Discord (best-effort; never fails the run)
    if args.notify_target:
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from artifact_digest import render_digest
            data = json.loads((st.dir / "data.json").read_text())
            msg = render_digest(data)
            cmd = ["/opt/hermes/.venv/bin/hermes", "send", "-t", args.notify_target]
            if args.notify_subject:
                cmd += ["--subject", args.notify_subject]
            send = subprocess.run(cmd + [msg], capture_output=True, text=True, timeout=60)
            print(f"{args.id}: digest -> {args.notify_target} ({'ok' if send.returncode == 0 else send.stderr.strip()[:120]})")
        except Exception as e:  # noqa: BLE001 — digest is best-effort
            print(f"{args.id}: digest failed (non-fatal): {e}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
