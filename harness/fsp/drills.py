"""Run every drill and write a dated drills report. Run: python -m harness.fsp.drills

The report states each result as a demo measurement next to the appendix
target it is compared with, states each finding where the drill produced
it, and restates every finding as a final follow-up.
"""

from __future__ import annotations

import datetime as dt
import json
import platform
import time
from pathlib import Path

from . import drills_conformance, drills_lapse, drills_review, drills_targets
from .drills_text import render
from .params import Params

ROOT = Path(__file__).resolve().parents[2]


def run_all() -> dict:
    started = time.time()
    results = {
        "tamper": drills_targets.drill_tamper(),
        "silent": drills_targets.drill_silent(),
        "effect": drills_targets.drill_effect(),
        "lapse_cut": drills_lapse.run(run_dir=ROOT / "run"),
        "lapse_file": drills_lapse.run(file_channel=True, run_dir=ROOT / "run"),
        "conformance": [f() for f in drills_conformance.ALL + drills_review.ALL],
    }
    results["false_halts"] = drills_lapse.false_halt_accounting(
        [results["lapse_cut"], results["lapse_file"]])
    results["meta"] = {"date": dt.date.today().isoformat(),
                       "started": dt.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
                       "runtime_s": round(time.time() - started, 1),
                       "python": platform.python_version(), "platform": platform.platform()}
    return results


def main() -> None:
    results = run_all()
    stamp = results["meta"]["date"]
    out_dir = ROOT / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"drills-{stamp}.json").write_text(json.dumps(results, indent=1), "utf-8")
    text = render(results, Params())
    (out_dir / f"drills-{stamp}.md").write_text(text, "utf-8")
    print(text)


if __name__ == "__main__":
    main()
