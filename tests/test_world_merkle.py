"""test_world_merkle.py — the projected world carries a Merkle root with per-part proofs.

Success criteria:
  - project_world has a merkle_root, and the existing concat root_hash is preserved.
  - each part (roster/spine/findings/cursor) has an audit path that verifies.
  - tampering a part's leaf fails verification; a bad part name raises.
"""
import pytest

from harness import world


def test_world_has_merkle_root_and_backcompat_root_hash():
    doc = world.project_world()
    assert doc["merkle_root"].startswith("sha256:")
    assert len(doc["root_hash"]) == 64                  # concat root still present


def test_inclusion_proof_verifies_for_every_part():
    doc = world.project_world()
    for part in ("roster", "spine", "findings", "cursor"):
        proof = world.world_inclusion_proof(doc, part)
        assert world.verify_world_part(doc, proof), part


def test_tampered_part_fails_verification():
    doc = world.project_world()
    proof = world.world_inclusion_proof(doc, "cursor")
    proof["leaf"] = proof["leaf"] + "TAMPERED"
    assert not world.verify_world_part(doc, proof)


def test_invalid_part_raises():
    with pytest.raises(ValueError):
        world.world_inclusion_proof(world.project_world(), "nonsense")
