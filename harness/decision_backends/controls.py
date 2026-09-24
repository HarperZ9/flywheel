"""Harness controls for the decision bench, and the battery that voids a run.

Five controls, each a backend that returns one-hot distributions:

- ``include_all`` never acts: all mass on the first real label outside act_on
  (on the none label when every real label is an act label);
- ``exclude_all`` always acts: all mass on the first act_on label;
- ``random`` acts on a uniform-random share of questions equal to
  ``coverage``, decided by a seeded hash of the opaque question key, so the
  choice is independent of order, state and label;
- ``label_shuffle`` answers with the targets after a seeded permutation within
  each label set, which keeps the label counts and cuts every link to the
  state;
- ``oracle`` answers with the true target.

label_shuffle and oracle read suite labels and declare ``sees_labels``. They
test the harness and never score a model. ``battery`` voids a run when
label-shuffle certifies a threshold, the oracle misses an item, include-all
excludes a token, exclude-all passes the risk bound, or the leak detector
trips (design record section 6.2). A passing battery shows the harness
separates these cases on this suite; it does not show any arm is good.
"""
from __future__ import annotations

import hashlib
import random

from .. import decision_bench_metrics as metrics
from ..systemone_contract import answer_labels
from . import none_label, question_key

CONTROL_NAMES = ("include_all", "exclude_all", "random", "label_shuffle", "oracle")
CONTROL_ARMS = tuple("control." + name for name in CONTROL_NAMES)


class ControlBackend:
    """One control. ``choose(qid, labels)`` returns a real label or None."""

    def __init__(self, name: str, choose, *, sees_labels: bool):
        self.name, self.backend_id = name, "control:" + name
        self._choose, self._sees_labels = choose, sees_labels

    def capabilities(self) -> dict:
        return {"question_types": ["noul", "choice", "score"], "max_options": 62,
                "max_state_tokens": None, "shared_state": True, "local": True,
                "deterministic": True, "sees_labels": self._sees_labels}

    def read(self, state: str, questions: dict, *, deadline_ms: int = 0) -> dict:
        answers = {}
        for qid, question in questions.items():
            labels = answer_labels(question)
            pick = self._choose(qid, labels)
            raw = {label: float(label == pick) for label in labels}
            raw[none_label(question)] = float(pick is None)
            answers[qid] = {"raw": raw, "label_mass": 1.0, "order_agreement": True}
        return {"answers": answers, "usage": {"input_tokens": 0, "output_tokens": 0},
                "reads": 0, "gpu_seconds": 0.0, "weights_sha256": None,
                "cache_path": None}


def _keep_label(labels: list, act_on) -> str | None:
    rest = [label for label in labels if label not in act_on]
    return rest[0] if rest else None


def _act_label(labels: list, act_on) -> str | None:
    acts = [label for label in labels if label in act_on]
    return acts[0] if acts else _keep_label(labels, act_on)


def uniform(seed: int, qid: str) -> float:
    """A seeded uniform draw in [0, 1) that depends only on the question id."""
    digest = hashlib.sha256(f"{seed}:{qid}".encode("utf-8")).hexdigest()
    return int(digest[:13], 16) / 16 ** 13


def shuffled_targets(items: list, seed: int) -> dict:
    """Targets permuted within groups of items that share a label set."""
    groups: dict = {}
    for item in sorted(items, key=lambda i: i["item_id"]):
        groups.setdefault(tuple(answer_labels(item["question"])), []).append(item)
    rng, out = random.Random(seed), {}
    for key in sorted(groups):
        members = groups[key]
        targets = [m["target"] for m in members]
        rng.shuffle(targets)
        out.update({m["item_id"]: t for m, t in zip(members, targets)})
    return out


def make_controls(items: list, act_on, *, seed: int = 1709,
                  coverage: float = .3) -> list[tuple[str, ControlBackend]]:
    """The five controls for one split's items, as ``(arm_name, backend)``."""
    if not 0 <= coverage <= 1:
        raise ValueError("coverage must lie in [0, 1]")
    act_on = tuple(act_on)
    # read_items asks under opaque keys, so the label readers key by them too.
    truth = {question_key(item["item_id"]): item["target"] for item in items}
    shuffle = {question_key(k): t for k, t in shuffled_targets(items, seed).items()}

    def rand(qid, labels):
        pick = _act_label if uniform(seed, qid) < coverage else _keep_label
        return pick(labels, act_on)

    choosers = {
        "include_all": (lambda qid, labels: _keep_label(labels, act_on), False),
        "exclude_all": (lambda qid, labels: _act_label(labels, act_on), False),
        "random": (rand, False),
        "label_shuffle": (lambda qid, labels: shuffle[qid], True),
        "oracle": (lambda qid, labels: truth[qid], True),
    }
    return [("control." + name,
             ControlBackend(name, choosers[name][0], sees_labels=choosers[name][1]))
            for name in CONTROL_NAMES]


def battery(runs: dict, act_on, *, leak: dict, max_error: float = .05,
            delta: float = .05, grid=None) -> dict:
    """Harness-sanity checks over one split's control runs.

    ``runs`` maps each name in ``CONTROL_ARMS`` to its rows. Status is
    ``pass`` only when every check passes, else ``void``.
    """
    missing = [arm for arm in CONTROL_ARMS if arm not in runs]
    if missing or type(leak) is not dict or "tripped" not in leak:
        raise ValueError("the battery needs every control and a leak report")
    shuffle = metrics.certify(runs["control.label_shuffle"], act_on,
                              max_error=max_error, delta=delta, grid=grid)
    rand = metrics.certify(runs["control.random"], act_on,
                           max_error=max_error, delta=delta, grid=grid)
    oracle = [metrics.view(r, act_on) for r in runs["control.oracle"]]
    include = runs["control.include_all"]
    kept = metrics.selective_risk(include, [metrics.view(r, act_on) for r in include], act_on)
    cert = [r for r in runs["control.exclude_all"] if r["certification_unit"]]
    excluded = metrics.selective_risk(cert, [metrics.view(r, act_on) for r in cert],
                                      act_on, delta=delta)
    accuracy = sum(v["correct"] for v in oracle) / len(oracle) if oracle else 0.0
    checks = {
        "label_shuffle_certifies_nothing": {
            "pass": shuffle["status"] != metrics.CERTIFIED,
            "status": shuffle["status"], "threshold": shuffle["threshold"],
            "units": shuffle["units"]},
        "oracle_scores_100": {"pass": accuracy == 1.0, "top1_accuracy": accuracy,
                              "items": len(oracle)},
        "include_all_saves_zero": {"pass": kept["tokens_excluded"] == 0,
                                   "tokens_excluded": kept["tokens_excluded"]},
        "exclude_all_fails_bound": {
            "pass": excluded["upper_error_bound"] > max_error,
            "upper_error_bound": excluded["upper_error_bound"],
            "acted": excluded["acted"], "errors": excluded["errors"]},
        "leak_detector_clear": {"pass": not leak["tripped"],
                                "sealed_share": leak["splits"]["sealed"]["share"]},
    }
    return {"status": "pass" if all(c["pass"] for c in checks.values()) else "void",
            "checks": checks, "max_error": max_error, "delta": delta,
            "random_control": {"status": rand["status"], "threshold": rand["threshold"]},
            "does_not_prove": "That any arm is right; only that this harness "
                              "separates these controls on this suite."}
