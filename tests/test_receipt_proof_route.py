"""receipts-proof/v2 -- one strict wire object both languages verify.

The desktop must recompute inclusion before any MATCH label, so the
route serves exactly {schema, leaf, index, tree_size, merkle_root,
audit_path} with steps of exactly {hash, side}. The leaf vectors below
are the shared Python/Dart fixtures: the same leaves verify under
transparency_log.verify_inclusion here and under the pure-Dart walker
in desktop/test/receipt_proof_test.dart.
"""
import pytest

from harness.receipt_proof import (
    SCHEMA,
    LeafNotFound,
    ReceiptProofError,
    build_receipt_proof,
    route_payload,
)
from harness.transparency_log import verify_inclusion

# Five leaves: odd count exercises promotion on every level.
LEAVES = [format(i, "064x") for i in range(1, 6)]
ROOT = "c48c0df7d9b37592c69ba5ca2afc8ada511550e607e6dfe7fdef6b85d89f5269"
PROOF_IDX_2 = [
    {"hash": "82f02cf2ac0074619e6d747c35e08b29431a16943ddf81cfd9065c004ee6364a",
     "side": "right"},
    {"hash": "0971c8a1ce81287ccbc95aa4f171a5f807fb13ea2118f56b99769459a64906ad",
     "side": "left"},
    {"hash": "086fb60bd968fe68ecec6a8d826ea5aa7d3d8020e644d7c5d0e07ded456ca3e8",
     "side": "right"},
]


def test_v2_object_has_exact_keys_and_strict_steps():
    doc = build_receipt_proof(LEAVES[2], LEAVES)
    assert set(doc) == {"schema", "leaf", "index", "tree_size",
                        "merkle_root", "audit_path"}
    assert doc["schema"] == SCHEMA == "flywheel.receipts-proof/v2"
    assert doc["leaf"] == LEAVES[2]
    assert doc["index"] == 2
    assert doc["tree_size"] == 5
    assert doc["merkle_root"] == ROOT
    assert doc["audit_path"] == PROOF_IDX_2


def test_every_step_is_exactly_hash_and_side():
    doc = build_receipt_proof(LEAVES[0], LEAVES)
    for step in doc["audit_path"]:
        assert set(step) == {"hash", "side"}
        assert step["side"] in ("left", "right")
        assert len(step["hash"]) == 64
        int(step["hash"], 16)


def test_valid_proof_verifies_with_the_shared_walker():
    doc = build_receipt_proof(LEAVES[2], LEAVES)
    assert verify_inclusion(doc["leaf"], doc["audit_path"],
                            doc["merkle_root"]) is True


def test_single_leaf_tree_has_an_empty_path():
    solo = [LEAVES[0]]
    doc = build_receipt_proof(LEAVES[0], solo)
    assert doc["tree_size"] == 1
    assert doc["audit_path"] == []
    assert doc["index"] == 0


@pytest.mark.parametrize("bad", ["", "abc", "XYZ" + "0" * 61,
                                 ("abcdef" + "0" * 58).upper()])
def test_malformed_leaf_is_typed_with_a_fixed_message(bad):
    with pytest.raises(ReceiptProofError) as e:
        build_receipt_proof(bad, LEAVES)
    assert "64-hex" in str(e.value)


def test_malformed_leaf_is_not_a_not_found():
    with pytest.raises(ReceiptProofError) as e:
        build_receipt_proof("nothex", LEAVES)
    assert not isinstance(e.value, LeafNotFound)


def test_absent_leaf_raises_typed_not_found():
    stranger = format(0xABCDEF, "064x")
    with pytest.raises(LeafNotFound):
        build_receipt_proof(stranger, LEAVES)


def test_route_payload_maps_outcomes_to_fixed_statuses():
    body, code = route_payload(LEAVES[2], LEAVES)
    assert code == 200
    assert body["schema"] == SCHEMA

    bad_body, bad_code = route_payload("short", LEAVES)
    assert bad_code == 400
    assert set(bad_body) == {"error"}
    assert "64-hex" in bad_body["error"]

    stranger = format(0xABCDEF, "064x")
    miss_body, miss_code = route_payload(stranger, LEAVES)
    assert miss_code == 404
    assert miss_body["leaf"] == stranger
    assert miss_body["merkle_root"] == ROOT
