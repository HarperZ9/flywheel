"""Visual-measurement proof packet -- contract v0 (read-only).

Joins an artifact digest, declared color assumptions, measured metrics with
tolerances, honest display caveats, and a re-derivable MATCH/DRIFT/UNVERIFIABLE
verdict into one validated object. The non-mutation boundary is structural:
`read_only` must be true -- this packet never applies a LUT/ICC/DDC change, so it
can never claim hardware calibration it did not perform.

Stdlib-only. Reuses the proof-surface family's neutrality guards verbatim.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .._decision import validate_decision_summary
from .._failure import validate_failure_labels
from .._validate import Issue, reject_unknown, require_const, require_enum, require_text
from ..authorization_receipt import _reject_forbidden
from ..witness_receipt import _reject_authority_language
from ._calibration import validate_calibration_boundary

PACKET_VERSION = "visual-measurement-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
ARTIFACT_KINDS = {"image", "render", "lut", "icc", "video"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "artifact",
    "color",
    "read_only",
    "measurements",
    "display_caveats",
    "calibration_boundary",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
ARTIFACT_FIELDS = {"name", "sha256", "kind", "width", "height"}
COLOR_FIELDS = {"color_space", "transfer", "white_point", "primaries", "notes"}
MEASUREMENT_FIELDS = {
    "metric",
    "value",
    "unit",
    "target",
    "tolerance",
    "deviation",
    "method",
    "evidence",
}
VERDICTS_FIELDS = {"overall", "per_metric"}
PER_METRIC_FIELDS = {"metric", "status"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_visual_measurement_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate a visual-measurement proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_artifact(data.get("artifact"), issues)
    _validate_color(data.get("color"), issues)
    if data.get("read_only") is not True:
        issues.append(
            Issue("$.read_only", "expected true (read-only / non-mutation boundary)")
        )
    _validate_measurements(data.get("measurements"), issues)
    _validate_str_list(data.get("display_caveats"), "$.display_caveats", issues)
    validate_calibration_boundary(
        data.get("calibration_boundary"), data.get("read_only"), issues
    )
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    _validate_consistency(data, issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_visual_measurement_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_visual_measurement_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _require_hex64(value: Any, path: str, issues: list[Issue]) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        issues.append(Issue(path, "expected 64-char lowercase hex digest"))


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


def _validate_artifact(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.artifact", "expected object"))
        return
    reject_unknown(value, "$.artifact", ARTIFACT_FIELDS, issues)
    require_text(value, "name", issues, "$.artifact.name")
    _require_hex64(value.get("sha256"), "$.artifact.sha256", issues)
    require_enum(value, "kind", ARTIFACT_KINDS, issues, "$.artifact.kind")
    _require_opt_int(value.get("width"), "$.artifact.width", issues)
    _require_opt_int(value.get("height"), "$.artifact.height", issues)


def _validate_color(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.color", "expected object"))
        return
    reject_unknown(value, "$.color", COLOR_FIELDS, issues)
    require_text(value, "color_space", issues, "$.color.color_space")
    require_text(value, "transfer", issues, "$.color.transfer")
    for opt in ("white_point", "primaries", "notes"):
        v = value.get(opt)
        if v is not None and (not isinstance(v, str) or not v.strip()):
            issues.append(Issue(f"$.color.{opt}", "expected non-empty string or null"))


def _validate_measurements(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.measurements", issues)):
        path = f"$.measurements[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, MEASUREMENT_FIELDS, issues)
        require_text(item, "metric", issues, f"{path}.metric")
        require_text(item, "unit", issues, f"{path}.unit")
        require_text(item, "method", issues, f"{path}.method")
        _require_number(item.get("value"), f"{path}.value", issues)
        _require_number(item.get("target"), f"{path}.target", issues)
        _require_number(
            item.get("tolerance"), f"{path}.tolerance", issues, positive=True
        )
        _require_number(item.get("deviation"), f"{path}.deviation", issues, nonneg=True)
        _validate_str_list(item.get("evidence"), f"{path}.evidence", issues)


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
    metrics = data.get("measurements")
    metric_names = (
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
    for name in sorted(set(metric_names)):
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
            if isinstance(v, dict) and v.get("metric") not in set(metric_names):
                issues.append(
                    Issue(
                        f"$.verdicts.per_metric[{index}].metric",
                        f"references unknown metric {v.get('metric')!r}",
                    )
                )
