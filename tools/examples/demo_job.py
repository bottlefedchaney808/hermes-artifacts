#!/usr/bin/env python3
"""Demo job for livestream.py — emits a few lines with delays (exit 0)."""
import time

STEPS = [
    "loading context",
    "fetching chain snapshot (simulated)",
    "computing dealer book",
    "fitting SVI smile",
    "summarizing exposures",
]


def main() -> None:
    print("demo job starting", flush=True)
    for i, step in enumerate(STEPS, 1):
        time.sleep(0.7)
        print(f"[{i}/{len(STEPS)}] {step} ... ok", flush=True)
    time.sleep(0.4)
    print("demo job complete — exit 0", flush=True)


if __name__ == "__main__":
    main()
