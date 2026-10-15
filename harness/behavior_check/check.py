"""check.py -- run every scenario on build A and build B, then compare.

Each scenario runs once per build, in its own folders with its own scripted
model. The verdict is MATCH when all five streams agree after the frozen
normalization in every scenario, DRIFT with the first diverging event
otherwise, and UNVERIFIABLE when a scenario reached no model on either build
(the check then has nothing to compare).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import compare
from .run import load_scenarios, run_scenario, scenarios_path

SCHEMA = "flywheel.behavior-check/v1"


def source_tree(path: str) -> str:
    tree = Path(path).resolve()
    if not (tree / "harness" / "cli_entry.py").is_file():
        raise ValueError(f"{path} is not a Flywheel source tree (no harness/cli_entry.py)")
    return str(tree)


def run_pair(tree_a: str, tree_b: str, scenarios: list, work: str, *, jobs: int = 2,
             python: str = sys.executable, python_b: "str | None" = None,
             work_b: "str | None" = None) -> list:
    """[(scenario, run_a, run_b)] in scenario order."""
    tasks = []
    for s in scenarios:
        tasks.append((tree_a, s, work, python))
        tasks.append((tree_b, s, work_b or work, python_b or python))
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        runs = list(pool.map(lambda t: run_scenario(t[0], t[1], t[2], python=t[3]), tasks))
    return [(s, runs[2 * i], runs[2 * i + 1]) for i, s in enumerate(scenarios)]


def judge(pairs: list, rules: dict) -> dict:
    """Per-scenario verdicts and the first divergence across all of them."""
    rows, first = [], None
    for scenario, run_a, run_b in pairs:
        na, nb = compare.normalize(run_a, rules), compare.normalize(run_b, rules)
        found = compare.diverge(scenario["name"], na, nb)
        reached = bool(na["requests"]) or bool(nb["requests"])
        verdict = "DRIFT" if found else ("MATCH" if reached else "UNVERIFIABLE")
        rows.append({"scenario": scenario["name"], "verdict": verdict,
                     "a_sha256": compare.digest(na), "b_sha256": compare.digest(nb),
                     "model_requests": [len(na["requests"]), len(nb["requests"])],
                     "first_divergence": found})
        if found and first is None:
            first = found
    verdicts = {r["verdict"] for r in rows}
    overall = "DRIFT" if "DRIFT" in verdicts else (
        "UNVERIFIABLE" if "UNVERIFIABLE" in verdicts else "MATCH")
    return {"verdict": overall, "first_divergence": first, "scenarios": rows}


def select(scenarios: list, only: "list | None") -> list:
    if not only:
        return scenarios
    unknown = set(only) - {s["name"] for s in scenarios}
    if unknown:
        raise ValueError("unknown scenario(s): " + ", ".join(sorted(unknown)))
    return [s for s in scenarios if s["name"] in only]


def behavior_check(tree_a: str, tree_b: str, *, only: "list | None" = None,
                   scenarios_file: "str | None" = None, rules_file: "str | None" = None,
                   work: "str | None" = None, jobs: int = 2,
                   python: str = sys.executable) -> dict:
    """Run the scenarios on both trees and return the report."""
    tree_a, tree_b = source_tree(tree_a), source_tree(tree_b)
    scenarios = select(load_scenarios(scenarios_file), only)
    rules = compare.load_rules(rules_file)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="fw-behavior-", dir=work) as scratch:
        pairs = run_pair(tree_a, tree_b, scenarios, scratch, jobs=jobs, python=python)
    report = judge(pairs, rules)
    return {"schema": SCHEMA, **report, "a": tree_a, "b": tree_b,
            "scenario_count": len(scenarios),
            "scenarios_sha256": compare.file_sha256(scenarios_file or scenarios_path()),
            "normalization_sha256": compare.file_sha256(rules_file or compare.rules_path()),
            "python": python, "seconds": round(time.monotonic() - started, 1)}


def render(report: dict) -> str:
    lines = [f"behavior-check: {report['verdict']}"]
    first = report.get("first_divergence")
    if first:
        where = f"event {first['index']}" if first["index"] is not None else "value"
        label = f" ({first['label']})" if first.get("label") else ""
        lines += [f"  first divergence: scenario {first['scenario']}, stream {first['stream']}, "
                  f"{where}{label}, at {first['path']}",
                  f"  A: {json.dumps(first['a'], ensure_ascii=False)}",
                  f"  B: {json.dumps(first['b'], ensure_ascii=False)}"]
    counts: dict = {}
    for row in report["scenarios"]:
        counts[row["verdict"]] = counts.get(row["verdict"], 0) + 1
    summary = ", ".join(f"{n} {v}" for v, n in sorted(counts.items()))
    lines.append(f"{report['scenario_count']} scenario(s): {summary}")
    for row in report["scenarios"]:
        if row["verdict"] != "MATCH":
            lines.append(f"  {row['verdict']:<12} {row['scenario']}")
    return "\n".join(lines)


def seal_receipt(report: dict) -> dict:
    """The report as a sealed record: its sha256 covers every other field."""
    from harness.hash_chain import seal
    body = {k: v for k, v in report.items() if k != "schema"}
    body.update({"schema": "flywheel.behavior-check-receipt/v1",
                 "report_schema": report["schema"]})
    return seal(body, digest_key="receipt_sha256")


def write_receipt(report: dict, path: str) -> dict:
    receipt = seal_receipt(report)
    Path(path).write_text(json.dumps(receipt, indent=1, sort_keys=True) + "\n",
                          encoding="utf-8")
    return receipt
