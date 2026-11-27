# SPDX-License-Identifier: MIT
"""Unit and adversarial tamper tests for harness.crypto_attest."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from harness import crypto_attest as ca

RFC8439_PT = (
    b"Ladies and Gentlemen of the class of '99: "
    b"If I could offer you only one tip for the future, sunscreen would be it."
)
RFC8439_KEY = bytes(range(0x80, 0xA0))
RFC8439_NONCE = bytes.fromhex("070000004041424344454647")
RFC8439_AAD = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
RFC8439_CT_HEX = (
    "d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d6"
    "3dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b36"
    "92ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc"
    "3ff4def08e4b7a9de576d26586cec64b6116"
)


def _sample_five_isa() -> tuple[list[ca.IsaBuildRecord], dict[str, bytes], bytes]:
    stdout = b"1ae10b594f09e26a7e902ecbd0600691\n"
    raw_bins = {tgt: f"binary-payload-{tgt}".encode() for tgt in ca.REQUIRED_TARGETS}
    recs = [ca.build_record_from_bytes(t, raw_bins[t], stdout) for t in ca.REQUIRED_TARGETS]
    return recs, raw_bins, stdout


def test_multi_isa_parity_passes_five_targets() -> None:
    recs, raw_bins, stdout = _sample_five_isa()
    rep = ca.verify_multi_isa_parity(
        recs,
        expected_stdout_sha256=ca.sha256_hex(stdout),
        binary_bytes_by_target=raw_bins,
        max_binary_bytes=16384,
    )
    assert rep.passed is True
    assert rep.consensus_stdout_sha256 == ca.sha256_hex(stdout)
    assert rep.targets_verified == ca.REQUIRED_TARGETS
    assert rep.reasons == () and len(rep.attestation_sha256) == 64


@pytest.mark.parametrize("dropped", ca.REQUIRED_TARGETS)
def test_multi_isa_missing_target_fails_closed(dropped: str) -> None:
    recs, _, _ = _sample_five_isa()
    rep = ca.verify_multi_isa_parity([r for r in recs if r.target != dropped])
    assert rep.passed is False and rep.missing_targets == (dropped,)
    assert any(f"MISSING_REQUIRED_TARGETS:{dropped}" in r for r in rep.reasons)


@pytest.mark.parametrize("bad_target", ca.REQUIRED_TARGETS)
def test_multi_isa_single_target_stdout_divergence_caught(bad_target: str) -> None:
    recs, _, _ = _sample_five_isa()
    mutated = [
        ca.IsaBuildRecord(r.target, r.binary_sha256, ca.sha256_hex(b"bad"), r.binary_bytes)
        if r.target == bad_target
        else r
        for r in recs
    ]
    rep = ca.verify_multi_isa_parity(mutated)
    assert rep.passed is False and rep.divergent_targets == (bad_target,)
    assert any(f"SINGLE_ISA_STDOUT_DIVERGENCE:{bad_target}" in r for r in rep.reasons)


def test_multi_isa_forged_binary_digest_caught() -> None:
    recs, raw_bins, _ = _sample_five_isa()
    raw_bins["wasm"] = raw_bins["wasm"] + b"!"
    rep = ca.verify_multi_isa_parity(recs, binary_bytes_by_target=raw_bins)
    assert rep.passed is False
    assert "FORGED_BINARY_DIGEST:wasm" in rep.reasons
    assert "FORGED_BINARY_SIZE:wasm" in rep.reasons


def test_multi_isa_nonzero_exit_and_size_limit_caught() -> None:
    recs, _, _ = _sample_five_isa()
    recs[0] = ca.IsaBuildRecord("x64-pe", recs[0].binary_sha256, recs[0].stdout_sha256, 20000, 1)
    rep = ca.verify_multi_isa_parity(recs, max_binary_bytes=16384)
    assert rep.passed is False
    assert "NON_ZERO_EXIT:x64-pe:1" in rep.reasons
    assert "BINARY_SIZE_EXCEEDS_LIMIT:x64-pe:20000" in rep.reasons


def test_multi_isa_duplicate_unknown_and_malformed_caught() -> None:
    recs, _, _ = _sample_five_isa()
    bad = [*recs, recs[0], ca.IsaBuildRecord("mips64-elf", "deadbeef", "0" * 64, 100)]
    rep = ca.verify_multi_isa_parity(bad, expected_stdout_sha256="not-hex")
    assert rep.passed is False
    assert "DUPLICATE_TARGET:x64-pe" in rep.reasons
    assert "UNKNOWN_TARGET:mips64-elf" in rep.reasons
    assert "MALFORMED_EXPECTED_STDOUT_DIGEST" in rep.reasons


def test_multi_isa_expected_stdout_mismatch_and_to_dict() -> None:
    recs, _, _ = _sample_five_isa()
    rep = ca.verify_multi_isa_parity(recs, expected_stdout_sha256=ca.sha256_hex(b"other"))
    assert rep.passed is False and rep.consensus_stdout_sha256 is None
    assert rep.to_dict()["passed"] is False
    assert sum(1 for r in rep.reasons if r.startswith("EXPECTED_STDOUT_MISMATCH:")) == 5


def test_merkle_empty_and_single_leaf_roots() -> None:
    assert ca.merkle_root([]) == ca.EMPTY_TREE_HASH
    assert ca.merkle_root([b"alpha"]) == ca.leaf_hash(b"alpha")
    assert ca.inclusion_proof([b"alpha"], 0) == []
    assert ca.verify_inclusion(b"alpha", 0, 1, [], ca.leaf_hash(b"alpha")) is True


def test_merkle_inclusion_exhaustive_sizes_1_to_12() -> None:
    leaves = [f"entry-{i}".encode() for i in range(12)]
    for size in range(1, 13):
        subset = leaves[:size]
        root = ca.merkle_root(subset)
        for idx in range(size):
            proof = ca.inclusion_proof(subset, idx)
            assert ca.verify_inclusion(subset[idx], idx, size, proof, root) is True


def test_merkle_inclusion_catches_1bit_leaf_and_proof_flips() -> None:
    leaves = [f"leaf-{i}".encode() for i in range(7)]
    root = ca.merkle_root(leaves)
    proof = ca.inclusion_proof(leaves, 3)
    flipped_leaf = bytes([leaves[3][0] ^ 1]) + leaves[3][1:]
    flipped_proof = [bytes([proof[0][0] ^ 1]) + proof[0][1:], *proof[1:]]
    assert ca.verify_inclusion(flipped_leaf, 3, 7, proof, root) is False
    assert ca.verify_inclusion(leaves[3], 3, 7, flipped_proof, root) is False
    assert ca.verify_inclusion(leaves[3], 3, 7, [*proof, b"\x00" * 32], root) is False
    assert ca.verify_inclusion(leaves[3], 7, 7, proof, root) is False


def test_merkle_second_preimage_domain_separation() -> None:
    left, right = ca.leaf_hash(b"left-record"), ca.leaf_hash(b"right-record")
    assert ca.check_domain_separation(left, right) is True
    two_root = ca.merkle_root([b"left-record", b"right-record"])
    assert two_root == ca.node_hash(left, right)
    assert ca.merkle_root([left + right]) != two_root
    assert ca.verify_inclusion(left + right, 0, 1, [], two_root) is False


def test_merkle_consistency_exhaustive_pairs() -> None:
    leaves = [f"log-event-{i}".encode() for i in range(11)]
    roots = [ca.merkle_root(leaves[:n]) for n in range(12)]
    for first in range(0, 12):
        for second in range(first, 12):
            proof = ca.consistency_proof(leaves, first, second)
            assert ca.verify_consistency(first, second, roots[first], roots[second], proof) is True


def test_merkle_consistency_catches_1bit_flip_and_forked_history() -> None:
    leaves = [f"rec-{i}".encode() for i in range(9)]
    r4, r9 = ca.merkle_root(leaves[:4]), ca.merkle_root(leaves)
    proof = ca.consistency_proof(leaves, 4, 9)
    assert ca.verify_consistency(4, 9, r4, r9, proof) is True
    bad_proof = [bytes([proof[0][0] ^ 1]) + proof[0][1:], *proof[1:]]
    assert ca.verify_consistency(4, 9, r4, r9, bad_proof) is False
    forked = [*leaves[:2], b"rewritten-history", *leaves[3:]]
    assert ca.verify_consistency(4, 9, r4, ca.merkle_root(forked), proof) is False
    assert ca.verify_consistency(9, 4, r9, r4, proof) is False


def test_aead_rfc8439_section_2_8_2_exact_vector() -> None:
    ct, tag = ca.aead_seal(RFC8439_KEY, RFC8439_NONCE, RFC8439_PT, aad=RFC8439_AAD)
    assert ct.hex() == RFC8439_CT_HEX
    assert tag.hex() == ca.RFC8439_SECTION_2_8_2_TAG_HEX
    assert ca.aead_open(RFC8439_KEY, RFC8439_NONCE, ct, tag, aad=RFC8439_AAD) == RFC8439_PT


def test_aead_1bit_ciphertext_flip_fails_closed() -> None:
    ct, tag = ca.aead_seal(RFC8439_KEY, RFC8439_NONCE, RFC8439_PT, aad=RFC8439_AAD)
    with pytest.raises(ca.AeadAuthError):
        ca.aead_open(RFC8439_KEY, RFC8439_NONCE, bytes([ct[0] ^ 1]) + ct[1:], tag, aad=RFC8439_AAD)


def test_aead_1bit_aad_flip_fails_closed() -> None:
    ct, tag = ca.aead_seal(RFC8439_KEY, RFC8439_NONCE, RFC8439_PT, aad=RFC8439_AAD)
    bad_aad = bytes([RFC8439_AAD[0] ^ 1]) + RFC8439_AAD[1:]
    with pytest.raises(ca.AeadAuthError):
        ca.aead_open(RFC8439_KEY, RFC8439_NONCE, ct, tag, aad=bad_aad)


def test_aead_1bit_tag_flip_fails_closed() -> None:
    ct, tag = ca.aead_seal(RFC8439_KEY, RFC8439_NONCE, RFC8439_PT, aad=RFC8439_AAD)
    bad_tag = tag[:-1] + bytes([tag[-1] ^ 1])
    with pytest.raises(ca.AeadAuthError):
        ca.aead_open(RFC8439_KEY, RFC8439_NONCE, ct, bad_tag, aad=RFC8439_AAD)


def test_aead_wrong_key_nonce_and_empty_plaintext() -> None:
    ct, tag = ca.aead_seal(RFC8439_KEY, RFC8439_NONCE, b"", aad=b"header-only")
    assert ct == b"" and ca.aead_open(RFC8439_KEY, RFC8439_NONCE, ct, tag, aad=b"header-only") == b""
    wrong_key = bytes([RFC8439_KEY[0] ^ 1]) + RFC8439_KEY[1:]
    with pytest.raises(ca.AeadAuthError):
        ca.aead_open(wrong_key, RFC8439_NONCE, ct, tag, aad=b"header-only")
    with pytest.raises(ca.AeadAuthError):
        ca.aead_seal(b"short-key", RFC8439_NONCE, b"msg")
    with pytest.raises(ca.AeadAuthError):
        ca.aead_seal(RFC8439_KEY, b"short", b"msg")


def test_aead_envelope_roundtrip_and_tamper_rejection() -> None:
    env = ca.seal_envelope(RFC8439_KEY, RFC8439_NONCE, RFC8439_PT, aad=RFC8439_AAD)
    assert env["tag_hex"] == ca.RFC8439_SECTION_2_8_2_TAG_HEX
    assert ca.open_envelope(RFC8439_KEY, env) == RFC8439_PT
    with pytest.raises(ca.AeadAuthError):
        ca.open_envelope(RFC8439_KEY, dict(env, schema="wrong/1"))
    with pytest.raises(ca.AeadAuthError):
        ca.open_envelope(RFC8439_KEY, dict(env, tag_hex="zz" * 16))


def test_package_hygiene_loc_spdx_stdlib_and_scope_limits() -> None:
    root = Path(__file__).resolve().parents[1]
    pkg_files = sorted((root / "harness" / "crypto_attest").glob("*.py"))
    assert len(pkg_files) == 4
    assert set(ca.HONEST_SCOPE_LIMITS) == {"multi_isa_parity", "merkle_attest", "aead_envelope"}
    for path in [*pkg_files, Path(__file__).resolve()]:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        assert len(lines) <= 250, f"{path.name} has {len(lines)} lines (> 250)"
        assert lines[0] == "# SPDX-License-Identifier: MIT"
        assert "\u2014" not in text and "\u2013" not in text
    for path in pkg_files:
        text = path.read_text(encoding="utf-8")
        assert "HONEST_SCOPE_LIMIT" in text
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Import):
                assert all(a.name.split(".")[0] in sys.stdlib_module_names for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in sys.stdlib_module_names
