"""Conservation proof packet -- contract v0 (invariant conservation).

Harvest of dogfood passes 0105/0106/0107 (mass-conservation, stoichiometric
invariant, reaction-network corpus). A claimed transformation is asserted to
conserve a declared invariant, proven by independent witnesses (an exact
algebraic residual and/or a numeric drift bound) AND falsified by a required
negative fixture that must break the invariant. Domain-general: the same shape
covers mass/energy balance, refactor-preserves-total, RL return, and
optimization objective preservation. Stdlib-only; reuses the family guards.
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
from ._gates import validate_boundary_fixture, validate_negative_fixture

PACKET_VERSION = "conservation-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
WITNESS_KINDS = {"algebraic", "numeric", "symbolic"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "transformation",
    "invariant",
    "witnesses",
    "negative_fixture",
    "boundary_fixture",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
}
SOURCE_FIELDS = {"ref", "sha256"}
TRANSFORMATION_FIELDS = {"description", "domain"}
INVARIANT_FIELDS = {"name", "declared"}
WITNESS_FIELDS = {"kind", "drift", "tolerance", "method"}
VERDICTS_FIELDS = {"overall"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_conservation_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate a conservation proof packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_transformation(data.get("transformation"), issues)
    _validate_invariant(data.get("invariant"), issues)
    _validate_witnesses(data.get("witnesses"), issues)
    validate_negative_fixture(data.get("negative_fixture"), issues)
    validate_boundary_fixture(data.get("boundary_fixture"), issues)
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_conservation_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_conservation_packet(load_packet(path))
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


def _validate_transformation(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.transformation", "expected object"))
        return
    reject_unknown(value, "$.transformation", TRANSFORMATION_FIELDS, issues)
    require_text(value, "description", issues, "$.transformation.description")
    require_text(value, "domain", issues, "$.transformation.domain")


def _validate_invariant(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.invariant", "expected object"))
        return
    reject_unknown(value, "$.invariant", INVARIANT_FIELDS, issues)
    require_text(value, "name", issues, "$.invariant.name")
    _require_opt_text(value.get("declared"), "$.invariant.declared", issues)


def _validate_witnesses(value: Any, issues: list[Issue]) -> None:
    witnesses = _as_list(value, "$.witnesses", issues)
    if isinstance(value, list) and not witnesses:
        issues.append(
            Issue(
                "$.witnesses", "expected at least one independent conservation witness"
            )
        )
    for index, item in enumerate(witnesses):
        path = f"$.witnesses[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, WITNESS_FIELDS, issues)
        require_enum(item, "kind", WITNESS_KINDS, issues, f"{path}.kind")
        require_text(item, "method", issues, f"{path}.method")
        drift = item.get("drift")
        if not _is_number(drift) or drift < 0:
            issues.append(Issue(f"{path}.drift", "expected a non-negative number"))
        tolerance = item.get("tolerance")
        if not _is_number(tolerance) or tolerance <= 0:
            issues.append(Issue(f"{path}.tolerance", "expected a number > 0"))


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
