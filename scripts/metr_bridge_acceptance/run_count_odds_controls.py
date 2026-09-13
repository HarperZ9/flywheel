"""Run deterministic METR count_odds bridge controls through Inspect.

Draft only. Intended to run from the root of a checked-out
METR/inspect-metr-task-bridge tree after `uv sync --frozen` and after the
count_odds task image plus task-info OCI artifact have been pushed to a local
registry.

Required environment:
  IMAGE_TAG: full image tag, e.g. localhost:5000/inspect-ai/tasks:count_odds-0.0.1
  RECEIPTS_DIR: directory where summaries/logs should be written
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import traceback
from typing import Any

import inspect_ai

from control_solver import MOCK_MODEL_LABEL, SOLVER_EVENTS, fixed_count_odds_solver

from control_outcome import (
    EXPECTED_LOG_MODEL,
    EXPECTED_SCORER_NAME,
    classify_control,
    encode_json_value,
)

# Inspect's pinned eval_async API accepts model=None to disable a default model.
# At the pinned inspect-ai==0.3.189 runtime this records log.eval.model as
# EXPECTED_LOG_MODEL ("none/none"). The mock label below is only the output
# message model string emitted by the deterministic solver; it is not relied on
# to select a provider.
NO_PROVIDER_EVAL_MODEL_ARGUMENT = None
EXPECTED_TASK = "count_odds"
EXPECTED_VERSION = "0.0.1"
EXPECTED_SAMPLE_ID = "hard"



def _get_path(obj: Any, *names: str) -> Any:
    cur = obj
    for name in names:
        if cur is None:
            return None
        cur = getattr(cur, name, None)
    return cur



def verify_bridge_task_shape(image_tag: str) -> dict[str, Any]:
    """Verify the bridge still constructs a task with setup/scoring/cleanup.

    This mirrors the upstream `tests/test_bridge.py` expectation that
    `mtb.bridge(image_tag=...)` resolves the `count_odds` task and version. The
    actual eval below then overrides only the solver, preserving the bridge task
    setup, scorer, and cleanup objects.
    """
    import mtb

    task = mtb.bridge(image_tag=image_tag)
    shape = {
        "task_name": getattr(task, "name", None),
        "task_version": getattr(task, "version", None),
        "has_setup": getattr(task, "setup", None) is not None,
        "has_scorer": getattr(task, "scorer", None) is not None,
        "has_cleanup": getattr(task, "cleanup", None) is not None,
        "has_dataset": getattr(task, "dataset", None) is not None,
        "default_solver_repr": repr(getattr(task, "solver", None)),
        "scorer_repr": repr(getattr(task, "scorer", None)),
        "expected_scorer_name": EXPECTED_SCORER_NAME,
    }
    missing = [key for key in ("has_setup", "has_scorer", "has_cleanup", "has_dataset") if not shape[key]]
    if shape["task_name"] != EXPECTED_TASK or shape["task_version"] != EXPECTED_VERSION or missing:
        raise RuntimeError(f"Unexpected bridge task shape: {shape!r}")
    return shape


def _score_summary(sample: Any) -> dict[str, Any]:
    scores = getattr(sample, "scores", None)
    if not scores:
        return {
            "score_name": None,
            "score_names": [],
            "score_value": None,
            "score_value_repr": None,
            "score_answer": None,
            "score_explanation": "no scores",
            "score_metadata": None,
        }
    if not isinstance(scores, dict):
        return {
            "score_name": None,
            "score_names": [f"<non-mapping:{type(scores).__name__}>"] ,
            "score_value": None,
            "score_value_repr": None,
            "score_answer": None,
            "score_explanation": f"scores object is not a mapping: {type(scores).__name__}",
            "score_metadata": None,
        }

    score_names = [str(name) for name in scores.keys()]
    if EXPECTED_SCORER_NAME not in scores:
        return {
            "score_name": None,
            "score_names": score_names,
            "score_value": None,
            "score_value_repr": None,
            "score_answer": None,
            "score_explanation": f"expected scorer {EXPECTED_SCORER_NAME!r} missing",
            "score_metadata": None,
        }

    score = scores[EXPECTED_SCORER_NAME]
    return {
        "score_name": EXPECTED_SCORER_NAME,
        "score_names": score_names,
        "score_value": encode_json_value(getattr(score, "value", None)),
        "score_value_repr": repr(getattr(score, "value", None)),
        "score_answer": encode_json_value(getattr(score, "answer", None)),
        "score_explanation": getattr(score, "explanation", None),
        "score_metadata": encode_json_value(getattr(score, "metadata", None)),
    }

def _summarize_log(control_name: str, logs: list[Any], bridge_shape: dict[str, Any] | None) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "control": control_name,
        "logs_count": len(logs),
        "solver_event_count": SOLVER_EVENTS.get(control_name, 0),
        "eval_model_argument": NO_PROVIDER_EVAL_MODEL_ARGUMENT,
        "expected_log_model": EXPECTED_LOG_MODEL,
        "expected_scorer_name": EXPECTED_SCORER_NAME,
        "mock_output_model_label": MOCK_MODEL_LABEL,
        "bridge_task_shape": bridge_shape,
    }
    if len(logs) != 1:
        return summary

    log = logs[0]
    samples = getattr(log, "samples", None) or []
    log_task_version = _get_path(log, "eval", "task_version") or _get_path(
        log, "eval", "task_version_resolved"
    )
    shape_task_version = (
        bridge_shape.get("task_version")
        if isinstance(bridge_shape, dict) and not bridge_shape.get("runtime_exception")
        else None
    )
    summary.update(
        {
            "log_status": getattr(log, "status", None),
            "log_error": encode_json_value(getattr(log, "error", None)),
            "log_location": str(getattr(log, "location", None)),
            "log_eval_model": _get_path(log, "eval", "model"),
            "task_name": _get_path(log, "eval", "task"),
            "task_version": log_task_version or shape_task_version,
            "task_version_source": "log" if log_task_version else "bridge_task_shape",
            "sample_count": len(samples),
        }
    )
    if len(samples) == 1:
        sample = samples[0]
        summary.update(
            {
                "sample_id": getattr(sample, "id", None),
                "sample_error": encode_json_value(getattr(sample, "error", None)),
                "sample_completed": getattr(sample, "completed", None),
                "sample_output_model": _get_path(sample, "output", "model"),
                "sample_output_completion": _get_path(sample, "output", "completion"),
            }
        )
        summary.update(_score_summary(sample))
    return summary


async def _run_one(
    *,
    image_tag: str,
    receipts_dir: pathlib.Path,
    name: str,
    answer: str | None,
    expected_value: float | None,
    must_not_equal: float | None = None,
    bridge_shape: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_log_dir = receipts_dir / "logs" / "eval" / name
    run_log_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any]
    try:
        logs = await inspect_ai.eval_async(
            "mtb/bridge",
            model=NO_PROVIDER_EVAL_MODEL_ARGUMENT,
            task_args={"image_tag": image_tag},
            sample_id=EXPECTED_SAMPLE_ID,
            solver=fixed_count_odds_solver(name, answer),
            log_dir=str(run_log_dir),
            log_format="eval",
            fail_on_error=False,
            retry_on_error=0,
            tags=["metr-count-odds-acceptance", name],
            metadata={
                "fixture": EXPECTED_TASK,
                "sample_id": EXPECTED_SAMPLE_ID,
                "control": name,
                "paid_model_calls": False,
                "model_provider": "none",
                "eval_model_argument": None,
                "expected_log_model": EXPECTED_LOG_MODEL,
                "expected_scorer_name": EXPECTED_SCORER_NAME,
                "mock_output_model_label": MOCK_MODEL_LABEL,
            },
        )
        summary = _summarize_log(name, logs, bridge_shape)
    except Exception as exc:  # retain negative evidence and continue other controls
        summary = {
            "control": name,
            "runtime_exception": type(exc).__name__,
            "runtime_exception_message": str(exc),
            "traceback": traceback.format_exc(),
            "logs_count": 0,
            "solver_event_count": SOLVER_EVENTS.get(name, 0),
            "eval_model_argument": NO_PROVIDER_EVAL_MODEL_ARGUMENT,
            "expected_log_model": EXPECTED_LOG_MODEL,
            "expected_scorer_name": EXPECTED_SCORER_NAME,
            "mock_output_model_label": MOCK_MODEL_LABEL,
            "bridge_task_shape": bridge_shape,
        }

    summary["solver_answer"] = answer
    summary["classification"] = classify_control(
        summary,
        expected_value=expected_value,
        must_not_equal=must_not_equal,
    )
    out = receipts_dir / "summary" / f"control-{name}.json"
    out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


async def main() -> None:
    image_tag = os.environ["IMAGE_TAG"]
    receipts_dir = pathlib.Path(os.environ["RECEIPTS_DIR"]).resolve()
    (receipts_dir / "summary").mkdir(parents=True, exist_ok=True)

    bridge_shape = None
    bridge_shape_path = receipts_dir / "summary" / "bridge-task-shape.json"
    try:
        bridge_shape = verify_bridge_task_shape(image_tag)
        bridge_shape_path.write_text(json.dumps(bridge_shape, indent=2, sort_keys=True) + "\n")
    except Exception as exc:
        bridge_shape = {
            "runtime_exception": type(exc).__name__,
            "runtime_exception_message": str(exc),
            "traceback": traceback.format_exc(),
        }
        bridge_shape_path.write_text(json.dumps(bridge_shape, indent=2, sort_keys=True) + "\n")

    controls = [
        {"name": "correct", "answer": "6", "expected_value": 1.0},
        {"name": "wrong", "answer": "1", "expected_value": 0.0},
        {"name": "no_submit_tool_call", "answer": None, "expected_value": None, "must_not_equal": 1.0},
    ]
    summaries = []
    for control in controls:
        summaries.append(
            await _run_one(
                image_tag=image_tag,
                receipts_dir=receipts_dir,
                name=control["name"],
                answer=control["answer"],
                expected_value=control.get("expected_value"),
                must_not_equal=control.get("must_not_equal"),
                bridge_shape=bridge_shape,
            )
        )

    out = receipts_dir / "summary" / "control-summary.json"
    out.write_text(json.dumps(summaries, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summaries, indent=2, sort_keys=True))

    failures = [s for s in summaries if s.get("classification", {}).get("status") != "pass"]
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
