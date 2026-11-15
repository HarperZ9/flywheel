from __future__ import annotations

from dataclasses import dataclass

from .canonical_json import is_sha256_ref
from .omission import Omission
from .retention_receipts import retention_artifacts
from .retention_safety import (
    add_unique as _add,
    non_bool_int as _non_bool_int,
    normalize as _normalize,
    safe_identifier as _safe_identifier,
    safe_locator as _safe_locator,
    tuple_or_original as _tuple_or_original,
)
from .transform import TransformReceipt

RETENTION_ACTIONS = ("retain", "tombstone", "purge-derived", "purge-all")
DERIVED_STORES = (
    "sqlite",
    "files",
    "vault",
    "managed-surface",
    "capsule",
    "canonpack",
    "witness",
    "backup",
    "exported-artifact",
)

@dataclass(frozen=True, slots=True)
class DerivedArtifactRef:
    store: str
    locator: str
    content_sha256: str | None
    contains_raw: bool


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    subject_id: str
    action: str
    retain_content_hash: bool
    derived_stores: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "derived_stores", _tuple_or_original(self.derived_stores))


@dataclass(frozen=True, slots=True)
class Tombstone:
    subject_id: str
    reason_code: str
    purged_at_ord: int
    content_sha256: str | None


@dataclass(frozen=True, slots=True)
class RetentionPlan:
    ok: bool
    subject_id: str
    action: str
    refs_to_purge: tuple[DerivedArtifactRef, ...]
    tombstone: Tombstone | None
    omissions: tuple[Omission, ...]
    receipts: tuple[TransformReceipt, ...]
    violations: tuple[str, ...]
    deleted_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "refs_to_purge", _tuple_or_original(self.refs_to_purge))
        object.__setattr__(self, "omissions", _tuple_or_original(self.omissions))
        object.__setattr__(self, "receipts", _tuple_or_original(self.receipts))
        object.__setattr__(self, "violations", _tuple_or_original(self.violations))
        object.__setattr__(self, "deleted_paths", _tuple_or_original(self.deleted_paths))


def validate_retention_policy(policy: RetentionPolicy) -> tuple[str, ...]:
    if type(policy) is not RetentionPolicy:
        return ("invalid-policy",)
    violations: list[str] = []
    if not _safe_identifier(policy.subject_id):
        _add(violations, "invalid-subject-id")
    if type(policy.action) is not str or policy.action not in RETENTION_ACTIONS:
        _add(violations, "invalid-action")
    if type(policy.retain_content_hash) is not bool:
        _add(violations, "invalid-retain-content-hash")
    _validate_policy_stores(policy.derived_stores, violations)
    return tuple(violations)


def make_tombstone(
    subject_id: str,
    *,
    reason_code: str,
    purged_at_ord: int,
    retain_content_hash: bool,
    content_sha256: str | None,
) -> Tombstone:
    violations: list[str] = []
    if not _safe_identifier(subject_id):
        _add(violations, "invalid-subject-id")
    if not _safe_identifier(reason_code):
        _add(violations, "invalid-reason-code")
    if not _non_bool_int(purged_at_ord) or purged_at_ord < 0:
        _add(violations, "invalid-purged-at-ord")
    if type(retain_content_hash) is not bool:
        _add(violations, "invalid-retain-content-hash")
    if retain_content_hash is True and not _is_sha256_ref(content_sha256):
        _add(violations, "invalid-content-sha256")
    if violations:
        raise ValueError("invalid-tombstone: " + "; ".join(violations))
    retained = content_sha256 if retain_content_hash is True else None
    return Tombstone(subject_id, reason_code, purged_at_ord, retained)


def plan_retention(
    subject_id: str,
    *,
    policy: RetentionPolicy,
    derived_refs: tuple[DerivedArtifactRef, ...],
    content_sha256: str | None,
) -> RetentionPlan:
    policy_violations = list(validate_retention_policy(policy))
    ref_violations, valid_refs = _validate_refs(derived_refs)
    violations = policy_violations + list(ref_violations)
    checked_subject = subject_id if _safe_identifier(subject_id) else ""
    action = policy.action if type(policy) is RetentionPolicy and type(policy.action) is str else ""
    if type(policy) is RetentionPolicy:
        _validate_plan_inputs(subject_id, policy, content_sha256, violations)
    selected = ()
    if _can_select_refs(policy) and not ref_violations:
        selected = _refs_for_policy(policy, _selected_refs(policy, valid_refs))
    _validate_coverage(policy, valid_refs, violations)
    if violations:
        return _plan(False, checked_subject, action, selected, None, (), (), tuple(violations))
    if action == "retain":
        return _plan(True, checked_subject, action, (), None, (), (), ())
    tombstone = make_tombstone(
        checked_subject,
        reason_code=action,
        purged_at_ord=0,
        retain_content_hash=policy.retain_content_hash,
        content_sha256=content_sha256,
    )
    omission, receipt = retention_artifacts(checked_subject, action, selected, tombstone, policy.retain_content_hash)
    return _plan(True, checked_subject, action, selected, tombstone, (omission,), (receipt,), ())


def _plan(
    ok: bool,
    subject_id: str,
    action: str,
    refs_to_purge: tuple[DerivedArtifactRef, ...],
    tombstone: Tombstone | None,
    omissions: tuple[Omission, ...],
    receipts: tuple[TransformReceipt, ...],
    violations: tuple[str, ...],
) -> RetentionPlan:
    return RetentionPlan(ok, subject_id, action, refs_to_purge, tombstone, omissions, receipts, violations, ())


def _validate_plan_inputs(
    subject_id: object,
    policy: RetentionPolicy,
    content_sha256: object,
    violations: list[str],
) -> None:
    if not _safe_identifier(subject_id):
        _add(violations, "invalid-subject-id")
    elif _safe_identifier(policy.subject_id) and subject_id != policy.subject_id:
        _add(violations, "subject-policy-mismatch")
    if type(policy.action) is str and policy.action != "retain" and policy.retain_content_hash is True:
        if content_sha256 is None:
            _add(violations, "missing-content-sha256")
        elif not _is_sha256_ref(content_sha256):
            _add(violations, "invalid-content-sha256")


def _validate_policy_stores(stores: object, violations: list[str]) -> None:
    if type(stores) is not tuple:
        _add(violations, "invalid-derived-stores")
        return
    seen: set[str] = set()
    for index, store in enumerate(stores):
        if not _safe_identifier(store):
            _add(violations, "invalid-derived-store")
            continue
        normalized = _normalize(store)
        if store not in DERIVED_STORES:
            _add(violations, f"unknown-derived-store:{index}")
        if normalized in seen:
            _add(violations, f"duplicate-derived-store:{index}")
        seen.add(normalized)


def _validate_refs(refs: object) -> tuple[tuple[str, ...], tuple[DerivedArtifactRef, ...]]:
    violations: list[str] = []
    if type(refs) is not tuple:
        return ("invalid-derived-refs",), ()
    valid: list[DerivedArtifactRef] = []
    seen: set[tuple[str, str]] = set()
    for index, ref in enumerate(refs):
        if type(ref) is not DerivedArtifactRef:
            _add(violations, "invalid-derived-ref")
            continue
        if _validate_ref(ref, index, violations):
            key = (_normalize(ref.store), _normalize(ref.locator))
            if key in seen:
                _add(violations, f"duplicate-derived-ref:{index}")
                continue
            seen.add(key)
            valid.append(ref)
    return tuple(violations), tuple(valid)


def _validate_ref(ref: DerivedArtifactRef, index: int, violations: list[str]) -> bool:
    before = len(violations)
    if not _safe_identifier(ref.store):
        _add(violations, "invalid-derived-store")
    elif ref.store not in DERIVED_STORES:
        _add(violations, f"unknown-derived-ref-store:{index}")
    if not _safe_locator(ref.locator):
        _add(violations, "invalid-derived-locator")
    if ref.content_sha256 is not None and not _is_sha256_ref(ref.content_sha256):
        _add(violations, "invalid-derived-content-sha256")
    if type(ref.contains_raw) is not bool:
        _add(violations, "invalid-derived-contains-raw")
    return len(violations) == before


def _selected_refs(policy: RetentionPolicy, refs: tuple[DerivedArtifactRef, ...]) -> tuple[DerivedArtifactRef, ...]:
    if policy.action == "purge-all":
        return _sort_refs(refs)
    if policy.action != "purge-derived" or type(policy.derived_stores) is not tuple:
        return ()
    stores = frozenset(policy.derived_stores)
    return _sort_refs(tuple(ref for ref in refs if ref.store in stores))


def _validate_coverage(
    policy: object,
    refs: tuple[DerivedArtifactRef, ...],
    violations: list[str],
) -> None:
    if type(policy) is not RetentionPolicy or type(policy.action) is not str or policy.action != "purge-derived":
        return
    stores = policy.derived_stores if type(policy.derived_stores) is tuple else ()
    for index, ref in enumerate(refs):
        if ref.contains_raw is True and ref.store not in stores:
            _add(violations, f"uncovered-derived-store:{index}")


def _sort_refs(refs: tuple[DerivedArtifactRef, ...]) -> tuple[DerivedArtifactRef, ...]:
    return tuple(sorted(refs, key=lambda ref: (_normalize(ref.store), _normalize(ref.locator), ref.content_sha256 or "")))


def _can_select_refs(policy: object) -> bool:
    return type(policy) is RetentionPolicy and type(policy.action) is str and policy.action in RETENTION_ACTIONS


def _refs_for_policy(
    policy: RetentionPolicy,
    refs: tuple[DerivedArtifactRef, ...],
) -> tuple[DerivedArtifactRef, ...]:
    if policy.retain_content_hash is True:
        return refs
    return tuple(DerivedArtifactRef(ref.store, ref.locator, None, ref.contains_raw) for ref in refs)


def _is_sha256_ref(value: object) -> bool:
    return type(value) is str and is_sha256_ref(value)
