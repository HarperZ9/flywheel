# Proof-Carrying Data Forge

`harness.data_forge` is a six-stage fail-closed dataset synthesis, cleaning, and
sealing pipeline built directly on Flywheel's stdlib primitives (`harness.merkle`
and `harness.verifier_sanitizer`). Every surviving row passes provenance,
deduplication, decontamination, oracle validation, and salience scoring before
being sealed into an RFC 6962 Merkle proof bundle that anyone can re-verify
offline.

## Pipeline stages

1. **Provenance and domain firewall (`adapters.py`)**: blocks secrets, PII,
   disallowed collection modes (`DISALLOWED_COLLECTION_MODES`), and unapproved
   licenses. Runs pluggable domain adapters:
   - `MedicalHipaaSafeHarborAdapter` checks HIPAA Safe Harbor identifiers
     (patient names, MRNs, exact dates, phone numbers, IPv4 addresses, restricted
     3-digit ZIP prefixes), physiological bounds, ICD-10 and LOINC formats, and
     assigns deterministic zero-bleed patient-level train/eval splits.
   - `ScientificPhysicsSensorAdapter` validates SI dimensional balance across
     unit vectors and checks conservation-law residuals against a tolerance.
2. **Three-tier deduplication (`dedup_and_holdout.py`)**: removes exact SHA-256
   matches, near-duplicates via 64-bit Charikar SimHash and 8-permutation MinHash
   LSH bands, and alpha-renamed Python AST or BuildLang token-skeleton clones.
3. **Zero-leak holdout decontamination (`dedup_and_holdout.py`)**: indexes sealed
   evaluation holdouts and blocks exact, 13-gram, multi-8-gram, and normalized
   AST overlap.
4. **Execution-oracle synthesis and grader sanitizer (`oracles.py`)**: verifies
   oracle-bearing candidates (`f64_exact`, `buildlang_check`,
   `search_trace_grounded`) against deterministic external checks and audits each
   grader with `harness.verifier_sanitizer.audit_verifier_planted_wrong` so
   trivial or leaky graders fail closed. Includes the Search-From-The-Start
   (`arXiv:2611.26809`) retrieval-trace synthesizer over built-in verified
   kernels or a supplied TSV formula catalog.
5. **Dual-lens salience and difficulty scoring (`scoring_and_seal.py`)**:
   combines Shannon token entropy, zlib compressibility, vocabulary uniqueness,
   oracle verification bonus, and an Articulate-aligned boilerplate slop penalty
   into a bounded salience score and difficulty tier (`tier_1_foundation`,
   `tier_2_applied`, `tier_3_frontier`).
6. **Proof-carrying seal (`scoring_and_seal.py`)**: writes
   `forged_dataset.jsonl.gz`, `rejected_audit_log.jsonl.gz`,
   `merkle_proof_bundle.json`, `dataset_card.json`, and optional zstd-compressed
   `forged_dataset.parquet` when `pyarrow` is installed. `verify_sealed_dataset`
   recomputes the RFC 6962 root and sample inclusion proofs offline.

## Quick start

Run the pipeline from the command line with the nine built-in planted dirty-data
controls enabled:

```bash
python -m harness.data_forge \
  --input path/to/corpus.jsonl::corpus_v1 \
  --holdout path/to/holdout.jsonl \
  --out-dir out/data_forge \
  --inject-traps
```

Or invoke it from Python:

```python
from pathlib import Path
from harness.data_forge import run_data_forge, verify_sealed_dataset

card = run_data_forge(
    input_specs=[(Path("corpus.jsonl"), "corpus_v1", None)],
    holdout_path=Path("holdout.jsonl"),
    out_dir=Path("out/data_forge"),
    run_oracle_synthesis=True,
    inject_planted_traps=True,
)
ok, verdict = verify_sealed_dataset(
    Path("out/data_forge/forged_dataset.jsonl.gz"),
    Path("out/data_forge/merkle_proof_bundle.json"),
)
assert ok and verdict == "MATCH"
```

## Planted dirty-data controls

With `inject_planted_traps=True`, the pipeline self-tests nine fail-closed
controls on every run and records each rejection in `dataset_card.json` and
`rejected_audit_log.jsonl.gz`:

| Trap ID | Stage | Control verified |
| --- | --- | --- |
| `trap1_secret_key` | Stage 1 | API key and email PII rejection |
| `trap2_near_duplicate` | Stage 2 | SimHash and MinHash LSH near-duplicate rejection |
| `trap3_holdout_contamination` | Stage 3 | 13-gram holdout overlap rejection |
| `trap4_leaky_unverified_grader` | Stage 4 | Planted-wrong grader sanitizer rejection |
| `trap5_malformed_utf8_json` | Stage 0 | Invalid UTF-8 and malformed JSON isolation |
| `trap6_post_seal_merkle_tamper` | Stage 6 | Post-seal byte mutation detection via RFC 6962 root |
| `trap7_hipaa_phi_leak` | Stage 1 | HIPAA Safe Harbor PHI and restricted ZIP3 rejection |
| `trap8_patient_split_bleed` | Stage 3 | Cross-split patient ID bleed detection |
| `trap9_si_dimensional_violation` | Stage 1 | SI dimensional mismatch and conservation residual rejection |

## Zero-dependency guarantee

`harness.data_forge` uses only the Python standard library on import. Optional
enhancements activate automatically when present on the host: `pyarrow` writes a
zstd-compressed Parquet companion table alongside `forged_dataset.jsonl.gz`, and
`buildc` enables live BuildLang type-check oracle synthesis.
