"""Control-certificate proof packet -- contract v0 (decrease/stability certificate).

Harvest of dogfood passes 0112 (Lyapunov stability certificate) and 0113
(constrained-MPC feasibility), scoped in by the operator's robotics and
cybernetics lane. A controller or iterative process claiming stability,
termination, or convergence carries a declared certificate, witnessed
conditions with real residuals, a REQUIRED negative fixture that must violate
the certificate, and an explicit sim-to-real boundary. Decrease is not
constancy: a conserved quantity belongs to the conservation wedge; this wedge
covers quantities that must strictly hold a directional condition.
Stdlib-only; reuses the family guards.
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
from ._gates import (
    CONDITION_KINDS,
    validate_kind_completeness,
    validate_negative_fixture,
    validate_sim_to_real,
)

PACKET_VERSION = "control-certificate-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
CERTIFICATE_KINDS = {
    "lyapunov",
    "ranking-function",
    "contraction-metric",
    "mpc-feasibility",
}
REGIMES = {"simulation", "hardware", "hybrid"}
# Certificate origins are never conflated: a synthesized or independently
# verified certificate is a different evidence class than an author-asserted one.
PROVENANCES = {"synthesized", "verified", "author-asserted"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "system",
    "certificate",
    "witnesses",
    "negative_fixture",
    "sim_to_real",
    "trajectory",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
SOURCE_FIELDS = {"ref", "sha256"}
SYSTEM_FIELDS = {"description", "domain", "regime"}
CERTIFICATE_FIELDS = {"kind", "name", "declared", "provenance", "provenance_ref"}
WITNESS_FIELDS = {"condition", "residual", "tolerance", "method"}
TRAJECTORY_FIELDS = {"log_sha256", "samples", "description"}
VERDICTS_FIELDS = {"overall"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_control_certificate_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate a control-certificate proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_sources(data.get("sources"), issues)
    system = data.get("system")
    _validate_system(system, issues)
    certificate = data.get("certificate")
    _validate_certificate(certificate, issues)
    _validate_witnesses(data.get("witnesses"), issues)
    kind = certificate.get("kind") if isinstance(certificate, dict) else None
    validate_kind_completeness(kind, data.get("witnesses"), issues)
    validate_negative_fixture(data.get("negative_fixture"), issues)
    regime = system.get("regime") if isinstance(system, dict) else None
    validate_sim_to_real(data.get("sim_to_real"), regime, issues)
    _validate_trajectory(data.get("trajectory"), issues)
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_control_certificate_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_control_certificate_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _require_opt_text(value: Any, path: str, issues: list[Issue]) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        issues.append(Issue(path, "expected non-empty string or null"))


def _as_list(value: Any, path: str, issues: list[Issue]) -> list[Any]:
    if not isinstance(value, list):
        issues.append(Issue(path, "expected array"))
        return []
    return value


def _validate_str_list(value: Any, path: str, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, path, issues)):
        if not isinstance(item, str) or not item.strip():
            issues.append(Issue(f"{path}[{index}]", "expected non-empty string"))


def _validate_sources(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.sources", issues)):
        path = f"$.sources[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, SOURCE_FIELDS, issues)
        require_text(item, "ref", issues, f"{path}.ref")
        sha = item.get("sha256")
        if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
            issues.append(
                Issue(f"{path}.sha256", "expected 64-char lowercase hex digest")
            )


def _validate_system(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.system", "expected object"))
        return
    reject_unknown(value, "$.system", SYSTEM_FIELDS, issues)
    require_text(value, "description", issues, "$.system.description")
    require_text(value, "domain", issues, "$.system.domain")
    require_enum(value, "regime", REGIMES, issues, "$.system.regime")


def _validate_certificate(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.certificate", "expected object"))
        return
    reject_unknown(value, "$.certificate", CERTIFICATE_FIELDS, issues)
    require_enum(value, "kind", CERTIFICATE_KINDS, issues, "$.certificate.kind")
    require_text(value, "name", issues, "$.certificate.name")
    _require_opt_text(value.get("declared"), "$.certificate.declared", issues)
    require_enum(
        value, "provenance", PROVENANCES, issues, "$.certificate.provenance"
    )
    _require_opt_text(
        value.get("provenance_ref"), "$.certificate.provenance_ref", issues
    )


def _validate_trajectory(value: Any, issues: list[Issue]) -> None:
    """The binding to what was actually run: without it there is nothing the
    verdict is a verdict OF."""
    if not isinstance(value, dict):
        issues.append(
            Issue("$.trajectory", "expected object (the executed-log binding)")
        )
        return
    reject_unknown(value, "$.trajectory", TRAJECTORY_FIELDS, issues)
    sha = value.get("log_sha256")
    if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
        issues.append(
            Issue("$.trajectory.log_sha256", "expected 64-char lowercase hex digest")
        )
    samples = value.get("samples")
    if not isinstance(samples, int) or isinstance(samples, bool) or samples <= 0:
        issues.append(Issue("$.trajectory.samples", "expected an integer > 0"))
    _require_opt_text(value.get("description"), "$.trajectory.description", issues)


def _validate_witnesses(value: Any, issues: list[Issue]) -> None:
    witnesses = _as_list(value, "$.witnesses", issues)
    if isinstance(value, list) and not witnesses:
        issues.append(
            Issue("$.witnesses", "expected at least one witnessed condition")
        )
    for index, item in enumerate(witnesses):
        path = f"$.witnesses[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, WITNESS_FIELDS, issues)
        require_enum(item, "condition", CONDITION_KINDS, issues, f"{path}.condition")
        require_text(item, "method", issues, f"{path}.method")
        residual = item.get("residual")
        if not _is_number(residual) or residual < 0:
            issues.append(Issue(f"{path}.residual", "expected a non-negative number"))
        tolerance = item.get("tolerance")
        if not _is_number(tolerance) or tolerance <= 0:
            issues.append(Issue(f"{path}.tolerance", "expected a number > 0"))


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
