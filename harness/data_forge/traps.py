"""Planted dirty-data, HIPAA, patient-bleed, SI-physics, and Merkle-tamper controls."""

from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from .adapters import assign_patient_level_split, verify_zero_patient_bleed
from .common import extract_row_text
from .scoring_and_seal import verify_sealed_dataset


def run_pre_seal_traps(
    start_idx: int,
    first_surviving_text: str | None,
    holdout_rows: Sequence[dict[str, Any]],
    process_row: Callable[[int, dict[str, Any]], None],
    record_reject: Callable[[int, str, str, str, str | None], None],
) -> int:
    """Inject 8 pre-seal dirty-data, HIPAA, patient-bleed, and SI-physics traps."""
    idx = start_idx
    base_txt = (
        first_surviving_text
        or "Deterministic verification pipeline for numerical kernels with strict parity checks and audit receipts."
    )
    words = base_txt.split()
    near_dup = " ".join(words[:-1] + ["verified_variant"]) if len(words) > 14 else (base_txt + " extra")
    ho_sample = extract_row_text(holdout_rows[0]) if holdout_rows else "sealed holdout sentinel"

    row_traps: tuple[dict[str, Any], ...] = (
        {
            "id": "trap-1-secret", "license": "MIT", "_source_corpus": "planted_trap",
            "_planted_trap_id": "trap1_secret_key",
            "text": "Deploy using API key sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz123456 and admin@corp.example",
        },
        {
            "id": "trap-2-neardup", "license": "MIT", "_source_corpus": "planted_trap",
            "_planted_trap_id": "trap2_near_duplicate", "text": near_dup,
        },
        {
            "id": "trap-3-holdout", "license": "MIT", "_source_corpus": "planted_trap",
            "_planted_trap_id": "trap3_holdout_contamination",
            "text": "Rephrased wrapper around sealed evaluation item: " + ho_sample,
        },
        {
            "id": "trap-4-leaky-grader", "license": "clean-room-synthetic",
            "oracle_kind": "leaky_regex_trap", "_source_corpus": "planted_trap",
            "_planted_trap_id": "trap4_leaky_unverified_grader",
            "text": "Solve for x with a broken regex grader that accepts PASS unconditionally in every test.",
        },
        {
            "id": "trap-7-hipaa-phi", "domain": "medical_clinical", "license": "clean-room-synthetic",
            "_source_corpus": "planted_trap", "_planted_trap_id": "trap7_hipaa_phi_leak",
            "text": "Patient Name: Jane Doe MRN-448291 seen on 2025-03-19 from ZIP 03604 with elevated heart rate.",
        },
        {
            "id": "trap-9-si-mismatch", "domain": "scientific_physics", "license": "clean-room-synthetic",
            "si_lhs_units": ["J"], "si_rhs_units": ["N"],
            "conservation_in": 100.0, "conservation_out": 82.0,
            "_source_corpus": "planted_trap", "_planted_trap_id": "trap9_si_dimensional_violation",
            "text": "Equate energy in Joules directly to force in Newtons across an unclosed thermal boundary.",
        },
    )
    for trap_row in row_traps:
        idx += 1
        process_row(idx, trap_row)

    idx += 1
    try:
        json.loads(b'{"text": "\xff\xfe broken utf8 json'.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        record_reject(idx, "planted_trap", "stage0_parse", "MALFORMED_INPUT:INVALID_UTF8", "trap5_malformed_utf8_json")

    idx += 1
    clean_pids = [f"cohort-p{k:03d}" for k in range(40)]
    tr_p = [p for p in clean_pids if assign_patient_level_split(p) == "train"]
    ev_p = [p for p in clean_pids if assign_patient_level_split(p) == "eval"]
    ok_clean, _ = verify_zero_patient_bleed(tr_p, ev_p)
    if not ok_clean:
        raise RuntimeError("Deterministic patient split produced unexpected overlap")
    ok_bleed, leaked = verify_zero_patient_bleed(tr_p, ev_p + [tr_p[0]])
    if not ok_bleed:
        record_reject(
            idx, "planted_trap", "stage3_patient_split_guard",
            f"PATIENT_SPLIT_BLEED_DETECTED:{leaked[0]}", "trap8_patient_split_bleed",
        )
    return idx


def run_post_seal_merkle_tamper_trap(out_dir: Path) -> str:
    """Mutate a temporary copy of the sealed dataset and verify RFC 6962 tamper detection."""
    tamper_path = out_dir / "_tmp_tamper_probe.jsonl.gz"
    try:
        with gzip.open(out_dir / "forged_dataset.jsonl.gz", "rb") as src_gz:
            all_lines = src_gz.readlines()
        with gzip.open(tamper_path, "wb") as dst_gz:
            dst_gz.write(all_lines[0].replace(b"df-0000000", b"df-9999999", 1))
            dst_gz.writelines(all_lines[1:])
        t_ok, t_reason = verify_sealed_dataset(tamper_path, out_dir / "merkle_proof_bundle.json")
        if t_ok or "MERKLE_TAMPER_DETECTED" not in t_reason:
            raise RuntimeError(f"Merkle tamper probe unexpectedly passed: {t_reason}")
        return f"CAUGHT:stage6_merkle:{t_reason}"
    finally:
        tamper_path.unlink(missing_ok=True)
