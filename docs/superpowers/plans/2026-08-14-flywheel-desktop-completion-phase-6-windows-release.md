# Flywheel Desktop Completion Phase 6 Windows Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce one immutable, signed, per-user Windows candidate whose wheel and installer share one identity and whose installed behavior passes fail-closed acceptance on supported clean Windows systems.

**Architecture:** A single source-bound release identity feeds default-reject staging, legal/SBOM evidence, inner-binary and installer signing, and clean-VM installed acceptance. Publishing workflows can consume only the accepted immutable manifest, but Phase 6 neither publishes nor deploys anything.

**Tech Stack:** Python 3.11+ standard library, PowerShell 7, Flutter 3.44.6, Dart 3.6+, PyInstaller 6.21.0, Inno Setup 6, Authenticode/SignTool, CycloneDX/SPDX evidence, pytest, Flutter test, protected GitHub Actions environments.

**Spec:** `docs/superpowers/specs/2026-08-13-flywheel-desktop-completion-design.md`

## Global Constraints

- No learned model on the accept path.
- No receipt, no accept; denominators and `does_not_prove` are mandatory.
- No later phase may become an implementation prerequisite for an earlier phase.
- Python containment is an independent capability gate and does not reorder these phases.
- Flutter must not derive evidence truth or treat receipt presence as verification.
- Write, exec, plugin, and network access default to denied; secrets use opaque credential handles and never enter Journey events.
- Telemetry is off by default.
- Missing containment must retain the accepted EXECUTION_CONTAINMENT_UNAVAILABLE null and must never fall back to ordinary execution or claim sandboxing.
- No provider, endpoint, model, or network dispatch from evidence routes
- New Python and Dart files stay at or below 300 physical lines.
- The verifier path keeps zero third-party runtime dependencies.
- Existing public paths, secrets, private artifacts, and historical receipts never enter fixtures.
- Each implementation task uses RED, GREEN, focused regression, gates, review, then a narrow commit.
- No public release is permitted before all six phases pass, even if it uses the non-executing profile.

---

## Per-task evidence envelope

For every numbered task, record `git rev-parse HEAD`, `git rev-parse HEAD^{tree}`, branch/worktree identity, and clean task-boundary status before RED. New production files stay at or below 300 physical lines, grandfathered over-limit files shrink, new/modified production functions stay at or below 60 lines, and test functions stay at or below 80 lines. Before handoff, record exact RED/GREEN/verification commands and exits, test and mutation denominators, touched-file SHA-256 values, measured file/function ceilings, limitations, `does_not_prove`, the task commit as rollback point, and receiving-owner acceptance. A missing field blocks the next task; reject with `git revert --no-edit HEAD` and rerun phase-to-date gates.

## Immutable preflight decisions

Phase 6 cannot start until the receiving release owner records and accepts all of these facts without guessed values: Phase 1 through 5 acceptance receipt hashes; exact supported Windows editions/build ranges/architectures and primary-source evidence; a truly clean snapshot runner without Python, Flutter, Visual Studio, Flywheel, or prior state; Authenticode provider, protected key custody, certificate chain/subject/thumbprint policy, RFC 3161 timestamp URL and digest, rotation/revocation, and uninstaller signing; every font's copyright/license/source/hash/redistribution terms (the current twelve font files, including Conso, have no accepted redistribution evidence and must be licensed, replaced, or removed); every shipped component's license/provenance; a previous supported signed installer with source tag/commit, hashes, schemas, and provenance for upgrade/rollback; protected signing and release environments plus PyPI Trusted Publishing; complete action SHA and toolchain pins; and exact retention days for build logs, signing logs, candidate artifacts, acceptance packets, and revoked releases.

User Journeys, drafts, and recovery journals are retained on-device indefinitely until the user explicitly deletes them. Per-user uninstall keeps that data by default; a separately confirmed `Delete Flywheel user data` action deletes it. The first candidate profile is exactly `flywheel.desktop-profile/non-executing/v1`: Journey persistence/projection, blocked-check recording, hash/schema/signature/Merkle/packet verification, admitted data-only checks, and capability-gated read-only extensions are enabled; arbitrary Python, user tests, shell/build runners, agent write/exec, plugin calls, executable packs, and Incident-generated execution are denied. Calling this profile sandboxed is prohibited.

### Task P6-T1: Bind preflight facts and one release identity

**Files:**
- Create: `desktop/release/windows-support.json`
- Create: `desktop/release/toolchains.json`
- Create: `desktop/release/release-policy.json`
- Create: `harness/release_identity.py`
- Create: `desktop/scripts/render_windows_version_info.py`
- Modify: `desktop/windows/runner/Runner.rc`
- Modify: `packaging/flywheel-gateway.spec`
- Test: `tests/test_release_preflight.py`
- Test: `tests/test_version_alignment.py`
- Test: `desktop/test/version_truth_test.dart`

**Interfaces:**
- Consumes: approved preflight facts, exact phase receipt hashes, tag/source commit, `pyproject.toml`, `desktop/pubspec.yaml`, `desktop/lib/version.dart`, PE metadata, Inno identity, and authenticated gateway API/capability versions.
- Produces: `build_release_identity(root: Path, *, tag: str, source_commit: str, phase_receipts: list[str]) -> dict` using `flywheel.release-identity/v1` and `{version,tag,source_commit,source_tree_sha256,wheel_name,desktop_product_id,desktop_exe_version,gateway_exe_version,installer_app_id,api_schema,capability_schema,profile,phase_receipts,policy_sha256,toolchains_sha256,support_sha256}`.

- [ ] **Write RED tests.** Fail on any missing preflight decision, unsupported/ambiguous OS, mutable tool/action version, action ref not a full 40-hex SHA, absent retention integer, unaccepted phase receipt, identity drift across tag/Python/Dart/Flutter/PE/Inno/API/release title, or a profile claiming execution/sandboxing. Current source must fail because required evidence and policies do not exist.
- [ ] **Run RED.** Run `python -m pytest tests/test_release_preflight.py tests/test_version_alignment.py -q` and from `desktop/` run `flutter test test/version_truth_test.dart`; expect the new preflight test to fail on unresolved release facts.
- [ ] **Implement minimal GREEN.** Populate policies only from owner-accepted offline evidence, use exact numeric build/retention values and full hashes, render both PE resources from the identity, and reject rather than default any missing fact. If a listed preflight fact remains unavailable, stop Phase 6 with a typed blocking receipt and do not commit or advance.
- [ ] **Verify.** Run both RED commands and `python scripts/check_file_gate.py`; expect PASS only when every identity surface and policy hash agrees and no secret/key/path appears in JSON.
- [ ] **Commit scope.** Run `git add desktop/release/windows-support.json desktop/release/toolchains.json desktop/release/release-policy.json harness/release_identity.py desktop/scripts/render_windows_version_info.py desktop/windows/runner/Runner.rc packaging/flywheel-gateway.spec tests/test_release_preflight.py tests/test_version_alignment.py desktop/test/version_truth_test.dart && git commit -m "build: bind windows release identity"`.

### Task P6-T2: Default-reject the complete payload and evidence inventory

**Files:**
- Create: `desktop/release/payload-policy.json`
- Create: `desktop/release/components.json`
- Create: `desktop/release/PRIVACY.md`
- Create: `desktop/release/THIRD-PARTY-NOTICES.txt`
- Create: `desktop/release/FONT-PROVENANCE.json`
- Create: `desktop/scripts/release_manifest.py`
- Create: `desktop/scripts/generate_release_evidence.py`
- Test: `tests/test_windows_release_manifest.py`
- Test: `tests/test_windows_release_evidence.py`

**Interfaces:**
- Consumes: Task P6-T1 identity, declared staging files, component/license/font inventory, exact retention/privacy facts, and generated PE dependency inventory.
- Produces: `build_manifest(staging_root: Path, *, policy: dict, version: str, source_commit: str) -> dict`, `verify_manifest(staging_root: Path, manifest: dict, *, policy: dict) -> dict`, CLI `release_manifest.py build|verify`, default-reject `flywheel.windows-payload-policy/v1`, payload manifest `flywheel.windows-payload-manifest/v1`, SPDX 2.3 SBOM, and signed-provenance inputs.

- [ ] **Write RED tests.** Allow only explicit normalized relative file/type/hash/size/purpose/license/component rows; reject globs, extra/missing files, symlinks/reparse points, alternate data streams, case collisions, reserved names, undeclared DLL/PE imports, and secrets, credentials, databases, caches, models, weights, training data, corpora, host paths, or private artifacts. Require complete notices/privacy/font redistribution and SBOM relationships; the current twelve-font inventory fails until each file is accepted or removed.
- [ ] **Run RED.** Run `python -m pytest tests/test_windows_release_manifest.py tests/test_windows_release_evidence.py -q`; expect import/policy and font-provenance failures.
- [ ] **Implement minimal GREEN.** Hash bytes with SHA-256, derive no allowlist entry from observed staging, generate deterministic JSON/SPDX, remove or replace any font lacking accepted redistribution evidence, and include the profile's disabled operations and on-device/CI retention inventory in privacy evidence.
- [ ] **Verify.** Run the RED command, `python scripts/check_file_gate.py`, `python scripts/check_claim_language.py`, `python scripts/check_public_instructions.py`, and `python scripts/check_writing.py --profile procedure --gate desktop/release/PRIVACY.md desktop/release/THIRD-PARTY-NOTICES.txt`; expect PASS with every staged byte declared and attributable and every secret/path plant rejected by the focused tests.
- [ ] **Commit scope.** Run `git add desktop/release/payload-policy.json desktop/release/components.json desktop/release/PRIVACY.md desktop/release/THIRD-PARTY-NOTICES.txt desktop/release/FONT-PROVENANCE.json desktop/scripts/release_manifest.py desktop/scripts/generate_release_evidence.py tests/test_windows_release_manifest.py tests/test_windows_release_evidence.py && git commit -m "build: default-reject windows payload"`.

### Task P6-T3: Stage a per-user, recoverable installer

**Files:**
- Create: `desktop/scripts/stage_windows_payload.ps1`
- Test: `tests/test_windows_installer_contract.py`
- Modify: `desktop/scripts/build_installer.ps1`
- Modify: `desktop/installer/flywheel.iss`
- Modify: `packaging/flywheel-gateway.spec`

**Interfaces:**
- Consumes: accepted release identity, policy, exact clean build outputs, manifest/evidence generator, and no preexisting staging tree.
- Produces: `Stage-WindowsPayload -RepositoryRoot -OutputRoot -IdentityPath -PolicyPath`, deterministic `build/windows/staging`, package-only installer build, per-user `{localappdata}\Programs\Flywheel`, least-privilege ACL, fixed AppId upgrade, repair, keep-data default, and separately confirmed delete-data uninstall.

- [ ] **Write RED tests.** Characterize recursive wildcard/skip/all-users behavior as forbidden; require a clean stage, declared files only, no `SkipFlutter|SkipEngine` release bypass, `PrivilegesRequired=lowest`, no privilege override, current-user registry, no service/task/startup/telemetry/non-loopback listener, atomic data migration, default retention, explicit deletion, and no broad ACL.
- [ ] **Run RED.** Run `python -m pytest tests/test_windows_installer_contract.py -q`; expect failure against the current recursive build and `PrivilegesRequiredOverridesAllowed=dialog`.
- [ ] **Implement minimal GREEN.** Split build/stage/package, fail if source outputs are stale or staging exists, copy only policy rows, verify the manifest before Inno, keep application and user data roots separate, and have the uninstaller remove program files while preserving data unless the explicit delete choice is confirmed.
- [ ] **Verify.** Run the RED command, `powershell -NoProfile -ExecutionPolicy Bypass -File desktop/scripts/stage_windows_payload.ps1 -RepositoryRoot . -OutputRoot build/windows/staging -IdentityPath build/release/release-identity.json -PolicyPath desktop/release/payload-policy.json`, then `python desktop/scripts/release_manifest.py verify --staging-root build/windows/staging --policy desktop/release/payload-policy.json --manifest build/windows/staging/release-manifest.json`; expect a deterministic declared staging tree and package input only.
- [ ] **Commit scope.** Run `git add desktop/scripts/stage_windows_payload.ps1 desktop/scripts/build_installer.ps1 desktop/installer/flywheel.iss packaging/flywheel-gateway.spec tests/test_windows_installer_contract.py && git commit -m "build: stage per-user windows installer"`.

### Task P6-T4: Sign, timestamp, and protect an immutable release graph

**Files:**
- Create: `desktop/release/windows-signing-policy.json`
- Create: `desktop/scripts/sign_release.ps1`
- Create: `desktop/scripts/verify_release.ps1`
- Create: `.github/workflows/windows-release-acceptance.yml`
- Modify: `.github/workflows/desktop-release.yml`
- Modify: `.github/workflows/publish.yml`
- Test: `tests/test_windows_release_workflow.py`
- Test: `tests/test_windows_signing_contract.py`

**Interfaces:**
- Consumes: P6-T1 through P6-T3 immutable hashes, protected credential handle, accepted certificate/timestamp policy, pinned action/toolchains, and later P6-T5 acceptance hash.
- Produces: `Sign-Release -ManifestPath -CredentialHandle` and `Test-ReleaseSignatures -ManifestPath`; signed/timestamped app and gateway before packaging, signed/timestamped installer and uninstaller, `flywheel.windows-release-manifest/v1`, and the graph `candidate -> sign -> verify-before-package -> package -> verify-after-download -> installed-acceptance -> protected-publish`.

- [ ] **Write RED tests.** Require certificate chain/subject/thumbprint/digest/RFC 3161 timestamp and manifest hash at every edge; fail revoked/expired/wrong-subject/missing timestamp, unsigned inner PE/uninstaller/installer, post-sign mutation, artifact identity drift, broad workflow permission, mutable action ref, independent wheel publish, tag-triggered publish, existing release/asset, `--clobber`, or protected-step bypass.
- [ ] **Run RED.** Run `python -m pytest tests/test_windows_release_workflow.py tests/test_windows_signing_contract.py -q`; expect failures for workflow-level `contents: write`, mutable actions, unsigned artifacts, independent PyPI trigger, and overwrite.
- [ ] **Implement minimal GREEN.** Candidate jobs use `contents: read`; signing alone gets protected credential access; acceptance consumes artifact hashes; GitHub publishing alone gets `contents: write`; PyPI publishing alone gets `id-token: write`. Both publish jobs are reusable `workflow_call` only and share one accepted identity; no Phase 6 workflow calls them. Existing releases/assets fail closed and overwrite flags are absent.
- [ ] **Verify.** Run `python -m pytest tests/test_windows_release_workflow.py tests/test_windows_signing_contract.py -q` and `python scripts/check_public_instructions.py`; with public synthetic signing fixtures expect policy tests PASS and every workflow/action/permission edge accepted. Real signing verification remains blocked until the protected signer produces the candidate and never exposes key material.
- [ ] **Commit scope.** Run `git add desktop/release/windows-signing-policy.json desktop/scripts/sign_release.ps1 desktop/scripts/verify_release.ps1 .github/workflows/windows-release-acceptance.yml .github/workflows/desktop-release.yml .github/workflows/publish.yml tests/test_windows_release_workflow.py tests/test_windows_signing_contract.py && git commit -m "ci: protect immutable signed releases"`.

### Task P6-T5: Prove installed behavior on every supported clean Windows target

**Files:**
- Create: `desktop/scripts/windows_acceptance.ps1`
- Create: `desktop/scripts/verify_clean_windows.ps1`
- Create: `tests/test_windows_acceptance_contract.py`
- Create: `tests/fixtures/windows-acceptance/README.md`

**Interfaces:**
- Consumes: signed candidate/release manifest, accepted support matrix, network-disabled clean snapshot runner `self-hosted,windows,flywheel-clean-vm`, previous supported signed artifact in `build/acceptance-input/previous`, and only public synthetic Journey fixtures.
- Produces: `Invoke-WindowsAcceptance -CandidateManifest -PreviousManifest -Output`, per-scenario JSON receipts, process/ACL/signature/hash captures, and packet `flywheel.windows-installed-acceptance/v1` bound to release/source/support/phase hashes.

- [ ] **Write RED contract tests.** Require clean-host attestation, non-elevated install, exact ACL, authenticated loopback, Journey create/restart/resume at the same head, packet export and offline recheck, real Stop with descendant termination, no false cancelled state, previous-version upgrade and rollback, repair, uninstall-retain/reinstall, separately confirmed uninstall-delete, signature/manifest checks after install, legal/font presence, and absence of service/task/startup/telemetry/non-loopback/unrelated files. Unsupported OS, missing previous artifact, or dirty image is a blocking null.
- [ ] **Run RED.** Run `python -m pytest tests/test_windows_acceptance_contract.py -q`; expect missing-script/schema failure.
- [ ] **Implement minimal GREEN.** Make the runner collect facts and invoke installed public CLI/loopback surfaces only; disable external network before installation, use no provider/model, enforce time/resource bounds, restore the clean snapshot per scenario, and never synthesize a PASS from process exit alone.
- [ ] **Verify.** On each policy-listed clean VM run `powershell -NoProfile -ExecutionPolicy Bypass -File desktop/scripts/windows_acceptance.ps1 -CandidateManifest build/acceptance-input/candidate/release-manifest.json -PreviousManifest build/acceptance-input/previous/release-manifest.json -Output build/windows-acceptance`; expect every scenario receipt MATCH and the packet to recheck offline. Then run the RED contract test against captured public-safe metadata.
- [ ] **Commit scope.** Run `git add desktop/scripts/windows_acceptance.ps1 desktop/scripts/verify_clean_windows.ps1 tests/test_windows_acceptance_contract.py tests/fixtures/windows-acceptance/README.md && git commit -m "test: verify installed windows candidate"`.

### Task P6-T6: Seal the release acceptance packet without publishing

**Files:**
- Create: `tests/test_windows_release_acceptance.py`
- Create: `project-docs/records/2026-08-14-desktop-phase-6-windows-release.md`
- Modify: `.github/workflows/windows-release-acceptance.yml`

**Interfaces:**
- Consumes: one release identity/manifest, all Phase 1 through 6 receipt hashes, per-supported-target installed packets, signatures/timestamps, payload/SBOM/notices/privacy/font provenance, and protected-environment reviewer decision.
- Produces: immutable `flywheel.desktop-release-acceptance/v1` with artifact/hash/signature/support/identity/install-scenario denominators, command/exits, limitations, rollback artifact, receiving owner, retention, and `does_not_prove`; it grants no publish/deploy authority.

- [ ] **Write RED acceptance tests.** Reject a missing target/scenario, phase receipt, file hash, signature/timestamp, SBOM relationship, notice/font/license/privacy row, rollback candidate, reviewer, denominator, retention value, or `does_not_prove`; reject any manifest/asset bytes that differ from the installed candidate.
- [ ] **Run RED.** Run `python -m pytest tests/test_windows_release_acceptance.py -q`; expect failure before the complete installed evidence set exists.
- [ ] **Implement minimal GREEN.** Aggregate only verified immutable inputs; hash and sign the acceptance packet, store public-safe records without secrets/host paths, and leave both reusable publish workflows uncalled. An existing remote release/asset remains a hard no-clobber failure if publishing is separately authorized later.
- [ ] **Verify.** Run `python -m pytest tests/ -q`, `python scripts/check_file_gate.py`, `python scripts/check_verifier_stdlib.py`, `python scripts/check_claim_language.py`, `python scripts/check_public_instructions.py`, `python scripts/check_writing.py --profile procedure --gate project-docs/records/2026-08-14-desktop-phase-6-windows-release.md`, and `python -m pip wheel . --no-deps --no-build-isolation -w build/wheel-smoke`; then from `desktop/` run `flutter analyze` and `flutter test`. Expect PASS; focused release-manifest/evidence tests reject every secret/path/undeclared-payload plant. Recheck the signed candidate, downloaded copy, installed files, acceptance packet, and rollback artifact hashes; no upload, release creation, deployment, or PyPI publication occurs.
- [ ] **Commit scope.** Run `git add tests/test_windows_release_acceptance.py project-docs/records/2026-08-14-desktop-phase-6-windows-release.md .github/workflows/windows-release-acceptance.yml && git commit -m "test: accept immutable windows release"`.

**Final gate:** The six phase receipts and Phase 6 installed packet establish candidate acceptance only. Publishing/deployment requires a separate explicit authorization and must consume the exact no-clobber hashes; rollback is the previous accepted signed installer plus `git revert --no-edit HEAD` for source changes. The receiving owner rechecks every signature, manifest, target denominator, retention fact, and limitation before any later release action.
