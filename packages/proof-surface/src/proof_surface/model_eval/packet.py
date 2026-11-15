"""Model-eval proof packet -- contract v0 (model-foundry / eval forge).

A model run + eval set + directional metrics + objective, joined into one
validated object with a re-derivable verdict and a **default-deny** promotion
decision: a model may be promoted only if the overall verdict is MATCH. Stdlib-only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .._decision import validate_decision_summary
from .._failure import validate_failure_labels
from .._replication import validate_replication
from .._validate import Issue, reject_unknown, require_const, require_enum, require_text
from ..authorization_receipt import _reject_forbidden
from ..witness_receipt import _reject_authority_language

PACKET_VERSION = "model-eval-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
PROVIDERS = {"hosted", "local", "open-weight"}
DIRECTIONS = {"maximize", "minimize", "within"}
OUTCOMES = {"promote", "reject", "needs-human"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "model",
    "eval_set",
    "objective",
    "metrics",
    "decision",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
    "replication",
}
MODEL_FIELDS = {"id", "provider", "config_hash"}
EVAL_SET_FIELDS = {"name", "ref", "sha256", "size"}
OBJECTIVE_FIELDS = {"name", "summary"}
METRIC_FIELDS = {
    "metric",
    "value",
    "target",
    "direction",
    "tolerance",
    "deviation",
    "unit",
    "method",
    "evidence",
}
DECISION_FIELDS = {"outcome", "reason"}
VERDICTS_FIELDS = {"overall", "per_metric"}
PER_METRIC_FIELDS = {"metric", "status"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_model_eval_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate a model-eval proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_model(data.get("model"), issues)
    _validate_eval_set(data.get("eval_set"), issues)
    _validate_objective(data.get("objective"), issues)
    _validate_metrics(data.get("metrics"), issues)
    _validate_decision(data.get("decision"), issues)
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    _validate_consistency(data, issues)
    validate_replication(data.get("replication"), issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_model_eval_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_model_eval_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _require_opt_hex64(value: Any, path: str, issues: list[Issue]) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        issues.append(Issue(path, "expected 64-char lowercase hex digest or null"))


def _require_number(
    value: Any,
    path: str,
    issues: list[Issue],
    *,
    positive: bool = False,
    nonneg: bool = False,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        issues.append(Issue(path, "expected number"))
        return
    if positive and not value > 0:
        issues.append(Issue(path, "expected number > 0"))
    if nonneg and value < 0:
        issues.append(Issue(path, "expected number >= 0"))


def _require_opt_int(value: Any, path: str, issues: list[Issue]) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        issues.append(Issue(path, "expected non-negative integer or null"))


def _as_list(value: Any, path: str, issues: list[Issue]) -> list[Any]:
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return []
    return value


def _validate_model(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.model", "expected object"))
        return
    reject_unknown(value, "$.model", MODEL_FIELDS, issues)
    require_text(value, "id", issues, "$.model.id")
    require_enum(value, "provider", PROVIDERS, issues, "$.model.provider")
    _require_opt_hex64(value.get("config_hash"), "$.model.config_hash", issues)


def _validate_eval_set(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.eval_set", "expected object"))
        return
    reject_unknown(value, "$.eval_set", EVAL_SET_FIELDS, issues)
    require_text(value, "name", issues, "$.eval_set.name")
    require_text(value, "ref", issues, "$.eval_set.ref")
    _require_opt_hex64(value.get("sha256"), "$.eval_set.sha256", issues)
    _require_opt_int(value.get("size"), "$.eval_set.size", issues)


def _validate_objective(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.objective", "expected object"))
        return
    reject_unknown(value, "$.objective", OBJECTIVE_FIELDS, issues)
    require_text(value, "name", issues, "$.objective.name")
    require_text(value, "summary", issues, "$.objective.summary")


def _validate_metrics(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.metrics", issues)):
        path = f"$.metrics[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, METRIC_FIELDS, issues)
        require_text(item, "metric", issues, f"{path}.metric")
        require_text(item, "method", issues, f"{path}.method")
        require_enum(item, "direction", DIRECTIONS, issues, f"{path}.direction")
        _require_number(item.get("value"), f"{path}.value", issues)
        _require_number(item.get("target"), f"{path}.target", issues)
        _require_number(
            item.get("tolerance"), f"{path}.tolerance", issues, positive=True
        )
        _require_number(item.get("deviation"), f"{path}.deviation", issues, nonneg=True)
        unit = item.get("unit")
        if unit is not None and (not isinstance(unit, str) or not unit.strip()):
            issues.append(Issue(f"{path}.unit", "expected non-empty string or null"))
        _validate_str_list(item.get("evidence"), f"{path}.evidence", issues)


def _validate_decision(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.decision", "expected object"))
        return
    reject_unknown(value, "$.decision", DECISION_FIELDS, issues)
    require_enum(value, "outcome", OUTCOMES, issues, "$.decision.outcome")
    require_text(value, "reason", issues, "$.decision.reason")


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
    for index, item in enumerate(
        _as_list(value.get("per_metric"), "$.verdicts.per_metric", issues)
    ):
        path = f"$.verdicts.per_metric[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, PER_METRIC_FIELDS, issues)
        require_text(item, "metric", issues, f"{path}.metric")
        require_enum(item, "status", OVERALL_VERDICTS, issues, f"{path}.status")


def _validate_str_list(value: Any, path: str, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, path, issues)):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"{path}[{index}]", "expected non-empty string"))


def _validate_consistency(data: dict[str, Any], issues: list[Issue]) -> None:
    metrics = data.get("metrics")
    names = (
        [
            m["metric"]
            for m in metrics
            if isinstance(m, dict) and isinstance(m.get("metric"), str)
        ]
        if isinstance(metrics, list)
        else []
    )
    verdicts = data.get("verdicts") if isinstance(data.get("verdicts"), dict) else {}
    per_metric = verdicts.get("per_metric") if isinstance(verdicts, dict) else None
    verdict_names = (
        [v.get("metric") for v in per_metric if isinstance(v, dict)]
        if isinstance(per_metric, list)
        else []
    )
    for name in sorted(set(names)):
        count = verdict_names.count(name)
        if count == 0:
            issues.append(
                Issue("$.verdicts.per_metric", f"no verdict for metric {name!r}")
            )
        elif count > 1:
            issues.append(
                Issue("$.verdicts.per_metric", f"multiple verdicts for metric {name!r}")
            )
    if isinstance(per_metric, list):
        for index, v in enumerate(per_metric):
            if isinstance(v, dict) and v.get("metric") not in set(names):
                issues.append(
                    Issue(
                        f"$.verdicts.per_metric[{index}].metric",
                        f"references unknown metric {v.get('metric')!r}",
                    )
                )
    # Default-deny: a model may be promoted only if the overall verdict is MATCH.
    decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
    overall = verdicts.get("overall") if isinstance(verdicts, dict) else None
    if decision.get("outcome") == "promote" and overall != "MATCH":
        issues.append(
            Issue(
                "$.decision.outcome", f"promote requires overall MATCH, got {overall!r}"
            )
        )
