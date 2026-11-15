# repo-proof-index v0.2.0

## Release Type

Minor release for proof-status boundary clarity, strict JSON reader hardening,
and current public package behavior since v0.1.1.

## What Changed

- Keeps `status` backward-compatible as the producer-reported value while adding
  `producer_status` and `verification_state` so a self-declared green proof row
  is not presented as independently verified by Repo Proof Index.
- These proof-surface and research-claim packets remain `not_verified` in this
  index; assess a separate tool's verification result on its own evidence.
- Rejects ambiguous or unsafe JSON inputs before indexing or validation:
  duplicate keys, `NaN`, `Infinity`, overflowing floats such as `1e999`, files
  over 1,048,576 bytes, and JSON nesting deeper than 200 levels.
- Adds organ-row provenance, proof-surface forwarding/conformance updates,
  public docs/examples/art, and publishing workflow updates accumulated after
  v0.1.1.

## Verification

Use the packaging tooling below before running the package checks. This release
procedure was verified with Twine 7.0.0. In local release prep, Twine 6.2.0
failed on Core Metadata 2.5 artifacts emitted by Hatchling 1.32.0.

- `python -m pip install --upgrade build "twine==7.0.0"`
- `python -m pytest -q`
- `python scripts/check_proof_surface_conformance.py`
- `python scripts/export_proof_surface_contract.py --out .release-check/proof-surface-contract-v0.1`
- `python scripts/score_proof_surface_research.py`
- `python -m json.tool schemas/proof-surface-packet.schema.json`
- `python -m build`
- `python -m twine check dist/*`
- `git diff --check`

## Artifacts

- `repo_proof_index-0.2.0-py3-none-any.whl`
- `repo_proof_index-0.2.0.tar.gz`

## Publishing Notes

GitHub Release artifacts are in scope. PyPI publication remains separate and
requires registry credentials.
