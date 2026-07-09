"""Confidence intervals for m7 scorecards. Stdlib only.

Per arm: Wilson score interval on pass_rate (exact given only the aggregate).
Arm difference (candidate minus baseline):
  - PAIRED bootstrap when both arms carry per_task vectors (m7-scorecard/v1
    with the per_task extension, written by harness.eval since 2026-07-09);
  - otherwise the Newcombe score interval on the difference of two proportions,
    labeled unpaired_approximation (typically conservative for paired data).

The point is honesty at small N: a 9/10 vs 8/10 difference carries an interval
that includes zero, and this tool says so with numbers instead of adjectives.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

Z95 = 1.959963984540054


def wilson_interval(passed: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n <= 0:
        return (0.0, 0.0)
    p = passed / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def newcombe_diff_interval(p1: int, n1: int, p2: int, n2: int) -> tuple[float, float]:
    """Score interval for (p1/n1 - p2/n2), Newcombe (1998) method 10."""
    r1 = p1 / n1 if n1 else 0.0
    r2 = p2 / n2 if n2 else 0.0
    l1, u1 = wilson_interval(p1, n1)
    l2, u2 = wilson_interval(p2, n2)
    d = r1 - r2
    lower = d - math.sqrt((r1 - l1) ** 2 + (u2 - r2) ** 2)
    upper = d + math.sqrt((u1 - r1) ** 2 + (r2 - l2) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def paired_bootstrap_diff(cand: list[bool], base: list[bool],
                          *, iters: int = 10000, seed: int = 7) -> tuple[float, float]:
    """Percentile bootstrap CI on mean(cand) - mean(base), resampling task
    indices so the per-task pairing is preserved."""
    n = len(cand)
    if n == 0 or n != len(base):
        raise ValueError("paired bootstrap needs equal-length non-empty vectors")
    rng = random.Random(seed)
    diffs = []
    for _ in range(iters):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(sum(cand[i] for i in idx) / n - sum(base[i] for i in idx) / n)
    diffs.sort()
    lo = diffs[int(0.025 * iters)]
    hi = diffs[min(iters - 1, int(0.975 * iters))]
    return (lo, hi)


def _passes(arm: dict[str, Any]) -> tuple[int, int]:
    n = int(arm.get("n_tasks", 0))
    return (round(float(arm.get("pass_rate", 0.0)) * n), n)


def _per_task_vector(arm: dict[str, Any]) -> list[bool] | None:
    rows = arm.get("per_task")
    if not isinstance(rows, list) or not rows:
        return None
    ordered = sorted(rows, key=lambda r: str(r.get("task_id", "")))
    return [bool(r.get("passed")) for r in ordered]


def analyze(scorecard: dict[str, Any], *, candidate: str = "verified_inference",
            baseline: str = "single_shot") -> dict[str, Any]:
    arms = scorecard.get("arms", {})
    out: dict[str, Any] = {"schema": "m7-scorecard-ci/v1", "z": Z95, "arms": {}, "difference": {}}
    for name, arm in arms.items():
        passed, n = _passes(arm)
        lo, hi = wilson_interval(passed, n)
        out["arms"][name] = {
            "passed": passed, "n": n,
            "pass_rate": round(passed / n, 4) if n else 0.0,
            "wilson_95": [round(lo, 4), round(hi, 4)],
        }
    cand_arm, base_arm = arms.get(candidate), arms.get(baseline)
    if cand_arm and base_arm:
        c_pass, c_n = _passes(cand_arm)
        b_pass, b_n = _passes(base_arm)
        diff = (c_pass / c_n if c_n else 0.0) - (b_pass / b_n if b_n else 0.0)
        cand_vec = _per_task_vector(cand_arm)
        base_vec = _per_task_vector(base_arm)
        if cand_vec is not None and base_vec is not None and len(cand_vec) == len(base_vec):
            lo, hi = paired_bootstrap_diff(cand_vec, base_vec)
            method = "paired_bootstrap_10000"
        else:
            lo, hi = newcombe_diff_interval(c_pass, c_n, b_pass, b_n)
            method = "newcombe_unpaired_approximation"
        out["difference"] = {
            "candidate": candidate, "baseline": baseline,
            "point": round(diff, 4), "ci_95": [round(lo, 4), round(hi, 4)],
            "method": method,
            "includes_zero": bool(lo <= 0.0 <= hi),
        }
    return out


def render_markdown(name: str, result: dict[str, Any]) -> str:
    lines = [f"### {name}", "", "| Arm | Passed | Wilson 95% CI |", "|---|---|---|"]
    for arm, row in sorted(result["arms"].items()):
        lo, hi = row["wilson_95"]
        lines.append(f"| {arm} | {row['passed']}/{row['n']} ({row['pass_rate']:.0%}) "
                     f"| [{lo:.3f}, {hi:.3f}] |")
    d = result.get("difference") or {}
    if d:
        lo, hi = d["ci_95"]
        verdict = "includes zero: no uplift is claimable at this N" if d["includes_zero"] \
            else "excludes zero"
        lines += ["", f"Difference {d['candidate']} minus {d['baseline']}: "
                      f"{d['point']:+.3f}, 95% CI [{lo:+.3f}, {hi:+.3f}] "
                      f"({d['method']}). This interval {verdict}.", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("scorecards", nargs="+", help="m7 scorecard JSON paths")
    ap.add_argument("--candidate", default="verified_inference")
    ap.add_argument("--baseline", default="single_shot")
    ap.add_argument("--out", default="")
    ap.add_argument("--markdown-out", default="")
    args = ap.parse_args(argv)

    results, md_parts = {}, ["## Confidence intervals", ""]
    for path_text in args.scorecards:
        path = Path(path_text)
        card = json.loads(path.read_text(encoding="utf-8"))
        result = analyze(card, candidate=args.candidate, baseline=args.baseline)
        results[path.name] = result
        md_parts.append(render_markdown(path.name, result))
    payload = json.dumps(results, indent=2, sort_keys=True)
    markdown = "\n".join(md_parts)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    if args.markdown_out:
        Path(args.markdown_out).write_text(markdown, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
