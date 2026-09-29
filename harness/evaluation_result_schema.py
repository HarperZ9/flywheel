"""Bounded input shapes for the offline evaluation consumer."""
from __future__ import annotations

from copy import deepcopy
import json
import math

CONDITIONS = {"task_revision", "scoring", "harness", "budget", "access", "safeguards"}
ORIGINS = {"observed", "reported", "simulated", "attempted", "unsupported", "missing"}
TRIAL_KEYS = {"trial_id", "task_id", "attempt_id", "arm_id", "model_revision",
              "method", "source", "conditions", "role"}
OBSERVATION_KEYS = {"origin", "outcome", "value", "reason", "model_revision", "conditions"}


def require(condition):
    if not condition:
        raise ValueError("invalid evaluation input")


def text(value, *, empty=False):
    require(type(value) is str and len(value) <= 1024)
    require(empty or bool(value.strip()))


def snapshot(value):
    """Copy plain, bounded JSON values without invoking custom object methods."""
    nodes = 0

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        require(nodes <= 300000 and depth <= 10)
        kind = type(item)
        if kind is dict:
            require(len(item) <= 4096 and all(type(k) is str for k in item))
            return {visit(k, depth + 1): visit(v, depth + 1) for k, v in item.items()}
        if kind is list:
            require(len(item) <= 4096)
            return [visit(v, depth + 1) for v in item]
        require(kind in (str, int, float, bool, type(None)))
        if kind is str:
            require(len(item) <= 4096)
        if kind is float:
            require(math.isfinite(item))
        if kind is int:
            require(item.bit_length() <= 256)
        return item

    return visit(value, 0)


def conditions(value):
    require(type(value) is dict and set(value) == CONDITIONS)
    for item in value.values():
        text(item)


def observation(value):
    require(type(value) is dict and set(value) == OBSERVATION_KEYS)
    text(value["origin"])
    require(value["origin"] in ORIGINS)
    require(value["outcome"] is None or
            (type(value["outcome"]) is str and value["outcome"] in {"completed", "not_completed"}))
    require(type(value["value"]) in (str, int, float, bool, type(None)))
    text(value["reason"], empty=True)
    text(value["model_revision"])
    conditions(value["conditions"])
    if value["origin"] == "observed":
        require(value["outcome"] is not None)
    if value["origin"] in {"missing", "unsupported"}:
        require(value["outcome"] is None and value["value"] is None)
        text(value["reason"])


def validate_plan(plan):
    require(type(plan) is dict and set(plan) == {"trials", "contrasts", "useful_defense_pairs"})
    trials, contrasts, pairs = plan["trials"], plan["contrasts"], plan["useful_defense_pairs"]
    require(type(trials) is list and 0 < len(trials) <= 4096)
    require(type(contrasts) is list and all(type(c) is str for c in contrasts))
    require(len(set(contrasts)) == len(contrasts) and set(contrasts) <= CONDITIONS | {"method"})
    indexed, arms, revisions = {}, {}, {}
    for trial in trials:
        require(type(trial) is dict and set(trial) == TRIAL_KEYS)
        for key in TRIAL_KEYS - {"conditions"}:
            text(trial[key])
        conditions(trial["conditions"])
        require(trial["role"] in {"evaluation", "benign"})
        ident, arm = trial["trial_id"], trial["arm_id"]
        require(ident not in indexed)
        slot = (trial["task_id"], trial["attempt_id"])
        require(slot not in arms.setdefault(arm, {}))
        arms[arm][slot] = trial
        require(revisions.setdefault(arm, trial["model_revision"]) == trial["model_revision"])
        indexed[ident] = trial
    # Every arm must cover the same task/repetition matrix, including benign roles.
    reference = next(iter(arms.values()))
    for slots in arms.values():
        require(slots.keys() == reference.keys())
        for slot, trial in slots.items():
            other = reference[slot]
            require(trial["role"] == other["role"])
            for key in CONDITIONS - set(contrasts):
                require(trial["conditions"][key] == other["conditions"][key])
            if "method" not in contrasts:
                require(trial["method"] == other["method"])
    require(type(pairs) is list)
    seen = set()
    for pair in pairs:
        require(type(pair) is dict and set(pair) == {"evaluation", "benign"})
        require(all(type(v) is str and v in indexed for v in pair.values()))
        evaluation, benign = indexed[pair["evaluation"]], indexed[pair["benign"]]
        require(evaluation["role"] == "evaluation" and benign["role"] == "benign")
        require(evaluation["arm_id"] == benign["arm_id"])
        key = (pair["evaluation"], pair["benign"])
        require(key not in seen)
        seen.add(key)
    return indexed


def validate_records(records, trials):
    require(type(records) is list and len(records) == len(trials))
    indexed = {}
    for record in records:
        required = {"trial_id", "source", "method", "observation"}
        require(type(record) is dict and required <= set(record) <= required | {"labels"})
        for key in ("trial_id", "source", "method"):
            text(record[key], empty=key != "trial_id")
        ident = record["trial_id"]
        require(ident in trials and ident not in indexed)
        if "labels" in record:
            require(type(record["labels"]) is dict and set(record["labels"]) <= {"provider", "nation"})
            for label in record["labels"].values():
                text(label, empty=True)
        observation(record["observation"])
        trial, observed = trials[ident], record["observation"]
        require(observed["model_revision"] == trial["model_revision"])
        require(observed["conditions"] == trial["conditions"])
        indexed[ident] = record
    return indexed


def canonical(value):
    """Exact JSON comparison avoids nested bool/int equality and numeric coercion."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def resolve_observation(resolve, trial):
    try:
        value = snapshot(resolve(deepcopy(trial)))
        observation(value)
        return canonical(value)
    except Exception:
        # The underlying contract includes exception text; never forward payloads.
        raise ValueError("observation authority unavailable") from None
