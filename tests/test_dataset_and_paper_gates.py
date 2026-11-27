# SPDX-License-Identifier: MIT
"""Unit tests for harness/dataset_attest and harness/paper_citation_gate."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from harness.dataset_attest import (
    HONEST_SCOPE_LIMIT as DATASET_SCOPE_LIMIT,
)
from harness.dataset_attest import (
    verify_dataset_pack,
    verify_dataset_pack_files,
)
from harness.paper_citation_gate import (
    HONEST_SCOPE_LIMIT as PAPER_SCOPE_LIMIT,
)
from harness.paper_citation_gate import (
    PaperSpec,
    scan_document_hygiene,
    verify_paper_bundle,
    verify_paper_bundle_files,
)

SHA_OK = "a" * 64


def _sample_pack() -> tuple[dict[str, Any], dict[str, Any], str, str, str]:
    bdb_rows = [
        {"record_id": "idea:A1", "license": "MIT", "content_sha256": SHA_OK, "reduction_pct": 0.0},
        {"record_id": "kern:K1", "license": "MIT", "content_sha256": SHA_OK, "reduction_pct": 52.5},
    ]
    tr_rows = [
        {"task_id": "T1", "license": "MIT", "split": "train", "source_sha256": SHA_OK, "reward_spec": {"pass_honest": 1.0, "hack": -1.0}},
        {"task_id": "T2", "license": "MIT", "split": "train", "source_sha256": SHA_OK, "reward_spec": {"pass_honest": 1.0, "hack": -1.0}},
    ]
    ev_rows = [
        {"task_id": "E1", "license": "MIT", "split": "eval", "source_sha256": SHA_OK, "reward_spec": {"pass_honest": 1.0, "hack": -1.0}},
    ]
    bdb_txt = "\n".join(json.dumps(r) for r in bdb_rows) + "\n"
    tr_txt = "\n".join(json.dumps(r) for r in tr_rows) + "\n"
    ev_txt = "\n".join(json.dumps(r) for r in ev_rows) + "\n"
    v5 = {
        "license": "MIT",
        "non_mit_rows": 0,
        "total_rows": 2,
        "record_type_counts": {"author_idea": 1, "buildlang_kernel": 1},
        "compression": {"ratio_x": 5.4},
        "artifacts": {
            "builddb_v5_mit.jsonl": {"bytes": len(bdb_txt.encode()), "sha256": f"sha256:{hashlib.sha256(bdb_txt.encode()).hexdigest()}"}
        },
    }
    v8 = {
        "license": "MIT",
        "total_tasks": 3,
        "train_tasks": 2,
        "eval_tasks": 1,
        "artifacts": {
            "train_rlvr_v8.jsonl": {"bytes": len(tr_txt.encode()), "sha256": f"sha256:{hashlib.sha256(tr_txt.encode()).hexdigest()}"},
            "eval_rlvr_v8.jsonl": {"bytes": len(ev_txt.encode()), "sha256": f"sha256:{hashlib.sha256(ev_txt.encode()).hexdigest()}"},
        },
    }
    return v5, v8, bdb_txt, tr_txt, ev_txt


def test_dataset_clean_pass_and_deterministic_attestation() -> None:
    v5, v8, bdb, tr, ev = _sample_pack()
    r1 = verify_dataset_pack(v5, v8, bdb, tr, ev)
    r2 = verify_dataset_pack(v5, v8, bdb, tr, ev)
    assert r1.passed and r1.builddb_rows == 2 and r1.rlvr_total_tasks == 3
    assert r1.non_mit_rows == 0 and r1.duplicate_ids == 0 and r1.train_eval_overlap == 0
    assert len(r1.dataset_attestation_sha256) == 64
    assert r1.dataset_attestation_sha256 == r2.dataset_attestation_sha256


def test_dataset_rejects_non_mit_license_leak() -> None:
    v5, v8, bdb, tr, ev = _sample_pack()
    bad_bdb = bdb.replace('"MIT"', '"AGPL-3.0-only"', 1)
    rep = verify_dataset_pack(v5, v8, bad_bdb, tr, ev)
    assert not rep.passed and rep.non_mit_rows == 1


def test_dataset_rejects_train_eval_overlap_and_duplicate_id() -> None:
    v5, v8, bdb, tr, ev = _sample_pack()
    overlap_ev = ev.replace('"E1"', '"T1"')
    rep = verify_dataset_pack(v5, v8, bdb, tr, overlap_ev)
    assert not rep.passed and rep.train_eval_overlap == 1
    dup_bdb = bdb.replace('"kern:K1"', '"idea:A1"')
    rep2 = verify_dataset_pack(v5, v8, dup_bdb, tr, ev)
    assert not rep2.passed and rep2.duplicate_ids == 1


def test_dataset_rejects_pass_rate_below_floor_and_sha_tamper() -> None:
    v5, v8, bdb, tr, ev = _sample_pack()
    assert not verify_dataset_pack(v5, v8, bdb, tr, ev, oracle_pass_rate=0.95).passed
    bad_hashes = {"builddb_v5_mit.jsonl": (len(bdb.encode()), "0" * 64)}
    assert not verify_dataset_pack(v5, v8, bdb, tr, ev, actual_hashes=bad_hashes).passed


@pytest.mark.parametrize("bad_rate", [math.nan, math.inf, -math.inf, True, False, -0.1, 1.1])
def test_dataset_rejects_non_finite_and_bool_pass_rates(bad_rate: Any) -> None:
    v5, v8, bdb, tr, ev = _sample_pack()
    assert not verify_dataset_pack(v5, v8, bdb, tr, ev, oracle_pass_rate=bad_rate).passed
    assert not verify_dataset_pack(v5, v8, bdb, tr, ev, min_oracle_pass_rate=bad_rate).passed


def test_dataset_file_roundtrip_and_missing_dir(tmp_path: Path) -> None:
    v5, v8, bdb, tr, ev = _sample_pack()
    (tmp_path / "v5_manifest.json").write_bytes(json.dumps(v5).encode("utf-8"))
    (tmp_path / "v8_rlvr_manifest.json").write_bytes(json.dumps(v8).encode("utf-8"))
    (tmp_path / "builddb_v5_mit.jsonl").write_bytes(bdb.encode("utf-8"))
    (tmp_path / "train_rlvr_v8.jsonl").write_bytes(tr.encode("utf-8"))
    (tmp_path / "eval_rlvr_v8.jsonl").write_bytes(ev.encode("utf-8"))
    assert verify_dataset_pack_files(tmp_path).passed
    assert not verify_dataset_pack_files(tmp_path / "missing").passed


def test_paper_clean_pass_with_honest_disclaimer() -> None:
    p1 = PaperSpec("paper1", 68793, "Receipt 68793 and 68741 verified; zero LLC/Inc claims.")
    p2 = PaperSpec("paper2", 68797, "Receipt 68797 verified cleanly; no LLC status claimed.")
    rep = verify_paper_bundle(
        [p1, p2],
        known_catalogue_ids={68793, 68797, 68741},
        receipt_verdicts={68793: True, 68797: True},
        min_docs=2,
    )
    assert rep.passed and rep.docs_checked == 2 and rep.primary_receipts_matched == 2
    assert rep.local_path_leaks == 0 and rep.dash_hits == 0 and rep.false_entity_hits == 0
    assert len(rep.paper_citation_attestation_sha256) == 64


def test_paper_rejects_forged_cid_and_receipt_drift() -> None:
    p1 = PaperSpec("paper1", 68793, "Verified against catalogue_id: 999999.")
    rep = verify_paper_bundle([p1], known_catalogue_ids={68793})
    assert not rep.passed and rep.forged_catalogue_ids == (999999,)
    p2 = PaperSpec("paper2", 68797, "Clean receipt 68797.")
    rep2 = verify_paper_bundle([p2], known_catalogue_ids={68797}, receipt_verdicts={68797: False})
    assert not rep2.passed and rep2.primary_receipts_matched == 0


@pytest.mark.parametrize(
    "bad_text",
    [
        "See " + "C:" + "/Users/alice/work.md for details.",
        "Stored under " + "D:" + "\\secret\\build.json.",
        "Check /home" + "/bob/data.txt now.",
        "Built by Example Labs LLC in Seattle.",
        "Sponsored by Example Systems Inc. today.",
        "Text with em dash \u2014 rejected.",
        "Text with en dash \u2013 rejected.",
    ],
)
def test_paper_rejects_path_leaks_false_entities_and_dashes(bad_text: str) -> None:
    spec = PaperSpec("doc1", 68793, bad_text)
    rep = verify_paper_bundle([spec], known_catalogue_ids={68793})
    assert not rep.passed


@pytest.mark.parametrize("bad_ratio", [math.nan, math.inf, -math.inf, True, False, -0.1, 1.1])
def test_paper_rejects_invalid_match_ratio(bad_ratio: Any) -> None:
    spec = PaperSpec("doc1", 68793, "Clean receipt 68793.")
    assert not verify_paper_bundle([spec], known_catalogue_ids={68793}, min_match_ratio=bad_ratio).passed


@pytest.mark.parametrize("bad_min_docs", [True, False, 0, -2, math.nan, "4"])
def test_paper_rejects_invalid_min_docs(bad_min_docs: Any) -> None:
    spec = PaperSpec("doc1", 68793, "Clean receipt 68793.")
    assert not verify_paper_bundle([spec], known_catalogue_ids={68793}, min_docs=bad_min_docs).passed


def test_paper_file_roundtrip_and_hygiene_scanner(tmp_path: Path) -> None:
    f = tmp_path / "p1.md"
    f.write_text("Verified 68793 with zero LLC/Inc claims.", encoding="utf-8")
    rep = verify_paper_bundle_files([("paper1", 68793, f)], known_catalogue_ids={68793})
    assert rep.passed and scan_document_hygiene("cid: 68793").cited_catalogue_ids == (68793,)
    assert not verify_paper_bundle_files([("missing", 68793, tmp_path / "no.md")]).passed


def test_explicit_honest_scope_limits_present() -> None:
    assert "Pure-Python stdlib" in DATASET_SCOPE_LIMIT
    assert "Pure-Python stdlib" in PAPER_SCOPE_LIMIT
