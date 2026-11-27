# SPDX-FileCopyrightText: 2026 Zain Dana Harper
# SPDX-License-Identifier: MIT
"""Unit and planted fail-closed trap tests for harness.search_forge (24 tests)."""
from __future__ import annotations

from dataclasses import replace

import pytest

from harness.search_forge import (
    DagNode,
    build_refit_chain,
    build_second_channel_envelope,
    seal_citation_span,
    validate_crop_bbox,
    verify_citation_bundle,
    verify_citation_span,
    verify_refit_dag,
    verify_second_channel,
)
from harness.search_forge.citation_verifier import sha256_bytes
from harness.search_forge.second_channel import verify_channel_batch

CORPUS_BYTES = b"BuildLang 1.15.0 verifies superopt certificates with zero semantic drift.\n"
CORPUS_STORE = {"doc-01": CORPUS_BYTES}


# --- N43 Citation Span Verifier tests (8) ---


def test_n43_valid_byte_span_seals_and_verifies_exact() -> None:
    start = CORPUS_BYTES.index(b"superopt certificates")
    end = start + len(b"superopt certificates")
    span = seal_citation_span("doc-01", CORPUS_BYTES, start, end)
    verdict = verify_citation_span(span, CORPUS_STORE)
    assert verdict.ok and verdict.verdict == "PASS" and span.quoted_text == "superopt certificates"


def test_n43_rejects_hallucinated_quote_text() -> None:
    span = seal_citation_span("doc-01", CORPUS_BYTES, 0, 16)
    forged = replace(span, quoted_text="Invented Quote!!")
    verdict = verify_citation_span(forged, CORPUS_STORE)
    assert not verdict.ok and verdict.reason == "quoted_text_hallucination"


def test_n43_rejects_shifted_byte_offset_mismatch() -> None:
    span = seal_citation_span("doc-01", CORPUS_BYTES, 0, 16)
    shifted = replace(span, byte_start=1, byte_end=17)
    verdict = verify_citation_span(shifted, CORPUS_STORE)
    assert not verdict.ok and verdict.reason == "span_sha256_mismatch"


def test_n43_rejects_out_of_bounds_and_inverted_offsets() -> None:
    span = seal_citation_span("doc-01", CORPUS_BYTES, 0, 10)
    oob = replace(span, byte_end=len(CORPUS_BYTES) + 5)
    inv = replace(span, byte_start=10, byte_end=5)
    assert verify_citation_span(oob, CORPUS_STORE).reason == "byte_offset_out_of_bounds"
    assert verify_citation_span(inv, CORPUS_STORE).reason == "byte_offset_out_of_bounds"


def test_n43_rejects_source_sha256_mismatch_and_missing_source() -> None:
    span = seal_citation_span("doc-01", CORPUS_BYTES, 0, 9)
    tampered_store = {"doc-01": CORPUS_BYTES + b"extra"}
    assert verify_citation_span(span, tampered_store).reason == "source_sha256_mismatch"
    assert verify_citation_span(span, {}).reason == "missing_source_id"


def test_n43_seal_rejects_empty_id_and_invalid_bounds() -> None:
    with pytest.raises(ValueError):
        seal_citation_span("  ", CORPUS_BYTES, 0, 5)
    with pytest.raises(ValueError):
        seal_citation_span("doc-01", CORPUS_BYTES, 10, 10)


def test_n43_bundle_passes_valid_and_rejects_empty_or_poisoned() -> None:
    s1 = seal_citation_span("doc-01", CORPUS_BYTES, 0, 9)
    s2 = seal_citation_span("doc-01", CORPUS_BYTES, 10, 16)
    ok_res = verify_citation_bundle([s1, s2], CORPUS_STORE)
    assert ok_res["ok"] and ok_res["verified"] == 2
    empty_res = verify_citation_bundle([], CORPUS_STORE)
    assert not empty_res["ok"] and empty_res["verdict"] == "REJECT"
    bad_res = verify_citation_bundle([s1, replace(s2, quoted_text="FAKE!!")], CORPUS_STORE)
    assert not bad_res["ok"] and bad_res["verified"] == 1


def test_n43_rejects_invalid_utf8_byte_slice() -> None:
    raw = b"\xff\xfe\xfdhello"
    fake_span = seal_citation_span("doc-01", CORPUS_BYTES, 0, 3)
    bad = replace(fake_span, source_id="bin-01", source_sha256=sha256_bytes(raw), span_sha256=sha256_bytes(raw[:3]))
    assert verify_citation_span(bad, {"bin-01": raw}).reason == "invalid_utf8_slice"


# --- N27 Typed Orthogonal Second-Channel tests (8) ---


def test_n27_orthogonal_envelope_passes() -> None:
    env = build_second_channel_envelope(
        sha256_bytes(b"claim-1"), "build_oracle", 1000, "cryptographic_receipt", 1050, sha256_bytes(b"witness-1")
    )
    v = verify_second_channel(env)
    assert v.ok and v.verdict == "PASS" and not v.errors


def test_n27_rejects_same_channel_self_corroboration() -> None:
    env = build_second_channel_envelope(
        sha256_bytes(b"claim-1"), "build_oracle", 1000, "build_oracle", 1050, sha256_bytes(b"witness-1")
    )
    v = verify_second_channel(env)
    assert not v.ok and "same_channel_self_corroboration" in v.errors


def test_n27_rejects_empty_and_unknown_channel_types() -> None:
    e_empty = build_second_channel_envelope(
        sha256_bytes(b"c"), "build_oracle", 1000, "", 1050, sha256_bytes(b"w")
    )
    e_unk = build_second_channel_envelope(
        sha256_bytes(b"c"), "build_oracle", 1000, "vibe_check", 1050, sha256_bytes(b"w")
    )
    assert not verify_second_channel(e_empty).ok
    assert any("invalid_second_channel" in e for e in verify_second_channel(e_unk).errors)


def test_n27_rejects_causal_reversal_second_before_primary() -> None:
    env = build_second_channel_envelope(
        sha256_bytes(b"c"), "build_oracle", 2000, "static_ast", 1999, sha256_bytes(b"w")
    )
    v = verify_second_channel(env)
    assert not v.ok and "causal_reversal_second_before_primary" in v.errors


def test_n27_rejects_non_positive_timestamps() -> None:
    env = build_second_channel_envelope(
        sha256_bytes(b"c"), "build_oracle", 0, "static_ast", 10, sha256_bytes(b"w")
    )
    assert "non_positive_timestamp" in verify_second_channel(env).errors


def test_n27_rejects_duplicate_witness_equals_claim_digest() -> None:
    same = sha256_bytes(b"same-digest")
    env = build_second_channel_envelope(same, "build_oracle", 1000, "static_ast", 1001, same)
    assert "duplicate_witness_equals_claim_digest" in verify_second_channel(env).errors


def test_n27_rejects_tampered_envelope_sha256() -> None:
    env = build_second_channel_envelope(
        sha256_bytes(b"c"), "build_oracle", 1000, "hardware_sensor", 1100, sha256_bytes(b"w")
    )
    tampered = replace(env, second_timestamp_ns=1200)
    assert "envelope_sha256_tampered" in verify_second_channel(tampered).errors


def test_n27_batch_rejects_empty_and_mixed_batches() -> None:
    good = build_second_channel_envelope(
        sha256_bytes(b"c"), "build_oracle", 1000, "out_of_band_corpus", 1010, sha256_bytes(b"w")
    )
    bad = build_second_channel_envelope(
        sha256_bytes(b"c"), "build_oracle", 1000, "build_oracle", 1010, sha256_bytes(b"w")
    )
    assert verify_channel_batch([good])["ok"] is True
    assert verify_channel_batch([])["ok"] is False
    mix = verify_channel_batch([good, bad])
    assert mix["ok"] is False and mix["failed_indices"] == [1]


# --- N32 Gather Refit Provenance DAG tests (8) ---


def test_n32_valid_four_stage_refit_chain_verifies_deterministically() -> None:
    nodes = build_refit_chain(CORPUS_BYTES, (0.1, 0.2, 0.8, 0.9), "zero semantic drift", "drift == 0")
    v1 = verify_refit_dag(nodes)
    v2 = verify_refit_dag(tuple(reversed(nodes)))
    assert v1.ok and v1.verdict == "PASS" and v1.dag_root_sha256.startswith("sha256:")
    assert v1.topo_order == v2.topo_order and v1.dag_root_sha256 == v2.dag_root_sha256


def test_n32_rejects_empty_dag() -> None:
    v = verify_refit_dag([])
    assert not v.ok and "empty_dag" in v.errors


def test_n32_rejects_cycle_via_kahn_topological_sort() -> None:
    a = DagNode("n:a", "source_sha256", sha256_bytes(b"a"), parents=("n:b",))
    b = DagNode("n:b", "claim_hash", sha256_bytes(b"b"), parents=("n:a",))
    v = verify_refit_dag([a, b])
    assert not v.ok and "cycle_detected_by_kahn_sort" in v.errors


def test_n32_rejects_orphan_non_root_and_dangling_parent() -> None:
    orphan = DagNode("n:claim", "claim_hash", sha256_bytes(b"x"), parents=())
    dangling = DagNode("n:quote", "quote_hash", sha256_bytes(b"y"), parents=("missing:crop",))
    assert "orphan_non_root_node:n:claim" in verify_refit_dag([orphan]).errors
    assert "missing_parent:n:quote->missing:crop" in verify_refit_dag([dangling]).errors


def test_n32_rejects_stage_order_inversion() -> None:
    src, crop, quote, claim = build_refit_chain(CORPUS_BYTES, (0.0, 0.0, 0.5, 0.5), "q", "c")
    bad_quote = replace(quote, parents=(claim.node_id,))
    v = verify_refit_dag([src, crop, bad_quote, claim])
    assert not v.ok and any("stage_order_violation" in e for e in v.errors)


def test_n32_rejects_invalid_crop_bbox_bounds() -> None:
    assert validate_crop_bbox((0.0, 0.0, 1.0, 1.0)) is True
    assert validate_crop_bbox((0.5, 0.1, 0.5, 0.9)) is False
    assert validate_crop_bbox((-0.1, 0.0, 0.5, 0.5)) is False
    assert validate_crop_bbox((0.0, 0.0, 1.2, 0.5)) is False
    with pytest.raises(ValueError):
        build_refit_chain(CORPUS_BYTES, (0.8, 0.2, 0.4, 0.9), "q", "c")


def test_n32_rejects_duplicate_node_id_and_bad_digest() -> None:
    src, crop, quote, claim = build_refit_chain(CORPUS_BYTES, (0.1, 0.1, 0.5, 0.5), "q", "c")
    dup = verify_refit_dag([src, src, crop, quote, claim])
    assert not dup.ok and any("duplicate_node_id" in e for e in dup.errors)
    bad_dig = verify_refit_dag([replace(src, digest="md5:123"), crop, quote, claim])
    assert not bad_dig.ok and any("invalid_digest" in e for e in bad_dig.errors)


def test_n32_multi_source_convergent_claim_dag_verifies() -> None:
    s1, c1, q1, _ = build_refit_chain(CORPUS_BYTES, (0.0, 0.0, 0.5, 0.5), "part1", "c1", prefix="a")
    s2, c2, q2, _ = build_refit_chain(b"Second verified witness.\n", (0.2, 0.2, 0.9, 0.9), "part2", "c2", prefix="b")
    joint = DagNode("joint:claim", "claim_hash", sha256_bytes(b"joint"), parents=(q1.node_id, q2.node_id))
    v = verify_refit_dag([s1, c1, q1, s2, c2, q2, joint])
    assert v.ok and len(v.topo_order) == 7 and v.topo_order[-1] == "joint:claim"
