"""shapley_far.py -- a placebo test for exact Shapley attribution over sources.

Shapley attribution over sources answers "which of these sources did the answer
come from" by giving each source its average marginal effect on a value function
across every coalition of the other sources. It is exact for its value function.
This module asks the question a reader needs before trusting a credit: how often
does a source that should get nothing get credit anyway?

Each item mixes one gold source, which holds the answer, with known-null
controls: an empty source, irrelevant passages, and shuffled passages. For every
item the caller evaluates the value function on all 2^N coalitions; this module
computes exact Shapley values (rational arithmetic, N up to MAX_N), turns each
control's credit into one trial, and reports the false-attribution rate (FAR)
over those trials with a Wilson 95% interval, per control kind and overall. The
verdict goes through `attribution_far.analyze`, the probe this repo already uses
for every attribution method, so one rule judges all of them.

The value function used by `scripts/shapley_placebo_run.py` is SCORING_RULE: 1
when a model's greedy answer contains an accepted answer as a whole word, else
0. A different value function can give different credits; nothing here
generalizes across value functions. Standard library only.
"""
from __future__ import annotations

import math
import re
from fractions import Fraction

from . import attribution_far as af
from . import incentive_manifest as im
from .trace_observation.intervals import rate_block

MAX_N = 10
CREDIT_THRESHOLD = Fraction(1, 20)
SCORING_RULE = "greedy-answer-contains-accepted/1"
PROMPT_RULE = "sources-then-question/1"
SHAPLEY_DOES_NOT_PROVE = (
    "The rate covers these items, these control constructions, this model, this "
    "prompt and this value function only. It says nothing about attribution over "
    "pre-training data, about hierarchical or sampled estimators, about larger N, "
    "or about any hosted demo whose value function is not known.")


class ShapleyError(ValueError):
    """A coalition table or item that cannot be scored honestly."""


def shapley_exact(n: int, value) -> list:
    """Exact Shapley values for players 0..n-1. `value(mask)` gives v(S) for the
    coalition whose bit i is set when player i is in it; it is called 2^n times."""
    if not 1 <= n <= MAX_N:
        raise ShapleyError(f"n: 1..{MAX_N}")
    v = [Fraction(value(m)) for m in range(1 << n)]
    weight = [Fraction(math.factorial(k) * math.factorial(n - k - 1), math.factorial(n))
              for k in range(n)]
    phi = []
    for i in range(n):
        bit, total = 1 << i, Fraction(0)
        for m in range(1 << n):
            if not m & bit:
                total += weight[bin(m).count("1")] * (v[m | bit] - v[m])
        phi.append(total)
    return phi


def normalize(text: str) -> str:
    t = re.sub(r"(?<=\d),(?=\d)", "", str(text).lower()).replace("-", " ")
    return re.sub(r"\s+", " ", t).strip()


def answer_value(output: str, accepted) -> int:
    """SCORING_RULE: 1 if any accepted answer appears as a whole word, else 0."""
    out = normalize(output)
    return int(any(re.search(r"\b" + re.escape(normalize(a)) + r"\b", out) for a in accepted))


def prompt(question: str, sources, mask: int) -> str:
    """PROMPT_RULE. Sources keep their letter whatever the coalition, so a source's
    label never changes; an empty source is shown as empty."""
    blocks = [f"[Source {chr(65 + i)}]\n{s['text'] or '(empty)'}"
              for i, s in enumerate(sources) if mask >> i & 1]
    body = "\n\n".join(blocks) if blocks else "(no sources)"
    return ("Answer the question. Use the sources if they help. Reply with the answer "
            "only, in a few words.\n\n" + body + f"\n\nQuestion: {question}\nAnswer:")


def item_trials(item: dict, values: list, threshold=CREDIT_THRESHOLD) -> list:
    """One trial per source: its exact Shapley value and whether it got credit."""
    n = len(item["sources"])
    if len(values) != 1 << n:
        raise ShapleyError(f"{item['item_id']}: needs {1 << n} coalition values")
    phi = shapley_exact(n, values.__getitem__)
    full, empty = values[(1 << n) - 1], values[0]
    if sum(phi) != Fraction(full) - Fraction(empty):
        raise ShapleyError(f"{item['item_id']}: efficiency failed")
    return [{"trial_id": f"{item['item_id']}:{chr(65 + i)}", "item_id": item["item_id"],
             "is_control": s["role"] == "control", "kind": s["kind"],
             "phi": str(phi[i]), "phi_float": round(float(phi[i]), 6),
             "attributed": phi[i] > threshold, "any_credit": abs(phi[i]) > threshold,
             "answerable": bool(full) and not empty}
            for i, s in enumerate(item["sources"])]


def manifest(environment_id: str, witness_entries: list) -> dict:
    """The environment record `attribution_far.analyze` requires, for this setup."""
    return {"schema": im.SCHEMA, "environment_id": environment_id, "kind": "deployment",
            "reward": {"declared_form": SCORING_RULE, "source_ref": "harness/shapley_far.py"},
            "data_distribution": {"summary": "public-domain passages with known-null controls",
                                  "source_ref": "items-v1.json"},
            "reinforced_behaviors": [], "penalized_behaviors": [], "scarcity_variables": [],
            "witness": {"algorithm": "sha256", "entries": witness_entries},
            "does_not_prove": im.DOES_NOT_PROVE}


def _rates(trials, key) -> dict:
    return rate_block(sum(1 for t in trials if t[key]), len(trials))


def analyze(trials: list, env_manifest: dict, *, far_threshold=af.DEFAULT_FAR_THRESHOLD) -> dict:
    """FAR over control trials (overall and per kind) with Wilson 95% intervals,
    gold detection on answerable items, and the attribution_far verdict."""
    controls = [t for t in trials if t["is_control"]]
    gold = [t for t in trials if not t["is_control"] and t["answerable"]]
    kinds = sorted({t["kind"] for t in controls})
    verdict = af.analyze(env_manifest, [{k: t[k] for k in ("trial_id", "is_control", "attributed")}
                                        for t in trials], far_threshold=far_threshold)
    return {"verdict": verdict["verdict"], "far_threshold": far_threshold,
            "credit_threshold": str(CREDIT_THRESHOLD),
            "false_attribution": _rates(controls, "attributed"),
            "false_any_credit": _rates(controls, "any_credit"),
            "false_attribution_answerable": _rates([t for t in controls if t["answerable"]],
                                                   "attributed")
            if any(t["answerable"] for t in controls) else None,
            "by_kind": {k: _rates([t for t in controls if t["kind"] == k], "attributed")
                        for k in kinds},
            "gold_detection_on_answerable": _rates(gold, "attributed") if gold else None,
            "answerable_items": len({t["item_id"] for t in gold}),
            "items": len({t["item_id"] for t in trials}), "flagged": verdict["flagged"],
            "does_not_prove": [af.FAR_DOES_NOT_PROVE, SHAPLEY_DOES_NOT_PROVE]}
