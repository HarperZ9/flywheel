"""AI4Science claim-to-experiment proof packet -- contract v0.

Harvest of dogfood pass 0104 (AI4ScienceClaimToExperimentReceipt/v1). A portable
proof packet that sits across scientific agents, foundation models, workflow
engines, and lab-record systems: a scientific claim bound to agent actions, a
protocol + workflow runtime, a measurement (or its absence), a reproduction
status, first-class reviewer objections, and a promotion rung that can never
reach a promoted discovery from one packet. Negative results stay first-class.

Stdlib-only. Reuses the proof-surface family's neutrality guards verbatim.
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
from ._gates import validate_promotion_gates

PACKET_VERSION = "ai4science-claim-proof-packet/v0"

OVERALL_VERDICTS = {"MATCH", "DRIFT", "UNVERIFIABLE"}
# A single packet can never reach PROMOTED_DISCOVERY (needs independent review).
PROMOTIONS = {"SOURCE_LEAD", "HYPOTHESIS", "MEASURED", "REPRODUCED", "PEER_REVIEWED"}
REPRODUCTION_STATUSES = {
    "NOT_RUN",
    "SINGLE_RUN",
    "INDEPENDENTLY_REPRODUCED",
    "FAILED_REPRODUCTION",
}
OBJECTION_STATUSES = {"open", "resolved"}

ROOT_FIELDS = {
    "version",
    "packet_id",
    "claim",
    "scope",
    "sources",
    "domain",
    "scientific_claim",
    "agent_actions",
    "protocol",
    "measurement",
    "reproduction",
    "reviewer_objections",
    "negative_result",
    "promotion",
    "failure_labels",
    "verdicts",
    "uncertainty",
    "decision_summary",
    "replication",
}
SOURCE_FIELDS = {"ref", "sha256", "url"}
AGENT_ACTION_FIELDS = {"action", "tool"}
PROTOCOL_FIELDS = {"protocol_ref", "workflow_runtime", "reproducible"}
MEASUREMENT_FIELDS = {"measured", "measurement_ref", "value", "unit"}
REPRODUCTION_FIELDS = {"status"}
OBJECTION_FIELDS = {"objection", "status"}
VERDICTS_FIELDS = {"overall"}

_HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def load_packet(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def validate_ai4science_packet(data: dict[str, Any]) -> list[Issue]:
    """Validate an AI4Science claim-to-experiment packet. Returns [] iff valid."""
    issues: list[Issue] = []
    _reject_forbidden(data, "$", issues)
    _reject_authority_language(data, "$", issues)
    reject_unknown(data, "$", ROOT_FIELDS, issues)
    require_const(data, "version", PACKET_VERSION, issues)
    require_text(data, "packet_id", issues)
    require_text(data, "claim", issues)
    require_text(data, "scope", issues)
    require_text(data, "domain", issues)
    require_text(data, "scientific_claim", issues)
    _validate_sources(data.get("sources"), issues)
    _validate_agent_actions(data.get("agent_actions"), issues)
    _validate_protocol(data.get("protocol"), issues)
    _validate_measurement(data.get("measurement"), issues)
    _validate_reproduction(data.get("reproduction"), issues)
    _validate_objections(data.get("reviewer_objections"), issues)
    if not isinstance(data.get("negative_result"), bool):
        issues.append(Issue("$.negative_result", "expected boolean"))
    require_enum(data, "promotion", PROMOTIONS, issues)
    validate_promotion_gates(data, issues)
    _validate_verdicts(data.get("verdicts"), issues)
    _validate_str_list(data.get("uncertainty"), "$.uncertainty", issues)
    validate_replication(data.get("replication"), issues)
    validate_failure_labels(data.get("failure_labels"), issues)
    validate_decision_summary(
        data.get("decision_summary"), issues, "$.decision_summary"
    )
    return issues


def validate_ai4science_packet_file(path: Path) -> list[Issue]:
    try:
        return validate_ai4science_packet(load_packet(path))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        return [Issue("$", str(exc))]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


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
        _require_opt_text(item.get("url"), f"{path}.url", issues)


def _validate_agent_actions(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.agent_actions", issues)):
        path = f"$.agent_actions[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, AGENT_ACTION_FIELDS, issues)
        require_text(item, "action", issues, f"{path}.action")
        _require_opt_text(item.get("tool"), f"{path}.tool", issues)


def _validate_protocol(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.protocol", "expected object"))
        return
    reject_unknown(value, "$.protocol", PROTOCOL_FIELDS, issues)
    require_text(value, "protocol_ref", issues, "$.protocol.protocol_ref")
    _require_opt_text(
        value.get("workflow_runtime"), "$.protocol.workflow_runtime", issues
    )
    if not isinstance(value.get("reproducible"), bool):
        issues.append(Issue("$.protocol.reproducible", "expected boolean"))


def _validate_measurement(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.measurement", "expected object"))
        return
    reject_unknown(value, "$.measurement", MEASUREMENT_FIELDS, issues)
    if not isinstance(value.get("measured"), bool):
        issues.append(Issue("$.measurement.measured", "expected boolean"))
    _require_opt_text(
        value.get("measurement_ref"), "$.measurement.measurement_ref", issues
    )
    val = value.get("value")
    if val is not None and (isinstance(val, bool) or not isinstance(val, (int, float))):
        issues.append(Issue("$.measurement.value", "expected number or null"))
    _require_opt_text(value.get("unit"), "$.measurement.unit", issues)


def _validate_reproduction(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.reproduction", "expected object"))
        return
    reject_unknown(value, "$.reproduction", REPRODUCTION_FIELDS, issues)
    require_enum(
        value, "status", REPRODUCTION_STATUSES, issues, "$.reproduction.status"
    )


def _validate_objections(value: Any, issues: list[Issue]) -> None:
    for index, item in enumerate(_as_list(value, "$.reviewer_objections", issues)):
        path = f"$.reviewer_objections[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue(path, "expected object"))
            continue
        reject_unknown(item, path, OBJECTION_FIELDS, issues)
        require_text(item, "objection", issues, f"{path}.objection")
        require_enum(item, "status", OBJECTION_STATUSES, issues, f"{path}.status")


def _validate_verdicts(value: Any, issues: list[Issue]) -> None:
    if not isinstance(value, dict):
        issues.append(Issue("$.verdicts", "expected object"))
        return
    reject_unknown(value, "$.verdicts", VERDICTS_FIELDS, issues)
    require_enum(value, "overall", OVERALL_VERDICTS, issues, "$.verdicts.overall")
