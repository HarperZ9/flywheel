from __future__ import annotations
from dataclasses import FrozenInstanceError
import pytest
from canon.atom import CanonAtom
from canon.import_policy import (
    DISCLOSURE_PROFILES,
    TRUST_LABELS,
    ImportDecision,
    ImportSubject,
    classify_trust,
    disclosure_omissions,
    review_import_subject,
    validate_atom_activation,
)
from canon.omission import Omission, validate_omission
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64


def _atom(
    atom_id: str,
    *,
    atom_type: str = "episodic-fact",
    critical: bool = False,
    classification: str = "descriptive",
    trust_label: str = "trusted-local",
    disclosure_profile: str = "project-only",
    source_refs: tuple[dict, ...] = ({"ref": "record:workspace/source-1"},),
    content_hash: str = HASH_A,
) -> CanonAtom:
    return CanonAtom.from_dict({
        "atom_schema": "canon.atom/v1",
        "type": atom_type,
        "id": atom_id,
        "layer": "workspace",
        "scope_key": "repo:canon",
        "precedence_rank": 50,
        "status": "active",
        "classification": classification,
        "critical": critical,
        "value": {"text": f"value for {atom_id}"},
        "source_refs": list(source_refs),
        "source_span_refs": [],
        "freshness": {"state": "current"},
        "trust": {"label": trust_label},
        "disclosure": {"profile": disclosure_profile},
        "hashes": {"value_sha256": content_hash},
    })


def _subject(
    source_id: str,
    atoms: tuple[CanonAtom, ...],
    *,
    signature_status: str = "none",
    key_id: str | None = None,
    local: bool = True,
    source_state_sha256: str = HASH_B,
    model_synthesized: bool = False,
) -> ImportSubject:
    return ImportSubject(source_id, atoms, signature_status, key_id, local, source_state_sha256, model_synthesized)


def test_label_vocabularies_are_exact_tuple_contracts() -> None:
    assert TRUST_LABELS == (
        "trusted-local",
        "signed-pinned",
        "signed-unknown-key",
        "unsigned-local",
        "imported-untrusted",
        "model-synthesized-unreviewed",
        "secret-quarantined",
        "stale",
        "public-exportable",
        "private-local-only",
    )
    assert DISCLOSURE_PROFILES == (
        "full-local",
        "project-only",
        "no-secrets",
        "team-safe",
        "public-safe",
        "need-to-know",
    )


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    (
        ({"signature_status": "valid", "key_id": "pinned", "pinned_key_ids": frozenset({"pinned"}), "local": False}, "signed-pinned"),
        ({"signature_status": "valid", "key_id": "unknown", "pinned_key_ids": frozenset({"pinned"}), "local": False}, "signed-unknown-key"),
        ({"signature_status": "none", "key_id": None, "pinned_key_ids": frozenset(), "local": True}, "unsigned-local"),
        ({"signature_status": "none", "key_id": None, "pinned_key_ids": frozenset(), "local": False}, "imported-untrusted"),
        ({"signature_status": "valid", "key_id": "pinned", "pinned_key_ids": frozenset({"pinned"}), "local": False, "model_synthesized": True}, "model-synthesized-unreviewed"),
        ({"signature_status": "bogus", "key_id": None, "pinned_key_ids": frozenset(), "local": True}, "imported-untrusted"),
    ),
)
def test_classify_trust_is_deterministic_and_fails_closed(kwargs: dict, expected: str) -> None:
    assert classify_trust(**kwargs) == expected
    assert classify_trust(**kwargs) == expected


def test_signed_unknown_key_is_integrity_only_and_inactive() -> None:
    atom = _atom("permission-1", atom_type="permission", critical=True, classification="normative")
    subject = _subject("capsule-a", (atom,), signature_status="valid", key_id="unknown-key", local=False)

    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset({"pinned-key"}))
    assert not decision.ok
    assert decision.trust_label == "signed-unknown-key"
    assert "untrusted-import" in decision.reason_codes
    assert decision.accepted_atom_ids == ()
    assert isinstance(decision.omissions, tuple)
    assert isinstance(decision.receipts, tuple)


def test_unsigned_remote_and_invalid_source_hash_fail_closed() -> None:
    subject = _subject("capsule-remote", (_atom("fact-remote"),), local=False, source_state_sha256="not-a-sha256-ref")

    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())
    assert not decision.ok
    assert {"unsigned-remote", "invalid-source-state-sha256", "untrusted-import"} <= set(decision.reason_codes)
    assert decision.accepted_atom_ids == ()


def test_model_synthesized_unreviewed_normative_atom_cannot_activate() -> None:
    atom = _atom("prohibition-1", atom_type="prohibition", critical=True, classification="normative")

    reasons = validate_atom_activation(atom, trust_label="model-synthesized-unreviewed")
    assert "unreviewed-model-normative" in reasons


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
def test_embedded_non_activating_trust_labels_prevent_activation(
    embedded_trust: str,
    expected: str,
) -> None:
    atom = _atom("fact-embedded-trust", trust_label=embedded_trust)
    subject = _subject("capsule-embedded-trust", (atom,))

    reasons = validate_atom_activation(atom, trust_label="trusted-local")
    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())

    assert expected in reasons
    assert not decision.ok
    assert expected in decision.reason_codes
    assert decision.accepted_atom_ids == ()


@pytest.mark.parametrize("embedded_trust", ("trusted-local", "signed-pinned", "unsigned-local"))
def test_embedded_activating_trust_labels_can_activate(embedded_trust: str) -> None:
    atom = _atom(f"fact-embedded-{embedded_trust}", trust_label=embedded_trust)
    subject = _subject(f"capsule-embedded-{embedded_trust}", (atom,))

    reasons = validate_atom_activation(atom, trust_label="trusted-local")
    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())

    assert reasons == ()
    assert decision.ok
    assert decision.reason_codes == ()
    assert decision.accepted_atom_ids == (f"fact-embedded-{embedded_trust}",)


def test_embedded_model_synthesized_normative_atom_cannot_activate() -> None:
    atom = _atom(
        "embedded-model-permission",
        atom_type="permission",
        critical=True,
        classification="normative",
        trust_label="model-synthesized-unreviewed",
    )
    subject = _subject("capsule-embedded-model", (atom,))

    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())

    assert not decision.ok
    assert "untrusted-import" in decision.reason_codes
    assert "unreviewed-model-normative" in decision.reason_codes
    assert decision.accepted_atom_ids == ()


@pytest.mark.parametrize(
    "atom_type",
    ("active-goal", "permission", "prohibition", "constraint", "frontier-state", "conflict", "unknown"),
)
def test_model_synthesized_unreviewed_critical_readiness_atoms_cannot_activate(atom_type: str) -> None:
    atom = _atom(f"{atom_type}-critical", atom_type=atom_type, critical=True, classification="descriptive")

    reasons = validate_atom_activation(atom, trust_label="model-synthesized-unreviewed")
    assert "unreviewed-model-normative" in reasons


def test_private_local_only_emits_valid_foundation_policy_omission() -> None:
    atom = _atom(
        "fact-1",
        disclosure_profile="private-local-only",
        source_refs=({"ref": "record:workspace/fact-1"}, {"ref": "capsule:line-9"}),
    )

    omissions = disclosure_omissions((atom,), profile="team-safe")
    assert len(omissions) == 1
    assert isinstance(omissions[0], Omission)
    assert validate_omission(omissions[0]) == []
    assert omissions[0].to_dict() == {
        "schema": "canon.omission/v1",
        "reason": "policy",
        "count": 1,
        "affected_ids": ["fact-1"],
        "affected_source_refs": ["record:workspace/fact-1", "capsule:line-9"],
        "critical": False,
        "decision": "omitted",
        "does_not_prove": [
            "This private-local-only omission does not prove the omitted content is safe to disclose elsewhere."
        ],
    }


def test_critical_private_local_only_blocks_cloud_profile() -> None:
    atom = _atom(
        "goal-1",
        atom_type="active-goal",
        critical=True,
        classification="normative",
        disclosure_profile="private-local-only",
    )
    subject = _subject("capsule-b", (atom,))

    decision = review_import_subject(subject, profile="team-safe", pinned_key_ids=frozenset())
    assert not decision.ok
    assert {"private-local-only", "critical-disclosure-omission"} <= set(decision.reason_codes)
    assert decision.omissions[0].decision == "fail-build"
    assert validate_omission(decision.omissions[0]) == []
    assert decision.accepted_atom_ids == ()


def test_noncritical_private_local_only_prevents_whole_subject_activation() -> None:
    private_atom = _atom("fact-private", disclosure_profile="private-local-only")
    public_atom = _atom("fact-public")
    subject = _subject("capsule-c", (private_atom, public_atom))

    decision = review_import_subject(subject, profile="team-safe", pinned_key_ids=frozenset())
    assert not decision.ok
    assert decision.omissions[0].decision == "omitted"
    assert decision.accepted_atom_ids == ()


def test_clean_signed_pinned_subject_accepts_ids_in_input_order() -> None:
    subject = _subject("capsule-d", (_atom("fact-b"), _atom("fact-a")), signature_status="valid", key_id="pinned", local=False)

    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset({"pinned"}))
    assert decision.ok
    assert decision.accepted_atom_ids == ("fact-b", "fact-a")
    assert decision.reason_codes == ()
    assert decision.omissions == ()
    assert decision.receipts == ()


def test_invalid_profile_trust_and_key_inputs_fail_closed_without_exceptions() -> None:
    atom = _atom("fact-bad-trust", trust_label="bogus", disclosure_profile="bogus")
    subject = _subject("capsule-e", (atom,), signature_status="valid", local="yes", model_synthesized="no")

    decision = review_import_subject(subject, profile="unknown-profile", pinned_key_ids={"pinned"})
    assert not decision.ok
    assert {
        "invalid-profile",
        "invalid-pinned-key-ids",
        "invalid-key-id",
        "invalid-local-flag",
        "invalid-model-synthesized-flag",
        "invalid-atom-trust-label",
        "invalid-atom-disclosure-profile",
    } <= set(decision.reason_codes)
    assert decision.accepted_atom_ids == ()


def test_atom_subclass_cannot_launder_trust_through_to_dict_dispatch() -> None:
    dispatched = False
    trusted_payload = _atom("fact-laundered-view").to_dict()

    class LaunderingAtom(CanonAtom):
        def to_dict(self) -> dict:
            nonlocal dispatched
            dispatched = True
            return trusted_payload

    hostile = LaunderingAtom(
        "episodic-fact",
        "fact-hostile-object",
        "workspace",
        "repo:canon",
        50,
        "active",
        "descriptive",
        False,
        {"text": "object trust is untrusted"},
        source_refs=({"ref": "record:workspace/source-1"},),
        freshness={"state": "current"},
        trust={"label": "imported-untrusted"},
        disclosure={"profile": "project-only"},
        hashes={"value_sha256": HASH_A},
    )
    subject = _subject("capsule-hostile-atom", (hostile,))

    assert validate_atom_activation(hostile, trust_label="trusted-local") == ("invalid-atom",)
    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())

    assert not decision.ok
    assert decision.reason_codes == ("invalid-atom",)
    assert decision.accepted_atom_ids == ()
    assert not dispatched


def test_subject_and_atom_containers_must_be_exact_public_types() -> None:
    class ImportSubjectSubclass(ImportSubject):
        pass

    class HostileTuple(tuple):
        def __iter__(self):  # type: ignore[no-untyped-def]
            raise AssertionError("hostile atom container iterated")

    subclass = ImportSubjectSubclass("capsule-subclass", (_atom("fact-subclass"),), "none", None, True, HASH_B)
    hostile_container = _subject("capsule-hostile-container", (_atom("fact-container"),))
    object.__setattr__(hostile_container, "atoms", HostileTuple((_atom("fact-hidden"),)))

    subclass_decision = review_import_subject(subclass, profile="project-only", pinned_key_ids=frozenset())
    container_decision = review_import_subject(hostile_container, profile="project-only", pinned_key_ids=frozenset())

    assert subclass_decision.reason_codes == ("invalid-subject",)
    assert subclass_decision.accepted_atom_ids == ()
    assert container_decision.reason_codes == ("invalid-atoms",)
    assert container_decision.accepted_atom_ids == ()
    assert disclosure_omissions(HostileTuple((_atom("fact-private", disclosure_profile="private-local-only"),)), profile="team-safe") == ()


def test_exact_public_subject_tuple_and_atom_remain_accepted() -> None:
    subject = _subject("capsule-exact", (_atom("fact-exact"),))

    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())

    assert decision.ok
    assert decision.reason_codes == ()
    assert decision.accepted_atom_ids == ("fact-exact",)


def test_malformed_and_duplicate_atoms_fail_closed_without_exceptions() -> None:
    malformed = CanonAtom(
        "permission",
        "dup",
        "workspace",
        "repo:canon",
        50,
        "active",
        "normative",
        True,
        {"text": "bad source refs"},
        source_refs=("not-a-ref-dict",),
        freshness={"state": "current"},
        trust={"label": "trusted-local"},
        disclosure={"profile": "project-only"},
        hashes={"value_sha256": HASH_A},
    )
    duplicate = _atom("dup", atom_type="permission", critical=True, classification="normative")
    subject = _subject("capsule-f", (malformed, duplicate))

    decision = review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())
    assert not decision.ok
    assert {"invalid-atom", "duplicate-atom-id"} <= set(decision.reason_codes)
    assert decision.accepted_atom_ids == ()


def test_review_does_not_mutate_atom_inputs() -> None:
    atom = _atom("fact-stable")
    before = atom.to_dict()
    subject = _subject("capsule-g", (atom,))

    review_import_subject(subject, profile="project-only", pinned_key_ids=frozenset())
    assert atom.to_dict() == before


def test_decision_and_subject_are_frozen_and_store_tuples() -> None:
    atoms = [_atom("fact-list")]
    subject = ImportSubject("capsule-h", atoms, "none", None, True, HASH_B)
    atoms.append(_atom("fact-after"))
    decision = ImportDecision(True, "unsigned-local", "project-only", ["fact-list"], [], [], ["note"])
    assert subject.atoms == (_atom("fact-list"),)
    assert decision.accepted_atom_ids == ("fact-list",)
    assert decision.omissions == ()
    assert decision.receipts == ()
    assert decision.reason_codes == ("note",)
    with pytest.raises(FrozenInstanceError):
        decision.ok = False
