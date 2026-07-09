# Model-card claim grounding evidence flow - 2026-07-09

Status: implemented, not validated, not executed.

## Mechanism

`harness.model-card-claim-table/v1` is now part of the closed-loop evidence flow. It is a metadata-only artifact that records candidate model leads, required model-card fields, source status, unresolved fields, and non-execution guards before embodied realtime benchmark claims are reported.

## Evidence surfaces

- `scripts/run_model_card_claim_table.py` emits the claim table.
- `harness.cmd model-card-claims` exposes the command through the executable harness surface.
- `scripts/run_closed_loop_benchmark_seed.py` includes `model_card_claim_table` as a metadata-only preflight step.
- `scripts/run_benchmark_execution_matrix.py` includes the claim table in dry-tier planning and in later coverage artifact inputs.
- `scripts/run_benchmark_profile_coverage.py` recognizes `harness.model-card-claim-table/v1` as planned-only evidence for `embodied_realtime_multimodal_pressure`.
- `scripts/run_closed_loop_outcome_report.py` surfaces `model_card_claim_signals` so unresolved model-card claims remain visible in the final outcome.

## Non-claims

- This does not verify any model card.
- This does not browse the web.
- This does not call providers or local endpoints.
- This does not download, hash, or inspect model weights.
- This does not convert relayed Discord/community claims into benchmark facts.

## Next executable step

Run the targeted validation slice only after approval, then generate `model_card_claim_table.json` as part of the dry metadata preflight bundle.
