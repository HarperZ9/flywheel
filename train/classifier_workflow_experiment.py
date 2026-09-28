"""Closed-loop, owned-fixture evaluation. Never controls a browser or live tool."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
from pathlib import Path
from time import perf_counter

from harness.classifier_workflows import score_workflow_batch
from harness.evidence_json import canonical_sha256


class ScoredPolicy:
    """Research-only argmax over validated scores in an inert local simulator."""

    def __init__(self, runtime, *, family="tool_selection"):
        self.runtime, self.family = runtime, family
        self.last_score, self.last_status = None, "not_run"

    def __call__(self, request):
        shadow = score_workflow_batch(
            [{"task_family": self.family, "request": request}], self.runtime)[0]
        self.last_status, self.last_score = shadow["status"], shadow["scores"]
        if self.last_score is None:
            return None
        rows = [r for r in self.last_score["scores"] if r["eligible"]]
        if not rows:
            return None
        # Do not compare mixed scales. The runtime must supply one common field.
        key = next((k for k in ("raw_logit", "score", "probability_like")
                    if all(r[k] is not None for r in rows)), None)
        if key is None:
            self.last_status = "incomparable_scores"
            return None
        winner = max(rows, key=lambda r: (r[key], r["choice_id"]))["choice_id"]
        return None if winner == "__abstain__" else winner


def run_episode(case, policy, *, seed=0, max_steps=12):
    """Replay each policy's own states, preserving errors and exhausted budgets."""
    from .classifier_workflow_fixture import Workflow
    from .classifier_workflow_outcome import check_outcome

    if type(max_steps) is not int or not 1 <= max_steps <= 100:
        raise ValueError("invalid step budget")
    started = perf_counter()
    env, trace, stop = Workflow(copy.deepcopy(case), seed=seed), [], "step_budget"
    execution_error = None
    for _ in range(max_steps):
        if env.done:
            stop = "environment_terminal"
            break
        tick = perf_counter()
        before = env.snapshot()
        request = env.request()
        acquired = perf_counter()
        error = None
        try:
            selected = policy(copy.deepcopy(request))
            if selected is not None and type(selected) is not str:
                raise ValueError("invalid policy response")
        except Exception as exc:
            # Keep a failed episode; do not leak arbitrary exception contents.
            selected, error = None, type(exc).__name__
        scored = perf_counter()
        unavailable = getattr(policy, "last_status", None) in {
            "scorer_unavailable", "incomparable_scores"}
        if error or unavailable:
            stop = "policy_error" if error else "policy_unavailable"
            execution_error = error or getattr(policy, "last_status")
            action_result = {"status": "not_executed", "reason": stop}
        else:
            action_result = env.step(selected)
        acted = perf_counter()
        trace.append({
            "request": request, "before_sha256": canonical_sha256(before),
            "choice_id": selected, "policy_error": error,
            "policy_status": getattr(policy, "last_status", "returned_choice"),
            "score": copy.deepcopy(getattr(policy, "last_score", None)),
            "action_result": action_result,
            "after_sha256": canonical_sha256(env.snapshot()),
            "timings_ms": {"state_acquisition": (acquired-tick)*1000,
                           "selection": (scored-acquired)*1000,
                           "execution": (acted-scored)*1000},
        })
        if error or unavailable:
            break
    if env.done and stop == "step_budget":
        stop = "environment_terminal"
    final = env.snapshot()
    checked = perf_counter()
    outcome = check_outcome(copy.deepcopy(case), copy.deepcopy(final))
    if execution_error:
        outcome["reasons"].append(f"{stop}: {execution_error}")
        if outcome["outcome"] in {"success", "blocked"}:
            outcome["outcome"] = "unknown"
            outcome["task_resolution"] = "unresolved"
    ended = perf_counter()
    return {"case_id": case["id"], "seed": seed, "max_steps": max_steps,
            "trace": trace, "final": final, "outcome": outcome,
            "task_completed": outcome["outcome"] == "success",
            "stop_reason": stop, "elapsed_ms": (ended-started)*1000,
            "outcome_check_ms": (ended-checked)*1000}


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
            runs[name].append(run_episode(case, policy, seed=seed, max_steps=max_steps))
    return {
        "schema": "flywheel.classifier-workflow-experiment/v1",
        "cases_sha256": canonical_sha256(cases), "cases": copy.deepcopy(cases),
        "runs": runs, "scope": "synthetic_local_state_machine",
        "completion_denominator": "all cases; unknown and blocked are not completed tasks",
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["rules", "baseline", "encoder"], default="rules")
    parser.add_argument("--artifact")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=1709)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    from .classifier_workflow_fixture import deterministic_policy, scenarios
    out = Path(args.out)
    if out.exists():
        raise ValueError("output directory exists; preserve prior evidence")
    policies, identity, load_ms = {"rules": deterministic_policy}, "rules", 0.0
    if args.kind != "rules":
        if not args.artifact:
            parser.error("--artifact is required for learned models")
        from .classifier_benchmark import _runtime
        tick = perf_counter()
        runtime, identity = _runtime(args.kind, args.artifact, args.device)
        load_ms = (perf_counter()-tick)*1000
        policies[args.kind] = ScoredPolicy(runtime)
    report = run_experiment(scenarios(), policies, seed=args.seed, max_steps=args.max_steps)
    report.update({"model_ref": identity, "model_load_ms": load_ms,
                   "device": args.device, "python": platform.python_version(),
                   "platform": platform.platform()})
    if args.artifact:
        artifact = Path(args.artifact)
        descriptor = artifact/"manifest.json" if artifact.is_dir() else artifact
        report["artifact_descriptor_sha256"] = hashlib.sha256(descriptor.read_bytes()).hexdigest()
    source_paths = [Path(__file__), Path(__file__).with_name("classifier_workflow_fixture.py"),
                    Path(__file__).with_name("classifier_workflow_outcome.py")]
    report["source_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in source_paths}
    out.mkdir(parents=True, exist_ok=False)
    (out/"report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf8")
    counts = {name: {outcome: sum(r["outcome"]["outcome"] == outcome for r in rows)
                    for outcome in sorted({r["outcome"]["outcome"] for r in rows})}
              for name, rows in report["runs"].items()}
    print(json.dumps({"report": str(out/"report.json"), "outcomes": counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
