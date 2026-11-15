from __future__ import annotations

from dataclasses import dataclass

from .atom import CanonAtom
from .import_policy import ImportDecision, ImportSubject, review_import_subject
from .import_review_safety import (
    error_code,
    import_content_sha256,
    quarantine_code,
    safe_subject_id,
    severity,
    snapshot_atom,
    validate_import_item_fields,
)
from .omission import Omission
from .replay import ReplayClaim, ReplayError, check_replay_claim
from .secret_quarantine import SecretQuarantineError, SecretQuarantine, quarantine_text
from .source_state import SourceStateError, SourceStateItem, assert_source_state
from .transform import TransformReceipt


@dataclass(frozen=True, slots=True)
class ImportItem:
    source_id: str
    atom: CanonAtom
    text: str
    signature_status: str
    key_id: str | None
    local: bool
    model_synthesized: bool
    replay_nonce: str
    replay_expires_ord: int


@dataclass(frozen=True, slots=True)
class ImportFinding:
    code: str
    severity: str
    subject_id: str
    message: str


@dataclass(frozen=True, slots=True)
class ImportReview:
    ok: bool
    findings: tuple[ImportFinding, ...]
    accepted_atoms: tuple[CanonAtom, ...]
    omissions: tuple[Omission, ...]
    receipts: tuple[TransformReceipt, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "findings", _tuple_or_original(self.findings))
        object.__setattr__(self, "accepted_atoms", _tuple_or_original(self.accepted_atoms))
        object.__setattr__(self, "omissions", _tuple_or_original(self.omissions))
        object.__setattr__(self, "receipts", _tuple_or_original(self.receipts))


def review_import_items(
    items: tuple[ImportItem, ...],
    *,
    profile: str,
    pinned_key_ids: frozenset[str],
    expected_source_state: str,
    current_source_items: tuple[SourceStateItem, ...],
    seen_replay_keys: set[str],
    current_ord: int,
) -> ImportReview:
    preflight = _preflight(items, pinned_key_ids, seen_replay_keys)
    if preflight:
        return ImportReview(False, preflight, (), (), ())
    source_findings = list(_source_state_findings(expected_source_state, current_source_items))
    if _has_unsafe_source_state(source_findings):
        return ImportReview(False, tuple(source_findings), (), (), ())
    snapshots, item_findings = _snapshot_items(items)
    findings = [*source_findings, *item_findings, *_duplicate_atom_findings(snapshots)]
    omissions: list[Omission] = []
    receipts: list[TransformReceipt] = []
    staged_seen = set(seen_replay_keys)
    for item in snapshots:
        item_findings, item_omissions, item_receipts = _review_item(
            item, profile, pinned_key_ids, expected_source_state, staged_seen, current_ord
        )
        findings.extend(item_findings)
        omissions.extend(item_omissions)
        receipts.extend(item_receipts)
    ok = not _has_blocking_findings(findings)
    if ok:
        seen_replay_keys.update(staged_seen - seen_replay_keys)
    accepted = tuple(item.atom for item in snapshots) if ok else ()
    return ImportReview(ok, tuple(findings), accepted, tuple(omissions), tuple(receipts))


def _preflight(
    items: object,
    pinned_key_ids: object,
    seen_replay_keys: object,
) -> tuple[ImportFinding, ...]:
    if type(items) is not tuple:
        return (_finding("invalid-items", "import-review", "items must be an exact tuple"),)
    if type(pinned_key_ids) is not frozenset or not all(type(item) is str and item for item in pinned_key_ids):
        return (_finding("invalid-pinned-key-ids", "import-review", "pinned_key_ids must be exact frozenset[str]"),)
    if type(seen_replay_keys) is not set:
        return (_finding("invalid-seen", "import-review", "seen_replay_keys must be an exact set"),)
    return ()


def _source_state_findings(
    expected_source_state: object,
    current_source_items: object,
) -> tuple[ImportFinding, ...]:
    try:
        assert_source_state(expected_source_state, current_source_items)  # type: ignore[arg-type]
    except SourceStateError as exc:
        return (_finding(exc.code, "source-state", f"{exc.code} blocked import review"),)
    return ()


def _has_unsafe_source_state(findings: list[ImportFinding]) -> bool:
    return any(finding.code != "source_changed" for finding in findings)


def _snapshot_items(items: tuple[ImportItem, ...]) -> tuple[tuple[ImportItem, ...], tuple[ImportFinding, ...]]:
    snapshots: list[ImportItem] = []
    findings: list[ImportFinding] = []
    for index, item in enumerate(items):
        if type(item) is not ImportItem:
            findings.append(_finding("invalid-import-item", f"item:{index}", f"items[{index}] must be an exact ImportItem"))
            continue
        item_issues = validate_import_item_fields(item, index)
        if item_issues:
            findings.extend(_finding(issue.code, issue.subject_id, issue.message) for issue in item_issues)
            continue
        subject_id = safe_subject_id(item.source_id, fallback=f"item:{index}")
        atom, message = snapshot_atom(item.atom)
        if atom is None:
            findings.append(_finding("invalid-atom", subject_id, message))
            continue
        snapshots.append(ImportItem(
            item.source_id, atom, item.text, item.signature_status, item.key_id,
            item.local, item.model_synthesized, item.replay_nonce, item.replay_expires_ord,
        ))
    return tuple(snapshots), tuple(findings)


def _duplicate_atom_findings(items: tuple[ImportItem, ...]) -> tuple[ImportFinding, ...]:
    seen: set[str] = set()
    findings: list[ImportFinding] = []
    for item in items:
        atom_id = item.atom.id
        if atom_id in seen:
            findings.append(_finding("duplicate-atom-id", safe_subject_id(item.source_id), "duplicate atom id in import batch"))
        seen.add(atom_id)
    return tuple(findings)


def _review_item(
    item: ImportItem,
    profile: str,
    pinned_key_ids: frozenset[str],
    expected_source_state: str,
    seen: set[str],
    current_ord: int,
) -> tuple[tuple[ImportFinding, ...], tuple[Omission, ...], tuple[TransformReceipt, ...]]:
    decision = _policy_decision(item, profile, pinned_key_ids, expected_source_state)
    findings = list(_decision_findings(item, decision))
    omissions = list(decision.omissions)
    receipts = list(decision.receipts)
    secret_findings, secret_omissions, secret_receipts = _secret_findings(item)
    findings.extend(secret_findings)
    omissions.extend(secret_omissions)
    receipts.extend(secret_receipts)
    findings.extend(_replay_findings(item, expected_source_state, seen, current_ord))
    return tuple(findings), tuple(omissions), tuple(receipts)


def _policy_decision(
    item: ImportItem,
    profile: str,
    pinned_key_ids: frozenset[str],
    expected_source_state: str,
) -> ImportDecision:
    subject = ImportSubject(
        item.source_id, (item.atom,), item.signature_status, item.key_id,
        item.local, expected_source_state, item.model_synthesized,
    )
    return review_import_subject(subject, profile=profile, pinned_key_ids=pinned_key_ids)


def _decision_findings(item: ImportItem, decision: ImportDecision) -> tuple[ImportFinding, ...]:
    subject_id = safe_subject_id(item.source_id)
    return tuple(_finding(code, subject_id, f"{code} blocked import activation") for code in decision.reason_codes)


def _secret_findings(item: ImportItem) -> tuple[tuple[ImportFinding, ...], tuple[Omission, ...], tuple[TransformReceipt, ...]]:
    subject_id = safe_subject_id(item.source_id)
    try:
        quarantine = quarantine_text(item.text, source_id=item.source_id, critical=item.atom.critical)
    except SecretQuarantineError as exc:
        code = error_code(exc)
        return ((_finding(code, subject_id, f"{code} blocked import activation"),), (), ())
    return _quarantine_artifacts(quarantine, subject_id)


def _quarantine_artifacts(
    quarantine: SecretQuarantine,
    subject_id: str,
) -> tuple[tuple[ImportFinding, ...], tuple[Omission, ...], tuple[TransformReceipt, ...]]:
    findings = tuple(_finding(quarantine_code(code), subject_id, "secret quarantine blocked import activation") for code in quarantine.reason_codes)
    return findings, tuple(quarantine.omissions), tuple(quarantine.receipts)


def _replay_findings(
    item: ImportItem,
    expected_source_state: str,
    seen: set[str],
    current_ord: int,
) -> tuple[ImportFinding, ...]:
    subject_id = safe_subject_id(item.source_id)
    try:
        claim = ReplayClaim(
            principal=item.source_id,
            source_state_sha256=expected_source_state,
            capsule_sha256=import_content_sha256(item),
            nonce=item.replay_nonce,
            expires_ord=item.replay_expires_ord,
        )
        check_replay_claim(claim, seen=seen, current_ord=current_ord)
    except ReplayError as exc:
        return (_finding(exc.code, subject_id, f"{exc.code} blocked import activation"),)
    except (TypeError, ValueError, UnicodeEncodeError):
        return (_finding("invalid-replay-claim", subject_id, "invalid-replay-claim blocked import activation"),)
    return ()


def _finding(code: str, subject_id: str, message: str) -> ImportFinding:
    return ImportFinding(code, severity(code), subject_id, message)


def _has_blocking_findings(findings: list[ImportFinding]) -> bool:
    return any(finding.severity in ("critical", "warning") for finding in findings)


def _tuple_or_original(value: object) -> object:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return value
