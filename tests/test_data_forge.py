"""Pytest verification suite for harness.data_forge (6-stage Proof-Carrying Data Forge)."""

from __future__ import annotations

import gzip
import importlib.util
import json
import re
import shutil
from pathlib import Path

from harness.data_forge import (
    BUILTIN_SFTS_RECORDS,
    FLYWHEEL_MODULES_LINKED,
    HoldoutDecontaminator,
    ThreeTierDeduplicator,
    assign_patient_level_split,
    main,
    normalized_ast_hash,
    run_data_forge,
    run_domain_adapter,
    score_entropy_and_difficulty,
    stage1_provenance_firewall,
    synthesize_oracle_verified_rows,
    synthesize_search_from_the_start_rows,
    validate_oracle_candidate,
    verify_sealed_dataset,
    verify_zero_patient_bleed,
    word_tokens,
)


def test_flywheel_modules_linked() -> None:
    assert FLYWHEEL_MODULES_LINKED is True


def test_stage1_firewall_blocks_secrets_closed_licenses_and_privacy_modes() -> None:
    ok, reason, _ = stage1_provenance_firewall(
        {"license": "MIT"},
        "token sk-proj-0123456789abcdefghijKLMNOPQRST leaked here",
    )
    assert not ok and reason.startswith("SECRET_OR_PII_DETECTED")

    ok2, reason2, _ = stage1_provenance_firewall(
        {"license": "PROPRIETARY"},
        "Valid length clean prose text that belongs to a closed proprietary archive.",
    )
    assert not ok2 and reason2 == "LICENSE_REJECTED:PROPRIETARY"

    ok3, reason3, prov = stage1_provenance_firewall(
        {"license": "CC-BY-4.0", "_source_corpus": "unit"},
        "Clean technical prose describing orthogonal matrix transforms and checksums.",
    )
    assert ok3 and reason3 == "OK" and prov["spdx_license"] == "CC-BY-4.0"

    ok4, reason4, _ = stage1_provenance_firewall(
        {"license": "MIT", "collection_mode": "COVERT_TRACKING"},
        "Disallowed covert surveillance metadata record that must be blocked fail-closed.",
    )
    assert not ok4 and reason4 == "PRIVACY_ACT_GUARDRAIL_REJECTED:COVERT_TRACKING"


def test_stage5_subjective_lens_slop_scoring() -> None:
    slop = (
        "In today's fast-paced world, it's important to note that we delve into "
        "game-changing frameworks to seamlessly unlock the full power of data."
    )
    clean = (
        "Birkhoff Sinkhorn projection bounds residual layer spectral norms to unity "
        "across sixty four blocks with marginal error below one trillionth."
    )
    m_slop = score_entropy_and_difficulty(slop, word_tokens(slop), oracle_verified=False)
    m_clean = score_entropy_and_difficulty(clean, word_tokens(clean), oracle_verified=True)
    assert m_slop["articulate_slop_hits"] >= 4
    assert m_clean["articulate_slop_hits"] == 0
    assert m_clean["salience_score"] > m_slop["salience_score"]


def test_stage2_three_tier_dedup_exact_simhash_and_ast() -> None:
    dd = ThreeTierDeduplicator(max_hamming=3)
    base = (
        "Online softmax computes running max and log normalizer in one streaming pass "
        "over wide dynamic range logits without overflow."
    )
    near = (
        "Online softmax computes running max and log normalizer in one streaming pass "
        "over wide dynamic range logits without instability."
    )
    assert dd.check_and_add(base, word_tokens(base), "") == (True, "OK")
    assert dd.check_and_add(base, word_tokens(base), "") == (False, "EXACT_SHA256_DUPLICATE")
    assert dd.check_and_add(near, word_tokens(near), "") == (False, "NEAR_DUPLICATE_SIMHASH")

    code_a = "def calc_sum(alpha, beta):\n    total = alpha + beta\n    return total * 2\n"
    code_b = "def other_fn(x_val, y_val):\n    acc = x_val + y_val\n    return acc * 2\n"
    assert normalized_ast_hash(code_a) == normalized_ast_hash(code_b)
    assert dd.check_and_add("first python kernel text", word_tokens("first python kernel text"), code_a) == (True, "OK")
    assert dd.check_and_add("distinct description text", word_tokens("distinct description text"), code_b) == (
        False,
        "AST_STRUCTURAL_DUPLICATE",
    )


def test_stage3_holdout_decontamination_firewall() -> None:
    holdout = [
        {
            "id": "ho-1",
            "prompt": "Compute exact Birkhoff Sinkhorn projection for a four by four non separable log matrix.",
            "reference_code": "def sinkhorn_step(mat):\n    return [row for row in mat]\n",
        }
    ]
    dc = HoldoutDecontaminator(holdout)
    contaminated = "Paraphrase: Compute exact Birkhoff Sinkhorn projection for a four by four non separable log matrix."
    ok, reason = dc.is_clean(word_tokens(contaminated), "")
    assert not ok and reason.startswith("HOLDOUT_CONTAMINATION")

    clean = "Independent training item covering acoustic wave propagation in shallow coastal basins."
    assert dc.is_clean(word_tokens(clean), "") == (True, "OK")


def test_stage4_oracle_synthesis_and_planted_fault_rejection() -> None:
    rows = synthesize_oracle_verified_rows(count_f64=2, include_buildlang=True)
    assert len(rows) == 3

    def _mock_typecheck(src: str) -> bool:
        return "-> f64" in src and "-> bool" not in src

    for row in rows:
        ok, reason = validate_oracle_candidate(row, buildc_runner=_mock_typecheck)
        assert ok and reason == "OK", f"oracle row {row['id']} failed: {reason}"

    if shutil.which("buildc"):
        bld_row = rows[-1]
        ok_live, reason_live = validate_oracle_candidate(bld_row)
        assert ok_live and reason_live == "OK"

    leaky_trap = {"id": "leaky-1", "oracle_kind": "leaky_regex_trap", "target": "PASS"}
    ok_t, reason_t = validate_oracle_candidate(leaky_trap)
    assert not ok_t and reason_t == "GRADER_SANITIZER_LEAKY"


def test_full_pipeline_nine_of_nine_planted_traps_and_merkle_seal(tmp_path: Path) -> None:
    inp = tmp_path / "sample.jsonl"
    ho = tmp_path / "holdout.jsonl"
    out = tmp_path / "out"

    with inp.open("w", encoding="utf-8") as fh:
        for i in range(25):
            fh.write(
                json.dumps({
                    "id": f"row-{i}",
                    "license": "MIT",
                    "domain": "physics" if i % 2 == 0 else "compilers",
                    "text": (
                        f"Unique clean research paragraph number {i} discussing spectral norm bounds "
                        f"and lattice verification token_{i * 17}."
                    ),
                })
                + "\n"
            )
    with ho.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps({
                "id": "ho-0",
                "prompt": (
                    "Exact sealed evaluation prompt requiring twenty three distinct tokens "
                    "for thirteen gram holdout verification test."
                ),
            })
            + "\n"
        )

    card = run_data_forge(
        [(inp, "unit_sample", None)],
        ho,
        out,
        run_oracle_synthesis=True,
        inject_planted_traps=True,
        include_buildlang=False,
    )
    assert card["stats"]["planted_traps_caught"] == "9/9"
    assert card["stats"]["sfts_retrieval_trace_rows"] == len(BUILTIN_SFTS_RECORDS)
    assert card["parquet_emitted"] == (importlib.util.find_spec("pyarrow") is not None)
    ok, verdict = verify_sealed_dataset(out / "forged_dataset.jsonl.gz", out / "merkle_proof_bundle.json")
    assert ok and verdict == "MATCH"

    with gzip.open(out / "rejected_audit_log.jsonl.gz", "rt", encoding="utf-8") as gz:
        rej_traps = {json.loads(ln)["trap_id"] for ln in gz if json.loads(ln).get("trap_id")}
    assert len(rej_traps) == 8

    # Verify CLI entrypoint round-trip with --no-synth
    cli_out = tmp_path / "cli_out"
    assert main(["--out-dir", str(cli_out), "--input", f"{inp}::cli_sample::5", "--no-synth"]) == 0
    assert (cli_out / "dataset_card.json").is_file()


def test_pluggable_medical_hipaa_and_scientific_physics_adapters() -> None:
    ok_m, r_m, meta_m = run_domain_adapter(
        {
            "domain": "medical_clinical",
            "heart_rate_bpm": 72.0,
            "spo2_pct": 98.5,
            "icd10_code": "I10",
            "loinc_code": "8867-4",
            "patient_group_token": "anon-cohort-p42",
        },
        "De-identified adult cohort summary from year 2024 with normal sinus rhythm.",
    )
    assert ok_m and r_m == "OK" and meta_m["hipaa_safe_harbor_checked"] is True
    assert meta_m["patient_split"] in ("train", "eval")
    assert len({assign_patient_level_split("anon-cohort-p42") for _ in range(10)}) == 1

    ok_mrn, r_mrn, _ = run_domain_adapter({"domain": "medical_clinical"}, "Chart MRN-994821 admitted for observation.")
    assert not ok_mrn and r_mrn == "HIPAA_SAFE_HARBOR_VIOLATION:mrn"

    ok_dt, r_dt, _ = run_domain_adapter({"domain": "medical_clinical"}, "Encounter date 2025-04-17 outpatient visit.")
    assert not ok_dt and r_dt == "HIPAA_SAFE_HARBOR_VIOLATION:dob_or_exact_iso_date"

    ok_zip, r_zip, _ = run_domain_adapter({"domain": "medical_clinical"}, "Resident of ZIP 03608 low-population tract.")
    assert not ok_zip and r_zip == "HIPAA_SAFE_HARBOR_VIOLATION:restricted_zip3_036"

    ok_spo2, r_spo2, _ = run_domain_adapter(
        {"domain": "medical_clinical", "spo2_pct": 142.0},
        "Pulse oximetry reading from year 2025 cohort.",
    )
    assert not ok_spo2 and r_spo2.startswith("MEDICAL_RANGE_VIOLATION:spo2_pct")

    ok_p, r_p, meta_p = run_domain_adapter(
        {
            "domain": "scientific_physics",
            "si_lhs_units": ["N"],
            "si_rhs_units": ["kg", "m/s^2"],
            "conservation_in": 100.0,
            "conservation_out": 99.9999995,
            "conservation_tol": 1e-6,
        },
        "Verified Newtonian momentum balance across closed control volume.",
    )
    assert ok_p and r_p == "OK" and meta_p["si_physics_checked"] is True

    ok_dim, r_dim, _ = run_domain_adapter(
        {"domain": "scientific_physics", "si_lhs_units": ["J"], "si_rhs_units": ["N"]},
        "Broken dimensional balance equating energy to force.",
    )
    assert not ok_dim and r_dim.startswith("SI_DIMENSIONAL_MISMATCH")

    ok_cons, r_cons, _ = run_domain_adapter(
        {"domain": "scientific_physics", "conservation_in": 100.0, "conservation_out": 85.0, "conservation_tol": 1e-3},
        "Broken mass balance losing fifteen percent across boundary.",
    )
    assert not ok_cons and r_cons.startswith("CONSERVATION_RESIDUAL_VIOLATION")


def test_search_from_the_start_tsv_and_patient_bleed_guard(tmp_path: Path) -> None:
    tsv = tmp_path / "FORMULAS.tsv"
    header = "\t".join([f"c{i}" for i in range(15)])
    row1 = "\t".join([
        "F-101", "numerical", "harmonic_mean", "H = n / sum(1 / x_i)",
        "Exact positive-domain harmonic mean", "", "", "", "", "", "", "rel_err<=1e-12", "", "", "VERIFIED",
    ])
    row2 = "\t".join([
        "F-102", "draft", "unverified_stub", "y = x + 1 + 2 + 3",
        "Draft entry must be ignored", "", "", "", "", "", "", "none", "", "", "PENDING",
    ])
    tsv.write_text("\n".join([header, row1, row2]) + "\n", encoding="utf-8")

    sfts_rows = synthesize_search_from_the_start_rows(formulas_tsv_path=tsv, limit=10)
    assert len(sfts_rows) == 1
    assert sfts_rows[0]["expected_source_id"] == "F-101"
    for row in sfts_rows:
        assert validate_oracle_candidate(row) == (True, "OK")

    pids = [f"pt-{i:04d}" for i in range(50)]
    tr = [p for p in pids if assign_patient_level_split(p) == "train"]
    ev = [p for p in pids if assign_patient_level_split(p) == "eval"]
    assert verify_zero_patient_bleed(tr, ev) == (True, [])
    ok_b, leaked = verify_zero_patient_bleed(tr, ev + [tr[0]])
    assert not ok_b and leaked == [tr[0]]


def test_data_forge_module_line_budgets_and_hygiene() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    files = sorted((repo_root / "harness" / "data_forge").glob("*.py")) + [Path(__file__).resolve()]
    local_path_re = re.compile(r"[A-Za-z]:\\(?:dev|Users)\\")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 300, f"{path.name} exceeds 300-line gate"
        assert "\u2014" not in text, f"{path.name} contains a literal em dash"
        assert not local_path_re.search(text), f"{path.name} contains a hardcoded local path"
