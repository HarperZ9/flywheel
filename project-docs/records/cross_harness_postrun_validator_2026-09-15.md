# Cross-harness post-run validator record — 2026-09-15

Setup receipt:

- Branch: `codex/postrun-comparison-validator-20260915`
- Base/head at setup: `b255cee18700338ae8bef122170ef472e71e25a7`
- Scope: post-run comparison validator, pre-run intent binding, CLI, and focused tests. No providers are run by the validator.

Usage:

```powershell
python scripts/run_cross_harness_postrun_comparison.py <run_root> --out postrun.json --markdown-out postrun.md
```

Exit codes:

- `0`: validator classified the supplied local run root as `completed_comparison`.
- `3`: validator found a gap, planned-only state, malformed evidence, or legacy unbound run shape.

Acceptance contract:

- A new focused run writes `intended-matrix.json` before attempt execution and binds that matrix hash into every attempt row, `run.json`, `comparison-input.json`, and `artifact-index.json`.
- The original comparison denominator is exactly agt-003, roles `codex_harness` and `flywheel_harness`, one or more declared integer repetitions, and the accepted role identities: `codex`/`codex_cli_json/v1` and `flywheel`/`flywheel_router/v1`, both requesting and reporting `gpt-5.3-codex-spark` in the intent matrix.
- The validator rejects missing intended cells, duplicate intended cells, duplicate observed cells, extra observed rows, malformed cell keys, incomplete declared repetition products, and local_14b substitution.
- The validator keeps oracle-fail rows with returned execution and verified receipts as eligible observed comparisons; unavailable, timeout, malformed, internal-error, unverifiable, receipt-drift, and missing rows remain gaps or bounded observations.
- Parity is checked within each task/repetition pair for prompt, input, runtime context, tool policy, schema, and task identity. Tool policy hash equality is declaration parity only; enforcement equivalence remains `not_verified` unless distinct hashes show `non_equivalent` declarations.
- Artifact receipts still bind local bytes. The validator separately rejects symlinks/junctions along submitted paths before resolution and checks oracle, metrics/resource, enforcement, receipt, run, scorecard, and index consistency.
- The source tree must be clean in run and scorecard metadata, and before/after source snapshot hashes must match for a completed comparison. Drifted or legacy unsealed data stays usable as bounded evidence but cannot become a controlled comparison.

This validator is benchmark infrastructure. It does not prove the original comparison already executed, does not rank output quality without execution evidence, and does not make SHA-256 values into independent authenticity guarantees.

## HOLD review fixes — 2026-09-15

The independent HOLD review identified three blockers. The red tests failed on all three before the fix and pass after the fix:

```powershell
python -m pytest tests/test_cross_harness_postrun.py::test_postrun_validator_rejects_declared_two_repetitions_with_one_rep_cells tests/test_cross_harness_postrun.py::test_postrun_validator_rejects_linked_run_root_before_resolve tests/test_cross_harness_postrun_intent.py::test_build_intended_matrix_rejects_boolean_repetitions -q
```

Fixed behavior:

- A symlink or junction passed as `run_root` is rejected before resolution with `linked_run_root`.
- A valid declared Cartesian denominator is reported from `task_ids x roles x repetitions`; a matrix declaring repetitions `[1, 2]` for the two accepted roles reports four intended attempts even if only rep-001 cells exist.
- Invalid declared dimensions are reported with `intended_denominator_unknown` / `unknown_invalid_declared_dimensions` rather than treating the cell list as the denominator.
- `build_intended_matrix(..., repetitions=True)` now raises `ValueError` instead of accepting `True` as `1`.

Freeze hashes after the HOLD fixes:

```text
62E1B14AE2A3A4D711CFEE73F672BF1ED0679511F7AC3661F18C846C357EBD3D  harness/cross_harness_postrun.py
5C80F55B7ACF7374F9F779C29DB58309DE39ABD003ADD59FF83212945CE10CD9  harness/cross_harness_postrun_checks.py
2992AFA693118A8866EC02E7B28BAA0F2AC8CBA49E922F03089F98A4B08AE37E  harness/cross_harness_postrun_paths.py
0AF5FFC06320A848BFE410561FFD30D3EB8042E078DD4EEC90A5FAB4938594AC  harness/cross_harness_postrun_intent.py
50BB4BC653765E6167433581E339E7D4A8012F3836EA0FD8F580F2D2F443F094  harness/cross_harness_executor.py
08E5AD0B6173F30B71B495D7E461CDD88A2F1BC81CFCD419E7E401CD00539FC3  harness/cross_harness_run_seal.py
1A08142FB7F23757773DFF3A54CC699F35E91B375F610C267CCDCB12C6D2C278  scripts/run_cross_harness_postrun_comparison.py
D983901E25080446084726CB45AF114E629E6183372C76A818F7691B558D0AB6  tests/test_cross_harness_postrun.py
00B76F642CD79374E8E0310CF569B9ED22455FDDD575393F06C4961D147D30B7  tests/test_cross_harness_postrun_intent.py
16F89125ED0C73D5A0784190A8CA02AFD8288C288B773E64FC402579B2272A6C  tests/cross_harness_postrun_support.py
```
