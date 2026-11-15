# Contributing

behavior-transform.io is private-line IO boundary infrastructure. Contributions
must improve clarity, verification, safety boundaries, or developer ergonomics
without adding live credential handling, raw secret export, or hidden external
side effects.

## Workflow

1. Start from the relevant spec or create one under `project-docs/specs/` for
   multi-file changes.
2. Add or update a targeted regression test before changing behavior.
3. Keep changes local-first, receipt-backed, and mode-aware.
4. Run the smallest meaningful verification slice.
5. Keep README, `USAGE.md`, `CHANGELOG.md`, and doctor checks aligned with any
   operator-facing change.

## Verification

For delivery-surface changes, run:

```bash
python -B -m pytest tests/test_behavior_delivery_contract.py -q
python -m public_surface_sweeper . --workspace --json
```

For flagship or IO boundary changes, include:

```bash
python -B -m pytest tests/test_behavior_flagship.py tests/test_behavior_delivery_contract.py -q
python -B tools/behavior_flagship.py doctor --json
```

## Boundaries

- Do not commit `.env` files, tokens, credentials, or private evidence.
- Do not export raw prompts, private file contents, secret values, or full
  model-boundary payloads.
- Prefer counts, hashes, verdicts, redacted references, timestamps, mode names,
  and action identity fields for outward-facing evidence.
- Do not add network behavior or external writes to status, doctor, or demo
  surfaces.
