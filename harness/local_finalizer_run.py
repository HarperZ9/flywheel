"""Candidate-prefix orchestration, with optional durable accounting."""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable
from .cross_harness_artifacts import canonical_sha256
from .local_finalizer_experiment import (
    ARMS,
    SYSTEMIC_FINALIZER_STATES,
    _sha,
    _write_json,
    _task_arm_orders,
    _row,
    _ineligible_state,
    score_arm_text,
)


def run_candidate_prefix_experiment(
    tasks: list[dict[str, Any]],
    run_root: Path,
    params: dict[str, Any],
    *,
    candidate_runner: Callable,
    finalizer_runner: Callable,
    score_runner: Callable = score_arm_text,
    order_plan: dict[str, Any] | None = None,
    accounting=None,
) -> dict[str, Any]:
    run_root = Path(run_root)
    if run_root.exists():
        raise ValueError("run root already exists")
    task_arm_orders = _task_arm_orders(tasks, order_plan)
    order_hash = canonical_sha256(task_arm_orders)
    run_root.mkdir(parents=True)
    manifest = {
        "schema": "harness.local-finalizer-candidate-prefix-manifest/v1",
        "arms": list(ARMS),
        "params": params,
        "tasks": [task["task_id"] for task in tasks],
        "task_arm_orders": task_arm_orders,
        "task_arm_order_sha256": order_hash,
    }
    _write_json(run_root / "pre-run-manifest.json", manifest)
    if accounting is not None:
        accounting.prepare(run_root, tasks, params, order_hash)
    rows = []
    stopped_finalizer_arms: dict[str, str] = {}
    for task in tasks:
        prefix_dir = run_root / task["task_id"] / "candidate-prefix"
        try:
            candidate = (
                accounting.dispatch(
                    task["task_id"],
                    "normal",
                    candidate_runner,
                    task,
                    params,
                    prefix_dir,
                )
                if accounting is not None
                else candidate_runner(task, params, prefix_dir)
            )
            candidate.setdefault(
                "candidate_sha256",
                _sha(str(candidate.get("selected_text", "")).encode()),
            )
        except Exception as exc:
            if accounting is not None:
                accounting.check()
            candidate = {
                "state": "upstream_candidate_unavailable",
                "candidate_state": "upstream_candidate_unavailable",
                "candidate_sha256": "",
                "failure_detail": type(exc).__name__,
            }
        for order_index, arm in enumerate(task_arm_orders[task["task_id"]]):
            attempt = run_root / task["task_id"] / arm

            def row(finalizer_state, oracle_state, codes, calls, req_hash=""):
                return _row(
                    task,
                    arm,
                    candidate,
                    finalizer_state,
                    oracle_state,
                    codes,
                    calls,
                    req_hash,
                    order_index,
                    order_hash,
                )

            if candidate.get("state") != "returned":
                if accounting is not None:
                    accounting.skip(
                        task["task_id"], arm, "skipped_candidate_unavailable"
                    )
                rows.append(row("upstream_candidate_unavailable", "not_run", [], 0))
                continue
            if not candidate.get("eligible", True):
                if accounting is not None:
                    accounting.skip(
                        task["task_id"], arm, "skipped_candidate_ineligible"
                    )
                state = _ineligible_state(candidate)
                rows.append(row(state, "not_run", [state], 0))
                continue
            if arm == "C":
                state, codes = score_runner(
                    task, arm, candidate["selected_text"], attempt, candidate
                )
                rows.append(row("not_invoked", state, codes, 0))
                continue
            if arm in stopped_finalizer_arms:
                if accounting is not None:
                    accounting.skip(task["task_id"], arm, "skipped_systemic_arm_block")
                rows.append(
                    row(
                        "not_started_after_systemic_finalizer_block",
                        "not_run",
                        [stopped_finalizer_arms[arm]],
                        0,
                    )
                )
                continue
            try:
                out = (
                    accounting.dispatch(
                        task["task_id"],
                        arm,
                        finalizer_runner,
                        arm,
                        task,
                        candidate,
                        params,
                        attempt,
                    )
                    if accounting is not None
                    else finalizer_runner(arm, task, candidate, params, attempt)
                )
            except Exception as exc:
                if accounting is not None:
                    accounting.check()
                finalizer_state = type(exc).__name__
                stopped_finalizer_arms[arm] = finalizer_state
                rows.append(row(finalizer_state, "not_run", [], 1))
                continue
            fstate = str(out.get("state", "returned"))
            if fstate in SYSTEMIC_FINALIZER_STATES:
                stopped_finalizer_arms[arm] = fstate
            if fstate == "returned" and isinstance(out.get("selected_text"), str):
                state, codes = score_runner(
                    task, arm, out["selected_text"], attempt, candidate
                )
            else:
                state, codes = "not_run", []
            rows.append(
                row(fstate, state, codes, 1, str(out.get("request_body_sha256", "")))
            )
    summary = {
        "schema": "harness.local-finalizer-candidate-prefix-run/v1",
        "denominator": len(tasks) * 3,
        "rows": rows,
        "params_sha256": canonical_sha256(params),
        "task_arm_orders": task_arm_orders,
        "task_arm_order_sha256": order_hash,
    }
    if accounting is not None:
        for item in rows:
            accounting.annotate(item)
        summary["invocation_accounting"] = accounting.finalize()
    _write_json(run_root / "rows.json", rows)
    _write_json(run_root / "run-summary.json", summary)
    return summary
