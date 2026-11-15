# EMET release checklist

A release is reproducible from the public surface. Every gate below must be green
before a tag is cut, and the published artifacts must re-derive after upload.

## Pre-flight gates (all must pass)

```powershell
# 1. The implementations agree on the vector suite they claim.
python conformance/run.py membrane.py

rustc -O impl/rust/emet.rs -o "$env:TEMP\emet-rust.exe"
$env:EMET_SKIP_CAPABILITIES='rebind,eval-receipt'
python conformance/run.py "$env:TEMP\emet-rust.exe"
Remove-Item Env:\EMET_SKIP_CAPABILITIES

node --test impl/js/test_receipt.js
$env:EMET_SKIP_CAPABILITIES='rebind,eval-receipt'
python conformance/run.py impl/js/emet.js
Remove-Item Env:\EMET_SKIP_CAPABILITIES

go build -o "$env:TEMP\emet-go.exe" impl/go/emet.go
$env:EMET_SKIP_CAPABILITIES='receipt,rebind,eval-receipt'
python conformance/run.py "$env:TEMP\emet-go.exe"
Remove-Item Env:\EMET_SKIP_CAPABILITIES

# 2. The Python behavior + delivery suite.
python -m pytest -q
python test_reporter_flywheel.py
python test_witness_receipt_cross_lang.py

# 3. Identity + hygiene.
python membrane.py selftest
git diff --check
```

Expected conformance counts: Python reference 48/48; Rust 40/40 with
`rebind,eval-receipt` skipped; Node.js 40/40 with `rebind,eval-receipt` skipped;
Go 35/35 with `receipt,rebind,eval-receipt` skipped. The installed-package CI job
must also pass 48/48 against the installed `emet` console script.

Confirm: no secrets or `.env` in the tree; runtime state (`anchors.json`,
`*_log.jsonl`, `*.refused`) and build artifacts (`dist/`, `impl/**/emet*`) are
gitignored; `README.md`, `USAGE.md`, `SECURITY.md`, and `CHANGELOG.md` state the
package version honestly; the independent, different-author re-derivability bar
(SPEC section 12) is still described as open.

## Version bump surfaces

For a package-only 1.x release that does not change the frozen normative spec,
bump in lockstep: `pyproject.toml` `version`, `emet/__init__.py` `__version__`,
`emet/report.py` `EMET_VERSION`, README status text, the illustrative
`emet_version` envelope in `USAGE.md`, `SECURITY.md` support wording, and
`CHANGELOG.md`.

Do not bump `SPEC.md` spec version, `conformance/vectors.json` `spec_version`,
`COVERAGE.json` `spec_version`, adapter `SPEC_VERSION` constants, or the Rust
crate version unless the release intentionally changes those surfaces.

## Tag, push, release

```powershell
git tag -a vX.Y.Z -m "EMET X.Y.Z - <release summary>"
git push origin main
git push origin vX.Y.Z

# GitHub release from the tag. Use the matching CHANGELOG section as notes.
gh release create vX.Y.Z --title "EMET X.Y.Z" --notes-file release-notes.md
```

Only tag the exact commit whose source gates and GitHub push/PR checks passed.

## PyPI (emet)

The repository publishes through GitHub Actions OIDC Trusted Publishing in
`.github/workflows/release.yml` when a GitHub release is published. Do not run a
manual API-token upload for the normal release path.

Local artifact checks before publishing use a fresh output directory so older
artifacts are preserved and not mistaken for the current candidate:

```powershell
$stamp = Get-Date -Format 'yyyyMMddTHHmmssZ'
$artifactDir = Join-Path $PWD "dist-$stamp"
python -m build --outdir $artifactDir
$artifactPaths = (Get-ChildItem -LiteralPath $artifactDir -File).FullName
python -m twine check $artifactPaths
Get-FileHash $artifactPaths -Algorithm SHA256
```

Those local hashes identify the pre-publish candidate that was checked on the
operator's machine. The GitHub release workflow rebuilds the package artifacts;
only claim byte equality with local artifacts after comparing the actual workflow
outputs or PyPI files and recording the matching hashes.

## Post-publish re-derivation (the release verifies itself)

```powershell
$stamp = Get-Date -Format 'yyyyMMddTHHmmssZ'
$verifyDir = Join-Path $env:TEMP "emet-verify-$stamp"
python -m venv $verifyDir
$verifyPy = Join-Path $verifyDir 'Scripts\python.exe'
$verifyEmet = Join-Path $verifyDir 'Scripts\emet.exe'
$conformanceRunner = (Resolve-Path 'conformance/run.py').Path
& $verifyPy -m pip install --upgrade pip

Push-Location $env:TEMP
try {
  & $verifyPy -m pip install -I --no-deps emet==X.Y.Z
  @'
import importlib.metadata as md
import pathlib
import sys

import emet
import emet.report as report

emet_file = pathlib.Path(emet.__file__).resolve()
sys_prefix = pathlib.Path(sys.prefix).resolve()
assert md.version("emet") == "X.Y.Z"
assert emet.__version__ == "X.Y.Z"
assert report.SPEC_VERSION == "1.0.0"
assert emet_file == sys_prefix or sys_prefix in emet_file.parents
print(emet_file)
'@ | & $verifyPy -I -
  & $verifyEmet selftest
  & $verifyPy $conformanceRunner $verifyEmet
} finally {
  Pop-Location
}
```

After upload, confirm PyPI shows both sdist and wheel for the new version, record
their actual published hashes, and verify PyPI provenance points to the release
tag and `release.yml` workflow run. Confirm the installed package imports from
the verification environment, reports `emet.__version__ == "X.Y.Z"`, keeps
`SPEC_VERSION == "1.0.0"` unless the normative spec changed, and passes the
installed console conformance check.

If the published artifact does not re-derive, the release is not done. EMET's only
credential is reproduction; a release that cannot be reproduced refutes itself.
