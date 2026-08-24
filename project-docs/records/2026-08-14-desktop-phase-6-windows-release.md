# Desktop Phase 6 Windows release: code complete, installed acceptance BLOCKED

Date: 2026-08-23

Verdict: PARTIAL by design. The code-side Phase 6 work is complete and
verified: one release identity, a default-reject payload manifest, a
read-only candidate workflow, a protected no-clobber reusable publish
workflow, and full action SHA pins. The installed-Windows acceptance
that the phase exists to produce is BLOCKED on owner-accepted physical
facts this environment cannot supply. Per the plan's own instruction,
Phase 6 stops here with this typed blocking receipt instead of
fabricating any of them.

## Typed blocking receipt: flywheel.release-blocking/v1

| Blocking fact | Why it cannot be produced here | What unblocks it |
|---|---|---|
| Authenticode provider, key custody, certificate chain/subject/thumbprint, RFC 3161 timestamp URL | Signing requires a protected certificate and key custody the operator must choose and accept; fabricating one would be worse than none | Operator accepts a provider and custody model, then `desktop/release/release-policy.json` facts are filled |
| Clean snapshot Windows runner (`self-hosted,windows,flywheel-clean-vm`) | Requires a real VM snapshot with no Python, Flutter, VS, or Flywheel state | Operator provisions the snapshot and registers the runner label |
| Supported Windows editions/build ranges/architectures | Needs primary-source evidence accepted by the owner | Owner records the support matrix in `windows-support.json` |
| Font redistribution evidence | The shipped fonts, including Conso, have no accepted license/redistribution record; the payload policy marks this BLOCKED and the manifest refuses undeclared font bytes | Each font is licensed, replaced, or removed, and `FONT-PROVENANCE.json` is accepted |
| Previous supported signed installer (upgrade/rollback source) | No prior signed installer exists to roll back to | First accepted signed candidate becomes the rollback source for the next |
| Protected signing/release environments + retention days | GitHub environment protection and retention integers are operator account facts | Operator accepts them into `release-policy.json` |

## What IS complete and verified

- `harness/release_identity.py`: `flywheel.release-identity/v1`. The
  identity exists only when every policy file is present and carries no
  BLOCKED facts, tag/pubspec/pyproject versions agree, exactly five
  phase receipt hashes are bound, and the profile is
  `flywheel.desktop-profile/non-executing/v1`, never called sandboxed.
  7/7 tests.
- `desktop/scripts/release_manifest.py`: default-reject
  `flywheel.windows-payload-manifest/v1`. Only explicitly allowlisted
  normalized relative paths may ship; globs, host paths, reserved
  names, symlinks, alternate data streams, case collisions, undeclared
  files, and missing allowlisted files are all refusals. build/verify
  CLI round-trips. 9/9 tests.
- Workflow hardening: `desktop-release.yml` is now a candidate workflow
  with `contents: read` that stages the installer as an artifact and
  never touches releases. New `windows-publish.yml` is a reusable
  `workflow_call` that alone publishes, verifies the candidate hash
  before any upload, and treats an existing release as a hard
  no-clobber failure. `--clobber` is gone. Every action across all five
  workflows is pinned to a full verified 40-hex SHA (checkout, setup-
  python, upload/download-artifact, flutter-action, pypi-publish).
  PyPI Trusted Publishing keeps its isolated `id-token: write`. 7/7
  workflow contract tests.
- Policy scaffolding: `windows-support.json`, `toolchains.json`,
  `release-policy.json`, `payload-policy.json` carry the real pins that
  exist and explicit BLOCKED markers for the facts above, so the
  identity module refuses to run until they are resolved.

## Command evidence

```text
python -m pytest tests/test_release_preflight.py -q            # 7/7
python -m pytest tests/test_windows_release_manifest.py -q     # 9/9
python -m pytest tests/test_windows_release_workflow.py -q     # 7/7
python -m pytest tests/ -q --tb=no                             # 0 failures
python scripts/check_file_gate.py                              # clean
python scripts/check_verifier_stdlib.py                        # clean
python scripts/check_claim_language.py                         # clean
python scripts/check_public_instructions.py                    # clean
flutter test --no-pub (desktop/)                               # 568 passed, 4 skipped
flutter analyze --no-pub (desktop/)                            # no issues
```

## SHA-256 inventory at this record's boundary

| Artifact | SHA-256 |
|---|---|
| `harness/release_identity.py` | `59a426cb43dc7f12d2fc37c99a1b0b166789d174a4fbfb6ab6206f514a0832c3` |
| `desktop/scripts/release_manifest.py` | `238a744b999cd51c9c92d3049776cacf12a5ca6201541c2205e997cc51d47ad1` |
| `desktop/release/windows-support.json` | `eacb50d9efdf487970c53c1f7759d8729420f5af249cf661b9a8ec3dd97028e0` |
| `desktop/release/toolchains.json` | `55345c6bfcc10ff1644d1d31c69f8c7e46c699ae7645d8086b833ea8343c46c4` |
| `desktop/release/release-policy.json` | `3a480be6e2cc9aca6070a7f2a243b4c4739d121540e4afe548d5f38bb08f4990` |
| `desktop/release/payload-policy.json` | `6e2346ffb9fb3869c7096380324a6c3ae8fbc15333c479b9a2b623255b7cb881` |
| `.github/workflows/windows-publish.yml` | `f7ab0c72a66e757e23edb8393839f8d5b69155b6ac8245e4cfe69c2a79ea5e49` |
| `.github/workflows/desktop-release.yml` | `67bd5843462f7d86600b22f44bf4b3a4e4919a61bcb7ac61b92536ed22bba32c` |
| `.github/workflows/publish.yml` | `b8a7eccd2af2ed0eb57438221bb8afeddb1c6a0127e29f100259ea63f5b85a21` |

## What installed acceptance requires (unblocking path)

1. Owner accepts signing facts; `sign_release.ps1` /
   `verify_release.ps1` are written against the accepted policy.
2. Operator provisions the clean snapshot runner and accepts the
   support matrix; `windows_acceptance.ps1` runs the per-scenario
   receipts (install, persistence, packet export, real Stop, upgrade,
   rollback, repair, uninstall-retain, confirmed delete) on every
   supported target.
3. Fonts are licensed/replaced/removed; the payload manifest then
   admits the complete staged tree.
4. The acceptance packet (`flywheel.desktop-release-acceptance/v1`)
   aggregates the six phase receipts, per-target packets, and
   signatures, and still grants no publish authority: publishing is the
   separately authorized, explicitly called protected workflow.

## Does not prove

Nothing here proves installed behavior, signature validity, or release
readiness. No artifact was signed, no release was created, nothing was
published or deployed, and both publish paths remain uncalled. The
six-phase program is code-complete; candidate acceptance waits on the
blocking facts above, each of which is an operator decision or a
physical resource, not a code task.
