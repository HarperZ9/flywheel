# Studio runtime staging repair

## Objective
Make the Windows candidate build obtain and package the declared public Studio
runtime without developer paths or machine-dependent source bytes.

## Requirements
- [x] The workflow invokes the packaging CLI from a clean Python environment.
- [x] Git checkout preserves pinned source bytes despite global autocrlf settings.
- [x] Real public source pins stage successfully, retaining hash and license checks.
- [x] Required imports load in an isolated interpreter with only staged source roots.
- [x] Independent review covers the repaired candidate before integration.

## Approach and owned files
Use the package module entrypoint in `.github/workflows/desktop-release.yml`.
Set clone-local `core.autocrlf=false` in `scripts/studio_runtime_sources.py`.
Add subprocess and real Git checkout regressions in
`tests/test_studio_runtime_source_pins.py`. Preserve source hashes rather than
normalizing bytes after validation. Existing packaging and workflow tests remain.
Reconcile manifest hashes against the pinned Git blobs, recording prior CRLF-only
differences. Compute cross-package dependency closure, including the certificate
and composition modules. Add
`scripts/studio_runtime_imports.py` and its subprocess tests; run that check during
staging before allowing PyInstaller to consume the payload. Update the root
integration manifest generator's cross-package traversal and regression test.
Reject packaged manifest drift even when runtime file hashes still match.

## Acceptance and limits
Run the focused packaging tests and the actual public-pin staging command. Inspect
relocated runtime import closure before claiming the payload is usable. Successful
staging does not establish frozen gateway, installed desktop or release acceptance.

## Evidence and status
IMPLEMENTED, independent review returned GO for staging. Initial workflow execution failed with
ModuleNotFoundError. Hash pins mixed LF and CRLF working-tree bytes; reconciled
them to exact committed blobs. The initial staged closure could not import
Accountable Surface because cross-package dependencies were omitted.

Validation: 34 focused packaging/workflow tests passed. Actual staging fetched all
four pinned public commits, validated 81 source files and four license notices,
and loaded 14 entry modules in an isolated interpreter. Using that staged payload,
the root integration's bounded rendering action and gateway route checks passed.
The packaged-manifest false-success case failed before the equality repair and
passed afterward. These checks do not establish installed or released behavior.
