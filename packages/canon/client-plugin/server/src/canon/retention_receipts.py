from __future__ import annotations

from .atom import CanonAtom
from .canonical_json import canonical_sha256
from .omission import Omission
from .transform import TransformReceipt

RETENTION_LIMITATION = (
    "This retention plan is declarative only; it does not prove bytes were "
    "deleted from any backend, archive, backup, cache, or exported artifact."
)


def retention_artifacts(
    subject_id: str,
    action: str,
    refs: tuple[object, ...],
    tombstone: object,
    retain_content_hash: bool,
) -> tuple[Omission, TransformReceipt]:
    omission = _omission(subject_id, refs)
    receipt = _receipt(subject_id, action, refs, tombstone, omission, retain_content_hash)
    return omission, receipt


def _omission(subject_id: str, refs: tuple[object, ...]) -> Omission:
    return Omission(
        reason="policy",
        count=1,
        affected_ids=(subject_id,),
        affected_source_refs=_source_refs(subject_id, refs),
        critical=False,
        decision="reference-only",
        does_not_prove=(RETENTION_LIMITATION,),
    )


def _receipt(
    subject_id: str,
    action: str,
    refs: tuple[object, ...],
    tombstone: object,
    omission: Omission,
    retain_content_hash: bool,
) -> TransformReceipt:
    keep_hashes = retain_content_hash is True
    output_hash = canonical_sha256(_receipt_payload(subject_id, action, refs, tombstone, omission, keep_hashes))
    input_hash = tombstone.content_sha256 if keep_hashes else _unretained_input_hash(subject_id, action)
    return TransformReceipt(
        transform="redaction",
        method_id="retention-plan-v1",
        input_refs=_source_refs(subject_id, refs),
        input_span_hash=input_hash,
        output_ref="retention-plan:" + output_hash.removeprefix("sha256:"),
        output_hash=output_hash,
        lossy=True,
        retained_critical_atom_ids=(),
        omissions=(omission,),
        verifier="deterministic",
        does_not_prove=(RETENTION_LIMITATION,),
    )


def _receipt_payload(
    subject_id: str,
    action: str,
    refs: tuple[object, ...],
    tombstone: object,
    omission: Omission,
    retain_content_hash: bool,
) -> dict[str, object]:
    return {
        "action": action,
        "atom_schema": CanonAtom.atom_schema,
        "deleted_paths": [],
        "refs_to_purge": [_ref_dict(ref, retain_content_hash) for ref in refs],
        "subject_id": subject_id,
        "tombstone": _tombstone_dict(tombstone),
        "omissions": [omission.to_dict()],
    }


def _ref_dict(ref: object, retain_content_hash: bool) -> dict[str, object]:
    return {
        "store": ref.store,
        "locator": ref.locator,
        "content_sha256": ref.content_sha256 if retain_content_hash else None,
        "contains_raw": ref.contains_raw,
    }


def _tombstone_dict(tombstone: object) -> dict[str, object]:
    return {
        "subject_id": tombstone.subject_id,
        "reason_code": tombstone.reason_code,
        "purged_at_ord": tombstone.purged_at_ord,
        "content_sha256": tombstone.content_sha256,
    }


def _source_refs(subject_id: str, refs: tuple[object, ...]) -> tuple[str, ...]:
    return ("atom:" + subject_id,) + tuple(f"{ref.store}:{ref.locator}" for ref in refs)


def _unretained_input_hash(subject_id: str, action: str) -> str:
    return canonical_sha256({
        "action": action,
        "content_sha256_retained": False,
        "subject_ref": "atom:" + subject_id,
    })
