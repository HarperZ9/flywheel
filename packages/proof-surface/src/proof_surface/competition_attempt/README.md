# competition-attempt -- wedge #11

A **competition/judge attempt -> proof packet**. Harvested from the SAIR
competition dogfood cluster (passes 0136 / 0137 / 0138 / 0139).

A single competition attempt binds the `challenge` to a source-pinned
`judge_repo` observation, discloses its hosted-model usage, records how the
answer was extracted, and carries a closed `certificate_layers` ladder whose
overall verdict may only cite layers that actually EXECUTED.

## The load-bearing gates

`_gates.py` and `packet.py` enforce four rules. A verifier that cannot fail on
a known-bad input is not a verifier, so each gate ships a negative fixture that
must reject.

1. **Source-pinned judge.** The judge repository is observed, never assumed:
   `judge_repo` requires a `repo_ref`, a 40-hex `head_sha`, an
   `observed_files` count greater than zero, and a 64-hex `files_digest`. A
   forged or wrong-shaped commit sha is rejected.
2. **Hermeticity disclosure** (verbatim from the eval-attempt rule). When the
   attempt discloses `external_model_calls` or a `provider_receipt_ref`, the
   claim must be evidence-consistent: a hermetic claim (0 calls) citing a
   provider receipt is a contradiction; a nonzero count without a receipt is a
   claim with no evidence surface; a receipt without a disclosed count is
   undisclosed external usage. An undisclosed attempt (neither field) stays
   valid.
3. **Injection-safe extraction.** `answer_extraction.method` is one of `boxed`,
   `last-labeled`, or `bare-last-line`. A non-boxed method must record
   `injection_checked == true` (prompt instructions must never be parsed as
   answers), and an unrendered template marker (`{{` or `}}`) in the extracted
   reference is rejected.
4. **No tier inflation.** `certificate_layers` is a closed, duplicate-free
   ladder (`informal-model-output`, `machine-checked-proof`,
   `finite-counterexample`, `judge-verdict`). Every layer is either `EXECUTED`
   or `UNAVAILABLE_FENCED`; a fenced layer must cite the `probe_evidence` that
   proved the fence and may not carry a pass/fail result. The overall verdict
   may only cite layers that EXECUTED, and `MATCH` is only derivable from an
   EXECUTED, passing `judge-verdict` layer. A passing verdict with zero
   executed layers is impossible by construction.

The verdict is `MATCH` iff the `judge-verdict` layer EXECUTED and passed,
`DRIFT` if it EXECUTED and failed, `UNVERIFIABLE` otherwise (a fenced or absent
judge).

## Use

```bash
telos-proof competition-attempt --input claim.json --claim "..." --scope "..." --out ./artifacts
# or: python -m proof_surface.competition_attempt --input claim.json ...
```

`claim.json`: `{sources, challenge, attempt, answer_extraction,
certificate_layers[, uncertainty]}`. Emits `packet.json`, `report.md`, crucible
`thesis`/`measurements`, an optional peer assessment, and a content-addressed
`bundle.json`.
