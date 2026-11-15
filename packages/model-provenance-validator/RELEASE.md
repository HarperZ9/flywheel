# model-provenance-validator v0.1.1

## Release Type

Patch release for current public package behavior and release-artifact
normalization.

## Verification

- `python -m pytest -q`
- `python -m json.tool src/model_provenance_validator/schema.json`
- `python -m json.tool examples/envelopes/release.provenance.json`
- `python -m build`
- `python -m twine check dist/*`
- `python -m model_provenance_validator examples/envelopes/release.provenance.json --proof-packet`
- `git diff --check`

## Artifacts

- `model_provenance_validator-0.1.1-py3-none-any.whl`
- `model_provenance_validator-0.1.1.tar.gz`

## Publishing Notes

GitHub Release artifacts are in scope. PyPI publication remains separate and
requires registry credentials.
