"""Check report fidelity and admit complete, compatible evaluation observations.

The controller supplies the plan and read-only authorities separately from records.
No executor, network client or model runs here. Resolver independence is a caller
obligation; agreement alone does not prove it.
"""
from __future__ import annotations

from .evaluation_result_schema import (canonical, require, resolve_observation,
                                       snapshot, validate_plan, validate_records)
from .output_contract import check_answer, new_contract
from .contract_terms import CRITICAL, TABLE

LIMIT = ("Checks report fidelity against controller-supplied authorities and plan "
         "compatibility only. Does not prove authority independence, event truth, "
         "causation, generalization, safety or competitive superiority.")


def _held(code):
    return {"schema": "flywheel.evaluation-admission/v1", "release": "HOLD",
            "blocking": [code], "fidelity": None, "counts": None, "arms": {},
            "contrasts": [], "does_not_prove": LIMIT}


def check_evaluation(records, *, plan, authorities):
    """Return admission, fidelity and task-cluster counts for inert records.

All inputs are detached before authority calls. Authorities receive only a copy
of their controller-owned trial, never the submitted answer. Callers must supply
bounded read-only resolvers; this synchronous function is not a process sandbox.
    """
    try:
        policy = snapshot(plan)
        trials = validate_plan(policy)
    except (ValueError, TypeError, RecursionError):
        return _held("INVALID_PLAN")
    try:
        submitted = validate_records(snapshot(records), trials)
        require(type(authorities) is dict)
        resolvers = authorities.copy()
        require(all(type(k) is str and callable(v) for k, v in resolvers.items()))
    except (ValueError, TypeError, RecursionError):
        return _held("INVALID_RECORDS_OR_AUTHORITIES")
    specs, answer, sources = [], {}, {}
    # Generated source keys prevent the contract from echoing submitted citations.
    for number, (ident, trial) in enumerate(trials.items()):
        field, source = f"trial-{number}", f"authority-{number}"
        specs.append(dict(name=field, authority=TABLE, source=source,
                          method="required-method", criticality=CRITICAL))
        record = submitted[ident]
        answer[field] = dict(value=canonical(record["observation"]),
                             source=source if record["source"] == trial["source"] else "uncited",
                             method="required-method" if record["method"] == trial["method"]
                             else ("different-method" if record["method"] else ""))
        resolver = resolvers.get(trial["source"])
        if resolver is not None:
            sources[source] = lambda _, fn=resolver, item=trial: resolve_observation(fn, item)
    fidelity = check_answer(answer, new_contract(specs), sources)
    passed = {ident for ident, row in zip(trials, fidelity["fields"])
              if row["verdict"] == "PASS"}
    arms = {}
    for ident, trial in trials.items():
        arm = arms.setdefault(trial["arm_id"], {}).setdefault(trial["role"], {
            "planned_attempts": 0, "checked_observed_attempts": 0,
            "checked_completions": 0, "unavailable_attempts": 0,
            "task_clusters": {}, "completion_rate": None})
        arm["planned_attempts"] += 1
        task = trial["task_id"]
        arm["task_clusters"][task] = arm["task_clusters"].get(task, 0) + 1
        observation = submitted[ident]["observation"]
        if ident in passed and observation["origin"] == "observed":
            arm["checked_observed_attempts"] += 1
            arm["checked_completions"] += observation["outcome"] == "completed"
        else:
            arm["unavailable_attempts"] += 1
    blocking = [] if fidelity["release"] == "RELEASE" else ["REPORT_FIDELITY"]
    groups = [group for arm in arms.values() for group in arm.values()]
    if any(group["unavailable_attempts"] for group in groups):
        blocking.append("OUTCOME_UNAVAILABLE")
    for arm in groups:
        arm["distinct_tasks"] = len(arm["task_clusters"])
        if not arm["unavailable_attempts"]:
            arm["completion_rate"] = arm["checked_completions"] / arm["planned_attempts"]
    for pair in policy["useful_defense_pairs"]:
        benign = submitted[pair["benign"]]["observation"]
        if (pair["benign"] not in passed or benign["origin"] != "observed"
                or benign["outcome"] != "completed"):
            blocking.append("BENIGN_UTILITY_UNMET")
    evaluation = [t for t in trials.values() if t["role"] == "evaluation"]
    benign = [t for t in trials.values() if t["role"] == "benign"]
    return {"schema": "flywheel.evaluation-admission/v1",
            "release": "HOLD" if blocking else "RELEASE",
            "blocking": sorted(set(blocking)), "fidelity": fidelity, "arms": arms,
            "counts": {"planned_attempts": len(evaluation), "submitted_records": len(submitted),
                       "distinct_tasks": len({t["task_id"] for t in evaluation}),
                       "planned_benign_attempts": len(benign),
                       "distinct_benign_tasks": len({t["task_id"] for t in benign})},
            "contrasts": policy["contrasts"], "does_not_prove": LIMIT}
