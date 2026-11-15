# eval_attempt — wedge #7

A **single benchmark attempt → proof packet**. Harvested from dogfood pass
0085/0096 (`agi_eval_attempt_lab` / `EvalAttemptProofPacket`). For ARC-AGI-style
per-task evaluation where the meaningful unit is one attempt, not an aggregate
metric (that is `model_eval`'s job).

Binds:
- `benchmark` — benchmark ref, task id, and the **authority receipt** (who defines correctness).
- `attempt` — attempt id, prompt/model refs, **tool-use records**, and a **replay ref**.
- `result` — `correct` / `incorrect` / `abstained` / `error` (+ optional score).
- `boundaries` — `had_ground_truth` / `had_internet` / `had_tools`.

**Honesty gate (contamination):** a `correct` outcome with `had_ground_truth=true`
is contamination, **not a pass** — the verdict falls to `UNVERIFIABLE` and the
packet is rejected outright. `correct` + clean → `MATCH`; `incorrect` → `DRIFT`;
`abstained` / `error` → `UNVERIFIABLE`.

## Use

```bash
telos-proof eval-attempt --input attempt.json --claim "..." --scope "..." --out ./artifacts
# or: python -m proof_surface.eval_attempt --input attempt.json ...
```

`attempt.json`: `{sources, benchmark, attempt, result, boundaries[, uncertainty]}`.
Emits `packet.json`, `report.md`, crucible `thesis`/`measurements`, an optional
peer assessment, and a content-addressed `bundle.json`.
