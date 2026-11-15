from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Callable, ClassVar

from .adapter import INTEGRATION_TIERS
from .canonical_json import canonical_json_text, is_sha256_ref
from .capsule_types import SOURCE_STATE_DIGEST_KEYS
from .omission import Omission, validate_omission
from .readiness import ReadinessResult, validate_readiness_result
from .transform import TransformReceipt, validate_transform_receipt

BOOTSTRAP_WITNESS_SCHEMA = "canon.bootstrap-witness/v1"
BOOTSTRAP_CHECK_NAMES = ("freshness", "conflicts", "secrets", "budget", "reachability", "readiness")
BOOTSTRAP_CHECK_VERDICTS = ("pass", "fail", "warn", "blocked", "unknown")


@dataclass(frozen=True, slots=True)
class BootstrapCheck:
    name: str
    verdict: str
    evidence_refs: tuple[str, ...] = ()
    details: dict = field(default_factory=dict)

    schema: ClassVar[str] = BOOTSTRAP_WITNESS_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_refs", _tuple_sequence(self.evidence_refs))
        object.__setattr__(self, "details", copy.deepcopy(self.details))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "evidence_refs": _json_sequence(self.evidence_refs),
            "details": copy.deepcopy(self.details),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BootstrapCheck":
        if not isinstance(d, dict):
            raise TypeError(f"bootstrap check JSON must be an object, got {type(d).__name__}")
        return cls(
            name=d["name"],
            verdict=d["verdict"],
            evidence_refs=d.get("evidence_refs", ()),
            details=d.get("details", {}),
        )


@dataclass(frozen=True, slots=True)
class BootstrapWitness:
    run_id: str
    capsule_id: str
    capsule_manifest_sha256: str
    source_state: dict
    target: dict
    integration_tier_claimed: str
    host_enforcement_observed: bool
    started_at: str
    checks: tuple[BootstrapCheck, ...]
    omissions: tuple[Omission, ...]
    lossy_transforms: tuple[TransformReceipt, ...]
    readiness_result: ReadinessResult
    does_not_prove: tuple[str, ...] = ()

    schema: ClassVar[str] = BOOTSTRAP_WITNESS_SCHEMA

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_state", copy.deepcopy(self.source_state))
        object.__setattr__(self, "target", copy.deepcopy(self.target))
        object.__setattr__(self, "checks", _tuple_of(self.checks, BootstrapCheck.from_dict))
        object.__setattr__(self, "omissions", _tuple_of(self.omissions, Omission.from_dict))
        object.__setattr__(self, "lossy_transforms", _tuple_of(self.lossy_transforms, TransformReceipt.from_dict))
        object.__setattr__(self, "readiness_result", _value_of(self.readiness_result, ReadinessResult.from_dict))
        object.__setattr__(self, "does_not_prove", _tuple_sequence(self.does_not_prove))

    def to_dict(self) -> dict:
        return {
            "schema": BOOTSTRAP_WITNESS_SCHEMA,
            "run_id": self.run_id,
            "capsule_id": self.capsule_id,
            "capsule_manifest_sha256": self.capsule_manifest_sha256,
            "source_state": copy.deepcopy(self.source_state),
            "target": copy.deepcopy(self.target),
            "integration_tier_claimed": self.integration_tier_claimed,
            "host_enforcement_observed": self.host_enforcement_observed,
            "started_at": self.started_at,
            "checks": _items_to_json(self.checks, BootstrapCheck),
            "omissions": _items_to_json(self.omissions, Omission),
            "lossy_transforms": _items_to_json(self.lossy_transforms, TransformReceipt),
            "readiness_result": self.readiness_result.to_dict()
            if isinstance(self.readiness_result, ReadinessResult) else copy.deepcopy(self.readiness_result),
            "does_not_prove": _json_sequence(self.does_not_prove),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BootstrapWitness":
        if not isinstance(d, dict):
            raise TypeError(f"bootstrap witness JSON must be an object, got {type(d).__name__}")
        got = d.get("schema")
        if got != BOOTSTRAP_WITNESS_SCHEMA:
            raise ValueError(f"expected schema {BOOTSTRAP_WITNESS_SCHEMA!r}, got {got!r}")
        return cls(
            run_id=d["run_id"],
            capsule_id=d["capsule_id"],
            capsule_manifest_sha256=d["capsule_manifest_sha256"],
            source_state=d["source_state"],
            target=d["target"],
            integration_tier_claimed=d["integration_tier_claimed"],
            host_enforcement_observed=d["host_enforcement_observed"],
            started_at=d["started_at"],
            checks=d["checks"],
            omissions=d["omissions"],
            lossy_transforms=d["lossy_transforms"],
            readiness_result=d["readiness_result"],
            does_not_prove=d.get("does_not_prove", ()),
        )

    def to_json(self) -> str:
        return canonical_json_text(self.to_dict())


def validate_bootstrap_witness(witness: BootstrapWitness) -> list[str]:
    if not isinstance(witness, BootstrapWitness):
        return ["bootstrap witness must be a BootstrapWitness"]
    problems: list[str] = []
    _check_non_empty_string("run_id", witness.run_id, problems)
    _check_sha256("capsule_id", witness.capsule_id, problems)
    _check_sha256("capsule_manifest_sha256", witness.capsule_manifest_sha256, problems)
    if _valid_hashes_differ(witness.capsule_id, witness.capsule_manifest_sha256):
        problems.append("capsule_manifest_sha256 must match capsule_id")
    _check_dict("source_state", witness.source_state, problems)
    _check_dict("target", witness.target, problems)
    _check_source_state(witness.source_state, problems)
    _check_target(witness.target, problems)
    _check_member("integration_tier_claimed", witness.integration_tier_claimed, INTEGRATION_TIERS, problems)
    _check_bool("host_enforcement_observed", witness.host_enforcement_observed, problems)
    _check_non_empty_string("started_at", witness.started_at, problems)
    _check_nested_tuple("checks", witness.checks, validate_bootstrap_check, problems)
    _check_nested_tuple("omissions", witness.omissions, validate_omission, problems)
    _check_nested_tuple("lossy_transforms", witness.lossy_transforms, validate_transform_receipt, problems)
    _check_readiness_result(witness, problems)
    _check_string_tuple("does_not_prove", witness.does_not_prove, problems)
    _check_observed_claim(witness, problems)
    return problems


def validate_bootstrap_check(check: BootstrapCheck) -> list[str]:
    if not isinstance(check, BootstrapCheck):
        return ["bootstrap check must be a BootstrapCheck"]
    problems: list[str] = []
    _check_member("name", check.name, BOOTSTRAP_CHECK_NAMES, problems)
    _check_member("verdict", check.verdict, BOOTSTRAP_CHECK_VERDICTS, problems)
    _check_string_tuple("evidence_refs", check.evidence_refs, problems)
    _check_dict("details", check.details, problems)
    return problems


def _tuple_sequence(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return tuple(copy.deepcopy(item) for item in value)
    return copy.deepcopy(value)


def _json_sequence(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return [copy.deepcopy(item) for item in value]
    return copy.deepcopy(value)


def _tuple_of(value: object, factory: Callable[[dict], object]) -> object:
    if not isinstance(value, (list, tuple)):
        return copy.deepcopy(value)
    return tuple(_value_of(item, factory) for item in value)


def _value_of(value: object, factory: Callable[[dict], object]) -> object:
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    try:
        return factory(value)
    except (KeyError, TypeError, ValueError):
        return copy.deepcopy(value)


def _items_to_json(value: object, item_type: type) -> object:
    if not isinstance(value, (list, tuple)):
        return copy.deepcopy(value)
    return [item.to_dict() if isinstance(item, item_type) else copy.deepcopy(item) for item in value]


def _check_non_empty_string(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, str) or value == "":
        problems.append(f"{name} must be a non-empty string")


def _check_sha256(name: str, value: object, problems: list[str]) -> None:
    if not is_sha256_ref(value):
        problems.append(f"{name} must be a sha256: reference")


def _valid_hashes_differ(left: object, right: object) -> bool:
    return is_sha256_ref(left) and is_sha256_ref(right) and left != right


def _check_member(name: str, value: object, allowed: tuple[str, ...], problems: list[str]) -> None:
    if value not in allowed:
        problems.append(f"{name} must be one of {list(allowed)}, got {value!r}")


def _check_bool(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, bool):
        problems.append(f"{name} must be bool")


def _check_dict(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, dict):
        problems.append(f"{name} must be a dict")


def _check_source_state(value: object, problems: list[str]) -> None:
    if not isinstance(value, dict):
        return
    if not is_sha256_ref(value.get("records_digest")):
        problems.append("source_state.records_digest must be a sha256: reference")
    for key in SOURCE_STATE_DIGEST_KEYS[1:]:
        if key in value and value[key] is not None and not is_sha256_ref(value[key]):
            problems.append(f"source_state.{key} must be a sha256: reference")


def _check_target(value: object, problems: list[str]) -> None:
    if not isinstance(value, dict):
        return
    _check_non_empty_string("target.adapter", value.get("adapter"), problems)
    _check_non_empty_string("target.surface", value.get("surface"), problems)


def _check_string_tuple(name: str, value: object, problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for index, item in enumerate(value):
        if not isinstance(item, str):
            problems.append(f"{name}[{index}] must be a string")


def _check_nested_tuple(name: str, value: object, validator: Callable[[object], list[str]], problems: list[str]) -> None:
    if not isinstance(value, tuple):
        problems.append(f"{name} must be a tuple")
        return
    for index, item in enumerate(value):
        for problem in validator(item):
            problems.append(f"{name}[{index}]: {problem}")


def _check_readiness_result(witness: BootstrapWitness, problems: list[str]) -> None:
    result = witness.readiness_result
    for problem in validate_readiness_result(result):
        problems.append(f"readiness_result: {problem}")
    if isinstance(result, ReadinessResult) and result.capsule_id != witness.capsule_id:
        problems.append("readiness_result.capsule_id must match capsule_id")


def _check_observed_claim(witness: BootstrapWitness, problems: list[str]) -> None:
    if witness.host_enforcement_observed is not True:
        return
    if witness.integration_tier_claimed != "enforced":
        problems.append("host_enforcement_observed requires integration_tier_claimed 'enforced'")
        return
    _check_enforced_readiness(witness, problems)
    _check_enforced_checks(witness, problems)


def _check_enforced_readiness(witness: BootstrapWitness, problems: list[str]) -> None:
    result = witness.readiness_result
    if not isinstance(result, ReadinessResult) or result.verdict != "pass":
        problems.append("enforced host enforcement observation requires readiness_result verdict pass")
    readiness_checks = tuple(
        check for check in witness.checks
        if isinstance(check, BootstrapCheck) and check.name == "readiness"
    ) if isinstance(witness.checks, tuple) else ()
    if not any(check.verdict == "pass" for check in readiness_checks):
        problems.append("enforced host enforcement observation requires a passing readiness check")


def _check_enforced_checks(witness: BootstrapWitness, problems: list[str]) -> None:
    if not isinstance(witness.checks, tuple):
        return
    for index, check in enumerate(witness.checks):
        if not isinstance(check, BootstrapCheck):
            continue
        if check.verdict != "pass":
            problems.append(f"enforced host enforcement observation requires checks[{index}] to pass")
        if not isinstance(check.evidence_refs, tuple) or not check.evidence_refs:
            problems.append(f"enforced host enforcement observation requires checks[{index}].evidence_refs")
