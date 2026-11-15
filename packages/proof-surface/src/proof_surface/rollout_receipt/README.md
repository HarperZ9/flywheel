# rollout_receipt — wedge #6

An **RL / post-training run → proof packet**. Harvested from
`telos/docs/research/rl-scaling-receipt-spine.md`: wrap post-training stacks
(Slime-like frameworks, custom labs) with durable evidence instead of cloning the
trainer.

The defining property is **separation of records** — reward score, verifier
verdict, admission policy, and promotion decision are never collapsed into one
another:

- `rollout` — rollout id, policy/checkpoint ref, verifier ref, reward digest, sandbox receipt, dataset-mutation ref.
- `reward` — the numeric score + model ref (kept apart from the verdict).
- `verifier` — `MATCH` / `DRIFT` / `UNVERIFIABLE` + evidence.
- `admission` — `allow` / `block` / `escalate` / `require_review` (a policy decision, not a verdict).
- `promotion` — **derived default-deny**: `promote` only when the verifier said `MATCH` **and** admission said `allow`; `reject` on `DRIFT` or `block`; `hold` otherwise. A hand-forged `promote` without that backing fails validation.

## Use

```bash
telos-proof rollout-receipt --input run.json --claim "..." --scope "..." --out ./artifacts
# or: python -m proof_surface.rollout_receipt --input run.json ...
```

`run.json`: `{sources, rollout, reward, verifier, admission[, uncertainty]}`.
Emits `packet.json`, `report.md`, crucible `thesis`/`measurements`, an optional
peer assessment, and a content-addressed `bundle.json`.
