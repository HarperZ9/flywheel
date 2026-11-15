from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from typing import Iterator

import pytest

from canon.atom import CanonAtom
from canon.import_review import (
    ImportFinding,
    ImportItem,
    ImportReview,
    review_import_items,
)
from canon.omission import Omission, validate_omission
from canon.retention import DerivedArtifactRef, RetentionPolicy, plan_retention
from canon.source_state import SourceStateItem, source_state_sha256
from canon.transform import TransformReceipt, validate_transform_receipt

HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_F = "sha256:" + "f" * 64


def _atom(
    atom_id: str,
    *,
    critical: bool = False,
    disclosure_profile: str = "project-only",
    trust_label: str = "trusted-local",
    status: str = "active",
) -> CanonAtom:
    return CanonAtom.from_dict({
        "atom_schema": "canon.atom/v1",
        "type": "active-goal" if critical else "episodic-fact",
        "id": atom_id,
        "layer": "workspace",
        "scope_key": "repo:canon",
        "precedence_rank": 50,
        "status": status,
        "classification": "normative" if critical else "descriptive",
        "critical": critical,
        "value": {"text": "do not drop me" if critical else "ordinary fact"},
        "source_refs": [{"ref": "record:workspace/source-1"}],
        "source_span_refs": [],
        "freshness": {"state": "current"},
        "trust": {"label": trust_label},
        "disclosure": {"profile": disclosure_profile},
        "hashes": {"value_sha256": HASH_A},
    })


def _source_items() -> tuple[SourceStateItem, ...]:
    return (SourceStateItem(path="source.json", sha256=HASH_A, size=1),)


def _item(
    source_id: str = "capsule-1",
    *,
    atom: CanonAtom | None = None,
    text: str = "safe text",
    signature_status: str = "none",
    key_id: str | None = None,
    local: bool = True,
    model_synthesized: bool = False,
    nonce: str = "nonce-1",
    expires_ord: int = 100,
) -> ImportItem:
    return ImportItem(
        source_id=source_id,
        atom=atom or _atom("fact-1"),
        text=text,
        signature_status=signature_status,
        key_id=key_id,
        local=local,
        model_synthesized=model_synthesized,
        replay_nonce=nonce,
        replay_expires_ord=expires_ord,
    )


def _review(
    items: object,
    *,
    expected: str | None = None,
    current: object | None = None,
    seen: object | None = None,
    current_ord: object = 1,
    pinned: object = frozenset(),
    profile: object = "project-only",
) -> ImportReview:
    current_items = _source_items() if current is None else current
    return review_import_items(
        items,  # type: ignore[arg-type]
        profile=profile,  # type: ignore[arg-type]
        pinned_key_ids=pinned,  # type: ignore[arg-type]
        expected_source_state=expected or source_state_sha256(current_items),
        current_source_items=current_items,  # type: ignore[arg-type]
        seen_replay_keys=set() if seen is None else seen,  # type: ignore[arg-type]
        current_ord=current_ord,  # type: ignore[arg-type]
    )


def test_combined_untrusted_secret_and_source_stale_findings_are_visible() -> None:
    item = _item(
        text="token sk-live-abcdefghijklmnopqrstuvwxyz012345",
        signature_status="valid",
        key_id="unknown",
        local=False,
    )

    review = _review(
        (item,),
        expected=HASH_F,
        pinned=frozenset({"pinned"}),
    )

    assert not review.ok
    assert [finding.code for finding in review.findings] == [
        "source_changed",
        "untrusted-import",
        "secret-quarantined",
    ]
    assert review.accepted_atoms == ()


def test_critical_disclosure_omission_blocks_import() -> None:
    item = _item(
        "capsule-2",
        atom=_atom("goal-1", critical=True, disclosure_profile="private-local-only"),
        nonce="nonce-2",
    )

    review = _review((item,), profile="team-safe")

    assert not review.ok
    assert "critical-disclosure-omission" in {finding.code for finding in review.findings}
    assert review.omissions[0].decision == "fail-build"


def test_clean_trusted_local_review_accepts_atom_and_marks_replay_seen() -> None:
    item = _item("capsule-3", atom=_atom("fact-2"), nonce="nonce-3")
    seen: set[str] = set()

    review = _review((item,), seen=seen)

    assert review.ok
    assert tuple(atom.to_dict()["id"] for atom in review.accepted_atoms) == ("fact-2",)
    assert len(seen) == 1


def test_invalid_source_state_is_critical_and_skips_item_checks() -> None:
    seen: set[str] = set()
    item = _item(text="token sk-live-abcdefghijklmnopqrstuvwxyz012345")

    review = _review((item,), current=[SourceStateItem("source.json", HASH_A, 1)], expected=HASH_A, seen=seen)

    assert not review.ok
    assert [finding.code for finding in review.findings] == ["invalid-source-state"]
    assert review.omissions == ()
    assert review.receipts == ()
    assert seen == set()


def test_failed_aggregate_review_does_not_mutate_seen_replay_keys() -> None:
    item = _item(signature_status="valid", key_id="unknown", local=False)
    seen: set[str] = set()

    review = _review((item,), seen=seen, pinned=frozenset({"pinned"}))

    assert not review.ok
    assert "untrusted-import" in {finding.code for finding in review.findings}
    assert seen == set()
    assert review.accepted_atoms == ()


@pytest.mark.parametrize(
    ("embedded_trust", "expected"),
    (
        ("signed-unknown-key", "untrusted-import"),
        ("imported-untrusted", "untrusted-import"),
        ("model-synthesized-unreviewed", "untrusted-import"),
        ("secret-quarantined", "secret-quarantined"),
        ("stale", "stale"),
        ("public-exportable", "untrusted-import"),
        ("private-local-only", "untrusted-import"),
    ),
)
def test_embedded_non_activating_atom_trust_prevents_end_to_end_acceptance(
    embedded_trust: str,
    expected: str,
) -> None:
    item = _item(
        f"capsule-embedded-{embedded_trust}",
        atom=_atom(f"fact-embedded-{embedded_trust}", trust_label=embedded_trust),
        nonce=f"nonce-embedded-{embedded_trust}",
    )

    review = _review((item,))

    assert not review.ok
    assert [finding.code for finding in review.findings] == [expected]
    assert review.accepted_atoms == ()


@pytest.mark.parametrize("embedded_trust", ("trusted-local", "signed-pinned", "unsigned-local"))
def test_embedded_activating_atom_trust_accepts_end_to_end(embedded_trust: str) -> None:
    item = _item(
        f"capsule-activate-{embedded_trust}",
        atom=_atom(f"fact-activate-{embedded_trust}", trust_label=embedded_trust),
        nonce=f"nonce-activate-{embedded_trust}",
    )

    review = _review((item,))

    assert review.ok
    assert review.findings == ()
    assert tuple(atom.id for atom in review.accepted_atoms) == (f"fact-activate-{embedded_trust}",)


def test_malformed_import_item_fields_fail_first_without_leak_or_downstream_work() -> None:
    class BadStr(str):
        pass

    canary = "sk-live-abcdefghijklmnopqrstuvwxyz012345"
    item = ImportItem(
        source_id=BadStr(canary),  # type: ignore[arg-type]
        atom=_atom("fact-malformed", trust_label="stale"),
        text=BadStr(canary),  # type: ignore[arg-type]
        signature_status=BadStr("none"),  # type: ignore[arg-type]
        key_id=BadStr("key"),
        local=1,  # type: ignore[arg-type]
        model_synthesized=0,  # type: ignore[arg-type]
        replay_nonce=BadStr("nonce"),  # type: ignore[arg-type]
        replay_expires_ord=True,  # type: ignore[arg-type]
    )

    review = _review((item,))

    assert [finding.code for finding in review.findings] == [
        "invalid-source-id",
        "invalid-text",
        "invalid-signature-status",
        "invalid-key-id",
        "invalid-local-flag",
        "invalid-model-synthesized-flag",
        "invalid-replay-nonce",
        "invalid-replay-expires-ord",
    ]
    assert all(finding.subject_id == "item:0" for finding in review.findings)
    assert canary not in repr(review)
    assert review.accepted_atoms == ()
    assert review.omissions == ()
    assert review.receipts == ()


def test_mutated_atom_id_is_revalidated_before_duplicate_checks() -> None:
    atom = _atom("fact-mutated-id")
    object.__setattr__(atom, "id", ["unhashable"])

    review = _review((_item("capsule-mutated-atom", atom=atom),))

    assert review.findings == (
        ImportFinding("invalid-atom", "critical", "capsule-mutated-atom", "item atom failed validation"),
    )
    assert review.accepted_atoms == ()


def test_same_import_snapshot_replay_is_rejected_deterministically() -> None:
    item = _item("capsule-a", atom=_atom("fact-a"), text="same text", nonce="same")
    seen: set[str] = set()

    first = _review((item,), seen=seen)
    second = _review((item,), seen=seen)

    assert first.ok
    assert not second.ok
    assert [(f.subject_id, f.code) for f in second.findings] == [
        ("capsule-a", "replay"),
    ]
    assert second.accepted_atoms == ()


def test_replay_key_binds_sanitized_import_content_not_only_source_id() -> None:
    seen: set[str] = set()
    first = _item("capsule-content", atom=_atom("fact-content"), text="first text", nonce="same")
    second = _item("capsule-content", atom=_atom("fact-content"), text="second text", nonce="same")

    first_review = _review((first,), seen=seen)
    second_review = _review((second,), seen=seen)

    assert first_review.ok
    assert second_review.ok
    assert len(seen) == 2


def test_import_review_aggregates_policy_secret_and_replay_artifacts() -> None:
    item = _item(
        "capsule-private",
        atom=_atom("fact-private", disclosure_profile="private-local-only"),
        text="email jane@example.com",
        nonce="nonce-private",
    )

    review = _review((item,), profile="team-safe")

    assert not review.ok
    assert [finding.code for finding in review.findings] == [
        "private-local-only",
        "secret-quarantined",
    ]
    assert all(isinstance(omission, Omission) for omission in review.omissions)
    assert all(validate_omission(omission) == [] for omission in review.omissions)
    assert all(isinstance(receipt, TransformReceipt) for receipt in review.receipts)
    assert all(validate_transform_receipt(receipt) == [] for receipt in review.receipts)
    assert any(omission.does_not_prove for omission in review.omissions)
    assert any(receipt.does_not_prove for receipt in review.receipts)


def test_retention_composes_with_import_review_foundation_artifacts() -> None:
    item = _item("capsule-retain", atom=_atom("fact-retain"), nonce="nonce-retain")
    review = _review((item,))
    policy = RetentionPolicy("fact-retain", "purge-all", False, ())
    ref = DerivedArtifactRef("files", "workspace/fact-retain.json", HASH_A, True)

    plan = plan_retention(
        "fact-retain",
        policy=policy,
        derived_refs=(ref,),
        content_sha256=HASH_B,
    )

    assert review.ok
    assert plan.ok
    assert review.omissions + plan.omissions == plan.omissions
    assert review.receipts + plan.receipts == plan.receipts
    assert plan.deleted_paths == ()


def test_critical_secret_and_untrusted_policy_are_both_reported_without_canary_leak() -> None:
    canary = "sk-live-abcdefghijklmnopqrstuvwxyz012345"
    item = _item(
        "capsule-critical",
        atom=_atom("goal-secret", critical=True),
        text=f"token {canary}",
        signature_status="valid",
        key_id="unknown",
        local=False,
    )

    review = _review((item,), pinned=frozenset({"pinned"}))
    serialized = repr(review) + repr(asdict(review))

    assert not review.ok
    assert {"untrusted-import", "critical-secret"} <= {finding.code for finding in review.findings}
    assert canary not in serialized


def test_exact_container_and_item_types_are_enforced_without_hostile_iteration() -> None:
    class HostileTuple(tuple[ImportItem, ...]):
        def __iter__(self) -> Iterator[ImportItem]:
            raise AssertionError("hostile tuple iterated")

    class ImportItemSubclass(ImportItem):
        pass

    bad_container = _review(HostileTuple((_item(),)))
    bad_item = _review((ImportItemSubclass(**asdict(_item())),))

    assert bad_container.findings == (
        ImportFinding("invalid-items", "critical", "import-review", "items must be an exact tuple"),
    )
    assert bad_item.findings == (
        ImportFinding("invalid-import-item", "critical", "item:0", "items[0] must be an exact ImportItem"),
    )


def test_atom_subclasses_are_rejected_before_policy_review() -> None:
    class HostileAtom(CanonAtom):
        def to_dict(self) -> dict:
            raise AssertionError("hostile atom serialized")

    hostile = HostileAtom(
        "episodic-fact",
        "fact-hostile",
        "workspace",
        "repo:canon",
        50,
        "active",
        "descriptive",
        False,
        {"text": "hostile"},
        freshness={"state": "current"},
        trust={"label": "trusted-local"},
        disclosure={"profile": "project-only"},
        hashes={"value_sha256": HASH_A},
    )

    review = _review((_item(atom=hostile),))

    assert review.findings == (
        ImportFinding("invalid-atom", "critical", "capsule-1", "item atom must be an exact CanonAtom"),
    )


def test_input_mutation_after_review_construction_does_not_affect_result() -> None:
    item = _item("capsule-snapshot", atom=_atom("fact-snapshot"), nonce="nonce-snapshot")
    review = _review((item,))
    object.__setattr__(item, "atom", _atom("fact-mutated"))

    assert review.ok
    assert tuple(atom.id for atom in review.accepted_atoms) == ("fact-snapshot",)


def test_duplicate_atom_ids_across_items_fail_closed_in_input_order() -> None:
    items = (
        _item("capsule-first", atom=_atom("shared"), nonce="nonce-a"),
        _item("capsule-second", atom=_atom("shared"), nonce="nonce-b"),
    )

    review = _review(items)

    assert not review.ok
    assert [(finding.subject_id, finding.code) for finding in review.findings] == [
        ("capsule-second", "duplicate-atom-id"),
    ]
    assert review.accepted_atoms == ()


def test_result_types_are_frozen_and_snapshot_lists_to_tuples() -> None:
    findings = [ImportFinding("note", "info", "source", "message")]
    review = ImportReview(True, findings, [_atom("fact-list")], [], [])
    findings.append(ImportFinding("mutated", "info", "source", "message"))

    assert isinstance(review.findings, tuple)
    assert isinstance(review.accepted_atoms, tuple)
    assert isinstance(review.omissions, tuple)
    assert isinstance(review.receipts, tuple)
    assert [finding.code for finding in review.findings] == ["note"]
    with pytest.raises(FrozenInstanceError):
        review.ok = False
