# behavior-transform.io Agent Instructions

`behavior-transform.io` is the private-line IO boundary calibration layer for
Project Telos. It keeps local workstation IO explicit, mode-aware, and
receipt-friendly without exporting raw prompts, private file contents, secret
values, or model-boundary payloads.

## Before Editing

Read:

- `README.md` for the product surface
- `USAGE.md` for operator and developer commands
- `docs/INTEGRATION_CONTRACT.md` for the IO receipt and privacy contract
- `CLAUDE.md` for local project constraints
- `tools/behavior_flagship.py` for status, doctor, and demo envelopes

## Safe Default Work

Prefer changes that improve:

- docs and developer onboarding
- doctor checks and receipt fidelity
- installable CLI surfaces
- wrapper importability and deterministic tests
- explicit redaction and local-only boundaries

Do not add live credential handling, raw secret export, or external side
effects to the flagship doctor/demo surfaces.

## Verification

```powershell
python -B -m unittest tests.test_behavior_flagship -v
python -B tools\behavior_flagship.py doctor --json
```

Use `python -B` for local checks when avoiding cache churn is useful.
