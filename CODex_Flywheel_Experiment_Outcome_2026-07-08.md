# Codex vs Flywheel Benchmark Outcome

Date: 2026-07-08

## Scope
- Codex frontier harness: `gpt-5.3-codex-spark` via dry-run benchmark mode.
- Flywheel/local harness: live benchmark via `ollama` model `qwen2.5:7b`.
- Benchmarks executed: M7 easy set (`8` tasks) and hard set (`10` tasks).

## Execution notes
- Live frontier run for Codex (`--frontier` with provider calls) is not currently usable in this session due:
  - no OpenAI provider key configured for API mode, and
  - CLI plan mode (`codex.cmd exec`) not completing in this environment.
- Dry-run frontier runs are used for the Codex comparison.

## Outputs
- Live flywheel (easy): `artifacts_local_ollama_easy_full.json`
- Live flywheel (hard): `artifacts_local_ollama_hard_full.json`
- Codex dry-run harness (easy): `artifacts_codex_frontier_dry_easy_full.json`
- Codex dry-run harness (hard): `artifacts_codex_frontier_dry_hard_full.json`

## Results (pass rates)

| Benchmark | single_shot | no_search | flat_n | verified_inference | local_ollama | frontier_single_shot | frontier_codex-plan |
|---|---:|---:|---:|---:|---:|---:|---:|
| Codex dry-run (easy) | 1.00 | 0.875 | 1.00 | 1.00 | n/a | 1.00 | n/a |
| Codex dry-run (hard) | 1.00 | 1.00 | 1.00 | 1.00 | n/a | 1.00 | n/a |
| Flywheel live (ollama7b easy) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | n/a | n/a |
| Flywheel live (ollama7b hard) | 0.80 | 0.80 | 0.90 | 0.90 | 0.90 | n/a | n/a |
| Codex live artifact (historical) | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | n/a | 0.25 |

## Outcome
- Flywheel local harness shows a **+10 point lift** on hard: `verified_inference`/`flat_n` at `0.90` vs `single_shot` `0.80`.
- On easy, all tested local/flywheel arms are at ceiling (`1.00`), so no incremental lift signal.
- Front-end Codex dry-run is not a valid inference signal (stub mode) and tends to show parity (`1.00`) across all arms.
- Historical live codex-frontier artifact is inconsistent (`frontier_codex-plan=0.25`), but is not from this exact benchmark configuration.

## Commit/merge/push performed before this pass
- Commit: `c2c1778` (harness tooling integration + task curator/test edits)
- Fast-forward merge into `main` completed.
- Push to `origin` failed: SSH key missing (`no such identity: /c/Users/Zain/.ssh/id_ed25519`).
