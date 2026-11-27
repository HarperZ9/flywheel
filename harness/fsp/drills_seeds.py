"""Rerun the seeded drills over several seeds and report the spread.

Run: python -m harness.fsp.drills_seeds [fast_seeds] [silent_seeds]
Re-render a stored run: python -m harness.fsp.drills_seeds --render reports/drills-seeds-DATE.json

The standard drills report (python -m harness.fsp.drills) runs each seeded drill once,
with seeds 1, 2, 3 and 5, so a rerun replays the same simulation. This module
runs the four seeded drills (tamper, silent device, order to effect and
convergence) over a range of seeds and reports, for each headline figure, the
lowest, median and highest value across seeds. The lapse drills and the other
conformance drills draw no random numbers, so they are left out.

Every figure is a property of the demo: simulated devices, a simulated clock and
demo cadences. It writes its own report files and leaves the dated drills
report alone.
"""

from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
import time
from pathlib import Path

from . import drills_conformance, drills_targets

ROOT = Path(__file__).resolve().parents[2]
STANDARD = {"tamper": 1, "silent": 2, "effect": 3, "convergence": 5}


def _tamper(seed: int) -> dict:
    r = drills_targets.drill_tamper(seed=seed)
    return {"within_1_min": r["within_1_min"], "of": r["of"],
            "median_s": r["event_to_log_s"]["median"], "max_s": r["event_to_log_s"]["max"],
            "each_failed_closed": r["each_device_failed_closed"],
            "recheck_match": r["recheck"]["MATCH"]}


def _silent(seed: int) -> dict:
    r = drills_targets.drill_silent(seed=seed)
    out = {}
    for mode, m in r["modes"].items():
        out[f"{mode}_median_h"] = m["hours_to_fail_closed"]["median"]
        out[f"{mode}_max_h"] = m["hours_to_fail_closed"]["max"]
        out[f"{mode}_missed_max_min"] = m["minutes_to_missed"]["max"]
    return out


def _effect(seed: int) -> dict:
    r = drills_targets.drill_effect(seed=seed)
    return {"median_min": r["effective_to_receipt_min"]["median"],
            "max_min": r["effective_to_receipt_min"]["max"],
            "offline_flagged": r["offline_device_flagged_missing_receipt"],
            "backed": r["receipts_backed_by_prior_logged_order"], "receipts": r["receipts"]}


def _convergence(seed: int) -> dict:
    r = drills_conformance.convergence(seed=seed)
    return {"single_family_sets": r["single_family_sets"],
            "two_family_sets": r["two_family_sets"], "trials": r["trials"], "pass": r["pass"]}


def spread(rows: list[dict]) -> dict:
    """Lowest, median and highest of every numeric field; count of true flags."""
    out = {}
    for key in rows[0]:
        vals = [row[key] for row in rows]
        if all(isinstance(v, bool) for v in vals):
            out[key] = {"true": sum(vals), "of": len(vals)}
        else:
            med = round(statistics.median(vals), 3)
            out[key] = {"min": min(vals), "max": max(vals),
                        "median": int(med) if float(med).is_integer() else med}
    return out


def run(fast_seeds: int = 20, silent_seeds: int = 10) -> dict:
    started = time.time()
    plan = {"tamper": (_tamper, fast_seeds), "silent": (_silent, silent_seeds),
            "effect": (_effect, fast_seeds), "convergence": (_convergence, fast_seeds)}
    results = {}
    for name, (fn, count) in plan.items():
        seeds = list(range(1, count + 1))
        rows = [fn(s) for s in seeds]
        results[name] = {"seeds": seeds, "standard_seed": STANDARD[name],
                         "per_seed": rows, "spread": spread(rows)}
    results["meta"] = {"date": dt.date.today().isoformat(),
                       "started": dt.datetime.fromtimestamp(started).isoformat(timespec="seconds"),
                       "runtime_s": round(time.time() - started, 1)}
    return results


def render(res: dict) -> str:
    lines = [f"# Seeded drills over several seeds, {res['meta']['date']}", "",
             f"Started {res['meta']['started']} local time, {res['meta']['runtime_s']} s. "
             "Each row gives the lowest, median and highest value of a headline figure "
             "across seeds, and the value at the seed the dated drills report uses. "
             "Every figure is a demo measurement on simulated devices and a simulated clock.", ""]
    for name in ("tamper", "silent", "effect", "convergence"):
        r = res[name]
        std = r["per_seed"][r["seeds"].index(r["standard_seed"])]
        lines += [f"## {name}", "", f"Seeds {r['seeds'][0]} to {r['seeds'][-1]} "
                  f"({len(r['seeds'])} runs); the dated report uses seed {r['standard_seed']}.", "",
                  "| Figure | Lowest | Median | Highest | At the report's seed |",
                  "| - | - | - | - | - |"]
        for key, s in r["spread"].items():
            if "true" in s:
                lines.append(f"| {key} | true in {s['true']} of {s['of']} | | | {std[key]} |")
            else:
                lines.append(f"| {key} | {s['min']} | {s['median']} | {s['max']} | {std[key]} |")
        lines.append("")
    lines += ["**Does not prove.** The spread shows how much each figure moves with the "
              "simulation's random draws under fixed demo cadences. It says nothing about real "
              "devices, networks or fleets, and a model wrote the drills and this report.", ""]
    return "\n".join(lines)


def main() -> None:
    if sys.argv[1:2] == ["--render"]:
        res = json.loads(Path(sys.argv[2]).read_text("utf-8"))
        for name in ("tamper", "silent", "effect", "convergence"):
            res[name]["spread"] = spread(res[name]["per_seed"])
    else:
        res = run(*[int(a) for a in sys.argv[1:3]])
    stamp = res["meta"]["date"]
    out = ROOT / "reports"
    (out / f"drills-seeds-{stamp}.json").write_text(json.dumps(res, indent=1), "utf-8")
    text = render(res)
    (out / f"drills-seeds-{stamp}.md").write_text(text, "utf-8")
    print(text)


if __name__ == "__main__":
    main()
