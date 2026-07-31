"""findings_stats.py -- the paired statistics behind a finding, computed.

Split out of findings.py when that module crossed the 300-line gate, and the
boundary is real: findings.py COMPOSES a document and knows nothing about how a
p-value is derived, while this module computes and knows nothing about documents.

It exists because a p-value used to sit in findings.py as the string literal
"McNemar p=0.0015", inside the module whose docstring promises numbers are not
hand-transcribed. Working out where that number came from is the whole lesson.

`_selector_finding` reads `selector_consensus_headroom.json`, and hashes it into
`source_sha256`. That artifact's per-task outcomes give 11 gains, 0 regressions,
chi-square with continuity correction 9.0909, so p = 0.0026. The literal said
0.0015, which is the p-value of a DIFFERENT artifact,
`selector_comparison_headroom.json`, at 12 gains and chi-square 10.0833.

So the finding pinned the provenance hash of one file and quoted a statistic
computed from another. That is worse than a stale number. A stale number drifts
away from its own source and can be caught by rehashing; this one was bound to
the wrong source from the moment it was written, and rehashing would have
confirmed it forever.

The fix is not a better number. It is that no number in a finding is typed by
hand: `mcnemar` derives it from the per-task outcomes of the artifact the finding
actually hashes, or the finding reports that it cannot.
"""
from __future__ import annotations

import math


def mcnemar(per_task: list, base: str, arm: str) -> dict | None:
    """McNemar on the discordant pairs, computed from per-task outcomes.

    This exists because a p-value used to sit in this module as the string
    literal "McNemar p=0.0015", inside the module whose docstring promises
    numbers are not hand-transcribed. The literal was numerically right, which is
    the worst version of the defect: it cannot drift visibly, so it would have
    stayed right until the artifact changed and then been silently wrong.

    `b` is reported deliberately. b=0 means no task the baseline passed and the
    treatment failed, which is the signature of one arm CONTAINING the other
    rather than of an effect, and a reader needs it to weigh the p-value at all.
    """
    if not isinstance(per_task, list) or not per_task:
        return None
    try:
        b = sum(1 for t in per_task if t[base] and not t[arm])
        c = sum(1 for t in per_task if not t[base] and t[arm])
    except (KeyError, TypeError):
        return None
    m, k = b + c, min(b, c)
    if not m:
        return {"b": 0, "c": 0, "discordant": 0, "chi2_cc": 0.0, "p_exact": 1.0}
    p = min(1.0, 2 * sum(math.comb(m, i) for i in range(k + 1)) / 2 ** m)
    return {"b": b, "c": c, "discordant": m,
            "chi2_cc": (abs(b - c) - 1) ** 2 / m, "p_exact": p}


def selector_bounds(data: dict) -> str:
    """The two structural defects in this comparison, computed not asserted.

    Neither was recorded when this finding was first written, and the artifact's
    own verdict string says "externalization EARNS capability", which is the
    strongest wording anywhere in the repo. It rests on both defects at once.
    """
    per_task = data.get("per_task")
    ext = mcnemar(per_task, "single", "ext") if per_task else None
    slf = mcnemar(per_task, "single", "self") if per_task else None
    if ext is None:
        return ("headroom subset, one model, code tasks with oracles; per-task "
                "outcomes absent so no paired statistic can be computed")
    parts = [
        f"external: {ext['c']} gains, {ext['b']} regressions, "
        f"{ext['discordant']} discordant, exact McNemar p={ext['p_exact']:.6f}",
    ]
    if slf is not None:
        parts.append(f"self: {slf['c']} gains, {slf['b']} regressions, "
                     f"exact p={slf['p_exact']:.6f}")
    parts.append(
        "SELECTION ON THE DEPENDENT VARIABLE: the denominator is the headroom "
        "screen, defined by this same model failing the same temperature-0 draw "
        "that constitutes the single-shot arm, so the single-shot rate is near "
        "zero by construction and the difference is a resampling recovery rate")
    if ext["b"] == 0:
        parts.append(
            "NESTED ARMS: zero tasks where single-shot passed and the external "
            "selector failed, so the difference cannot be negative and the "
            "p-value tests a null that construction excluded")
    parts.append("one model, one run, no between-seed variance component")
    return "; ".join(parts)
