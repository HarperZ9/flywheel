"""Closed-loop, owned-fixture evaluation. Never controls a browser or live tool."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
from pathlib import Path
from time import perf_counter

from harness.classifier_workflows import exception_type_name, score_workflow_batch
from harness.evidence_json import canonical_sha256

ABSTAIN_ID = "__abstain__"
RESOLUTIONS = ("completed", "justified_blocked", "wrong_submission",
               "unjustified_block", "unresolved")


def abstain_probability(rows: list[dict], key: str) -> float | None:
    """Joint mass on the abstain row among the eligible rows.

    Probabilities are renormalized over the eligible rows. Logits and scores go
    through a softmax, the joint distribution a candidate-plus-abstain head
    defines. A scorer with no abstain row puts no mass on abstaining. The result
    is None when the rows carry no mass to normalize.
    """
    mass = [float(r[key]) for r in rows]
    if key != "probability_like":
        peak = max(mass)
        mass = [math.exp(value - peak) for value in mass]
    total = math.fsum(mass)
    if not total > 0:
        return None
    return math.fsum(m for m, r in zip(mass, rows) if r["choice_id"] == ABSTAIN_ID) / total


class ScoredPolicy:
    """Research-only chooser over validated scores in an inert local simulator.

    It decides act or abstain first. It abstains when the abstain row holds at
    least `abstain_threshold` of the eligible mass, so at the default of 0.5 an
    action needs a strict majority. Only after that does it take the argmax over
    real candidates. The earlier rule took one argmax over rows that included the
    abstain row, so an abstain row that beat each single candidate while holding
    under half the mass stalled every step.
    """

    def __init__(self, runtime, *, family="tool_selection", abstain_threshold=0.5):
        if type(abstain_threshold) not in (int, float) or not 0 < abstain_threshold <= 1:
            raise ValueError("abstain threshold must lie in (0, 1]")
        self.runtime, self.family = runtime, family
        self.abstain_threshold = abstain_threshold
        self.last_score, self.last_status = None, "not_run"
        self.last_decision = self.last_p_abstain = self.last_error_type = None

    def __call__(self, request):
        shadow = score_workflow_batch(
            [{"task_family": self.family, "request": request}], self.runtime)[0]
        self.last_status, self.last_score = shadow["status"], shadow["scores"]
        self.last_error_type = shadow["scorer_error_type"]
        self.last_decision = self.last_p_abstain = None
        if self.last_score is None:
            return None
        rows = [r for r in self.last_score["scores"] if r["eligible"]]
        if not rows:
            self.last_decision = "abstain"
            return None
        # Do not compare mixed scales. The runtime must supply one common field.
        key = next((k for k in ("raw_logit", "score", "probability_like")
                    if all(r[k] is not None for r in rows)), None)
        p_abstain = None if key is None else abstain_probability(rows, key)
        if p_abstain is None:
            self.last_status = "incomparable_scores"
            return None
        self.last_p_abstain = p_abstain
        candidates = [r for r in rows if r["choice_id"] != ABSTAIN_ID]
        if not candidates or p_abstain >= self.abstain_threshold:
            self.last_decision = "abstain"
            return None
        self.last_decision = "act"
        return max(candidates, key=lambda r: (r[key], r["choice_id"]))["choice_id"]


def _select(policy, request):
    """Call the policy on a private copy. On failure keep only the exception type."""
    try:
        selected = policy(copy.deepcopy(request))
        if selected is not None and type(selected) is not str:
            raise ValueError("invalid policy response")
    except Exception as exc:
        # Keep a failed episode; do not leak arbitrary exception contents.
        return None, exception_type_name(exc)
    return selected, None



def _step(env, policy):
    """Run one decision. Return (trace entry, stop reason on failure, failure detail)."""
    tick = perf_counter()
    before = env.snapshot()
    request = env.request()
    acquired = perf_counter()
    selected, error = _select(policy, request)
    scored = perf_counter()
    unavailable = getattr(policy, "last_status", None) in {
        "scorer_unavailable", "incomparable_scores"}
    stop = "policy_error" if error else "policy_unavailable" if unavailable else None
    if stop:
        action_result = {"status": "not_executed", "reason": stop}
    else:
        action_result = env.step(selected)
    acted = perf_counter()
    entry = {
        "request": request, "before_sha256": canonical_sha256(before),
        "choice_id": selected, "policy_error": error,
        "policy_status": getattr(policy, "last_status", "returned_choice"),
        "policy_detail": {field: getattr(policy, attr, None) for field, attr in (
            ("decision", "last_decision"), ("p_abstain", "last_p_abstain"),
            ("scorer_error_type", "last_error_type"))},
        "score": copy.deepcopy(getattr(policy, "last_score", None)),
        "action_result": action_result,
        "after_sha256": canonical_sha256(env.snapshot()),
        "timings_ms": {"state_acquisition": (acquired-tick)*1000,
                       "selection": (scored-acquired)*1000,
                       "execution": (acted-scored)*1000},
    }
    return entry, stop, error or (getattr(policy, "last_status") if stop else None)


def _checked_outcome(case, final, stop, execution_error) -> dict:
    from .classifier_workflow_outcome import check_outcome

    outcome = check_outcome(copy.deepcopy(case), copy.deepcopy(final))
    if execution_error:
        outcome["reasons"].append(f"{stop}: {execution_error}")
        if outcome["outcome"] in {"success", "blocked"}:
            outcome["outcome"] = "unknown"
            outcome["task_resolution"] = "unresolved"
    return outcome


def run_episode(case, policy, *, seed=0, max_steps=12):
    """Replay each policy's own states, preserving errors and exhausted budgets."""
    from .classifier_workflow_fixture import Workflow

    if type(max_steps) is not int or not 1 <= max_steps <= 100:
        raise ValueError("invalid step budget")
    started = perf_counter()
    env, trace, stop = Workflow(copy.deepcopy(case), seed=seed), [], "step_budget"
    execution_error = None
    for _ in range(max_steps):
        if env.done:
            stop = "environment_terminal"
            break
        entry, failed, execution_error = _step(env, policy)
        trace.append(entry)
        if failed:
            stop = failed
            break
    if env.done and stop == "step_budget":
        stop = "environment_terminal"
    final = env.snapshot()
    checked = perf_counter()
    outcome = _checked_outcome(case, final, stop, execution_error)
    ended = perf_counter()
    return {"case_id": case["id"], "seed": seed, "max_steps": max_steps,
            "trace": trace, "final": final, "outcome": outcome,
            "task_completed": outcome["outcome"] == "success",
            "stop_reason": stop, "elapsed_ms": (ended-started)*1000,
            "outcome_check_ms": (ended-checked)*1000}


def episode_resolution(episode: dict) -> str:
    """Give each episode exactly one label, so wrong submissions sit beside completions.

    `wrong_submission` means the form was submitted and the checker did not accept
    it as a completion: wrong fields, a violation on the way, or a submit on an
    impossible case. `unresolved` covers stalls, exhausted budgets and policy
    failures, where nothing was submitted or blocked.
    """
    outcome, final = episode["outcome"]["outcome"], episode["final"]
    if outcome == "success":
        return "completed"
    if outcome == "blocked":
        return "justified_blocked"
    if final.get("submitted") is True:
        return "wrong_submission"
    if final.get("blocked") is True:
        return "unjustified_block"
    return "unresolved"


def resolution_counts(runs: dict) -> dict:
    return {name: {label: sum(episode_resolution(ep) == label for ep in rows)
                   for label in RESOLUTIONS} for name, rows in runs.items()}


def run_experiment(cases, policies, *, seed=0, max_steps=12):
    if not cases or not policies:
        raise ValueError("cases and policies required")
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("duplicate case identity")
    runs = {}
    for name, policy in policies.items():
        runs[name] = []
        for case in cases:
            runtime = getattr(policy, "runtime", None)
            if hasattr(runtime, "clear_cache"):
                runtime.clear_cache()
            episode = run_episode(case, policy, seed=seed, max_steps=max_steps)
            episode["resolution"] = episode_resolution(episode)
            runs[name].append(episode)
    return {
        "schema": "flywheel.classifier-workflow-experiment/v1",
        "cases_sha256": canonical_sha256(cases), "cases": copy.deepcopy(cases),
        "runs": runs, "resolution_counts": resolution_counts(runs),
        "scope": "synthetic_local_state_machine",
        "completion_denominator": "all cases; unknown and blocked are not completed tasks",
        "resolution_denominator": "all cases; each episode takes exactly one resolution label",
        "automatic_selection_enabled": False, "cost_usd": None, "energy_joules": None,
        "cache_policy": "clear neural embeddings before each episode; reuse within episode",
        "does_not_prove": [
            "Real browser behavior, DOM extraction, production utility or alignment.",
            "These are authored synthetic scenarios, not independent human-reviewed tasks.",
            "Current tool-selection heads were not trained for these form action menus.",
            "No calibrated threshold, fallback cascade or model uplift is established.",
            "Elapsed time excludes model load and artifact serialization; resources remain unmeasured.",
        ],
    }


def _kind(value: str) -> str:
    from .classifier_benchmark import runtime_kind

    return value if value == "rules" else runtime_kind(value)


def _provenance(args) -> dict:
    from .classifier_benchmark import factory_source_sha256

    record = {}
    if args.artifact:
        artifact = Path(args.artifact)
        descriptor = artifact/"manifest.json" if artifact.is_dir() else artifact
        record["artifact_descriptor_sha256"] = hashlib.sha256(descriptor.read_bytes()).hexdigest()
    if args.kind.startswith("module:"):
        record["factory_source_sha256"] = factory_source_sha256(args.kind)
    source_paths = [Path(__file__), Path(__file__).with_name("classifier_workflow_fixture.py"),
                    Path(__file__).with_name("classifier_workflow_outcome.py")]
    record["source_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in source_paths}
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", type=_kind, default="rules",
                        help="rules, baseline, encoder, or module:<package.module>:<factory>")
    parser.add_argument("--artifact")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=1709)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if args.kind in ("baseline", "encoder") and not args.artifact:
        parser.error("--artifact is required for learned models")
    from .classifier_workflow_fixture import deterministic_policy, scenarios
    out = Path(args.out)
    if out.exists():
        raise ValueError("output directory exists; preserve prior evidence")
    policies, identity, load_ms = {"rules": deterministic_policy}, "rules", 0.0
    if args.kind != "rules":
        from .classifier_benchmark import _runtime
        tick = perf_counter()
        runtime, identity = _runtime(args.kind, args.artifact, args.device)
        load_ms = (perf_counter()-tick)*1000
        policies[args.kind] = ScoredPolicy(runtime)
    report = run_experiment(scenarios(), policies, seed=args.seed, max_steps=args.max_steps)
    report.update({"model_ref": identity, "model_load_ms": load_ms, "kind": args.kind,
                   "device": args.device, "python": platform.python_version(),
                   "platform": platform.platform()})
    report.update(_provenance(args))
    out.mkdir(parents=True, exist_ok=False)
    (out/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf8")
    counts = {name: {outcome: sum(r["outcome"]["outcome"] == outcome for r in rows)
                    for outcome in sorted({r["outcome"]["outcome"] for r in rows})}
              for name, rows in report["runs"].items()}
    print(json.dumps({"report": str(out/"report.json"), "outcomes": counts,
                      "resolutions": report["resolution_counts"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
