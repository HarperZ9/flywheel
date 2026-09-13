"""Pure classification helpers for METR count_odds bridge controls."""

from __future__ import annotations

import math
import numbers
from typing import Any


PASS = "pass"
FAIL = "fail"
EXPECTED_SCORER_NAME = "score_metr_task"
EXPECTED_LOG_MODEL = "none/none"


def encode_json_value(value: Any) -> Any:
    """Encode values for JSON without hiding non-finite numbers."""
    if isinstance(value, float):
        if math.isnan(value):
            return {"kind": "nonfinite", "repr": "nan"}
        if math.isinf(value):
            return {"kind": "nonfinite", "repr": "inf" if value > 0 else "-inf"}
    if isinstance(value, dict):
        return {str(k): encode_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode_json_value(v) for v in value]
    if hasattr(value, "model_dump"):
        return encode_json_value(value.model_dump(mode="json"))
    return value


def is_nonfinite_marker(value: Any) -> bool:
    return isinstance(value, dict) and value.get("kind") == "nonfinite"


def is_finite_real_number(value: Any) -> bool:
    """Return True only for finite real numeric scores, excluding bool."""
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def classify_control(
    summary: dict[str, Any],
    *,
    expected_value: float | None,
    must_not_equal: float | None = None,
    expected_scorer_name: str = EXPECTED_SCORER_NAME,
    expected_log_model: str = EXPECTED_LOG_MODEL,
) -> dict[str, Any]:
    """Classify one control run with fail-closed evidence requirements.

    A negative control only passes after the expected task, sample, scorer, log
    status, no-provider eval model, and solver execution are observed. Missing
    samples, task errors, missing or misnamed scores, null/non-numeric/bool
    scores, and non-finite scores fail instead of counting as "not 1". The current fallback-answer control is a no-submit-tool-call control, not proof that the bridge observed no answer at all.
    """

    reasons: list[str] = []

    if summary.get("runtime_exception"):
        reasons.append("runtime_exception")
    bridge_shape = summary.get("bridge_task_shape") or {}
    if bridge_shape.get("runtime_exception"):
        reasons.append("bridge_task_shape_error")
    for key in ("has_setup", "has_scorer", "has_cleanup"):
        if bridge_shape.get(key) is not True:
            reasons.append(f"bridge_{key}_not_observed")
    if summary.get("logs_count") != 1:
        reasons.append("expected_exactly_one_eval_log")
    if summary.get("log_status") != "success":
        reasons.append("log_status_not_success")
    if summary.get("log_error") not in (None, ""):
        reasons.append("log_error_present")
    if summary.get("log_eval_model") != expected_log_model:
        reasons.append(
            f"unexpected_eval_model_expected_{expected_log_model!r}_observed_{summary.get('log_eval_model')!r}"
        )
    if summary.get("task_name") != "count_odds":
        reasons.append("unexpected_task_name")
    if summary.get("task_version") != "0.0.1":
        reasons.append("unexpected_task_version")
    if summary.get("sample_count") != 1:
        reasons.append("expected_exactly_one_sample")
    if summary.get("sample_id") != "hard":
        reasons.append("unexpected_sample_id")
    if summary.get("sample_error") not in (None, ""):
        reasons.append("sample_error_present")
    if summary.get("solver_event_count", 0) < 1:
        reasons.append("solver_not_observed")

    score_name = summary.get("score_name")
    if score_name in (None, ""):
        reasons.append("score_not_observed")
    elif score_name != expected_scorer_name:
        reasons.append(
            f"unexpected_score_name_expected_{expected_scorer_name!r}_observed_{score_name!r}"
        )

    value = summary.get("score_value")
    if is_nonfinite_marker(value):
        reasons.append("score_nonfinite")
    elif not is_finite_real_number(value):
        reasons.append(f"score_not_finite_real_observed_{type(value).__name__}")
    else:
        observed = float(value)
        if expected_value is not None and observed != float(expected_value):
            reasons.append(f"score_expected_{expected_value!r}_observed_{value!r}")
        elif must_not_equal is not None and observed == float(must_not_equal):
            reasons.append(f"score_must_not_equal_{must_not_equal!r}")

    return {
        "status": PASS if not reasons else FAIL,
        "reasons": reasons,
    }
