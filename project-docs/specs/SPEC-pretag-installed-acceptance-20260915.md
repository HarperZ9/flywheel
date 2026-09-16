# Spec: Pre-tag Windows installed acceptance

## Objective

Add a manual CI path that can prove a source-bound Windows installer candidate on a clean ephemeral runner before a `v*` release tag exists. The run must rebuild from an exact operator-selected commit, record the bytes it produced, install those same bytes per-user in the same runner, and run the existing installed acceptance harness against the installed tree.

## Requirements

- [x] The workflow is `workflow_dispatch` only, uses `windows-latest`, and grants only `contents: read`.
- [x] The dispatch input is an exact 40-hex commit passed through an environment variable and validated before any Git checkout command uses it.
- [x] `GITHUB_SHA` must exactly match the accepted commit before helper checkout/build starts; the workflow dispatch ref is the candidate source.
- [x] The workflow checks out an admissible commit from the canonical repository branch history, then verifies `HEAD` equals that commit.
- [x] The candidate is rebuilt in CI; the workflow records its own installer, app, engine, and payload hashes and does not claim bit reproducibility with a local installer.
- [x] The runner fails closed if any Flywheel uninstall registry entry or standard Flywheel install path already exists before install.
- [x] Before build, the checked-out source, untracked files, and submodule state must be clean. After build and acceptance, tracked files and submodule checkout state must remain unchanged; generated outputs are limited to the build artifact locations uploaded by the workflow.
- [x] The installer runs `/CURRENTUSER /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` through a hidden, waited `Start-Process`, and nonzero exit is fatal.
- [x] Registry `InstallLocation` must exist and normalize to the requested per-user install root; the requested root is passed to acceptance.
- [x] The flow reuses the existing pinned Studio runtime staging, PyInstaller freeze, frozen gateway smoke, installer build, payload manifest producer, and installed acceptance wrapper.
- [x] Full mode runs with `-StartEngine`; inspect mode runs with `-InspectImport`; both pass exact source, version, manifest, app hash, and engine hash.
- [x] Uploaded artifacts are limited to sanitized receipts, hashes, manifest, and summary; no broad temp directories, user profile state, credentials, tags, releases, or provider calls.
- [x] The documentation states that this does not prove native UI/device/signing/provider acceptance, and does not accept any older local installer.

## Technical Approach

Create `.github/workflows/windows-installed-acceptance.yml` as a manual, read-only workflow that installs Flutter and Python, then delegates the sensitive PowerShell orchestration to `desktop/tool/run_ci_installed_acceptance.ps1`. The helper validates `ACCEPTANCE_COMMIT`, requires `GITHUB_SHA` to match it, fetches branch history, rejects commits unreachable from `origin/*`, checks out the exact commit, builds the candidate, records hashes, checks runner cleanliness, installs per-user, and runs full plus inspect installed acceptance. Static and behavioral tests guard the workflow and helper against tag requirements, input interpolation, unchecked installer exits, broad artifact upload, local-installer hash assumptions, release/publish side effects, missing registry properties, nested argument arrays, and dirty source gates.

## Files to Modify

- `.github/workflows/windows-installed-acceptance.yml` — new manual workflow.
- `desktop/tool/run_ci_installed_acceptance.ps1` — new CI-only orchestration helper.
- `tests/test_windows_installed_acceptance_workflow.py` — new static workflow/helper/spec regression tests.
- `project-docs/specs/SPEC-pretag-installed-acceptance-20260915.md` — this spec.

## Success Criteria

- [x] `python -m pytest tests/test_windows_installed_acceptance_workflow.py -q` passes after red/green verification.
- [x] All new files are under the 300-line gate, and repository-wide `python scripts/check_file_gate.py` passes with no new or grown violations.
- [x] The helper parses as PowerShell without executing the installer locally.
- [x] No existing workflow, release workflow, tag publishing path, or desktop golden file is edited.

## Status: IMPLEMENTED

