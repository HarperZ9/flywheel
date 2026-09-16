# Installed Payload Binding

Status: implemented for installed-launch H20 preflight. This is local
acceptance evidence, not release publication.

## Problem

The installed-launch H20 check previously bound the expected source, version,
launcher EXE SHA-256, engine EXE SHA-256, and observed installed version. That
could miss a Flutter payload change where `flywheel_desktop.exe` stayed byte
identical while `data/app.so`, `data/flutter_assets`, or frozen `_internal`
engine files changed.

The acceptance decision needs to bind the complete installed payload expected
from the build producer. The expected set must come from the producer manifest,
not from whatever files happen to be installed at validation time.

## Manifest Schema

Schema: `flywheel.installed-build-manifest/v1`

Required identity fields:

- `source_commit`: expected source commit string.
- `version`: expected product version.
- `artifacts.app_sha256`: SHA-256 for `flywheel_desktop.exe`.
- `artifacts.engine_sha256`: SHA-256 for `engine/flywheel-gateway.exe`.
- `payload.schema`: exactly `flywheel.installed-payload/v1`.
- `payload.files`: complete expected installed file list.

Each `payload.files` row has a normalized path relative to the install root.
Paths use `/`, are case-insensitively unique, and may not be absolute, drive
qualified, empty, traversal-bearing, backslash-bearing, colon-bearing, or contain
control characters.

Build-byte rows use:

```json
{"path": "data/app.so", "origin": "build", "sha256": "<64 hex>", "size": 123}
```

Installer-generated rows are limited to the actual Inno uninstall files:

```json
{"path": "unins000.exe", "origin": "installer_generated"}
```

`unins000.dat` uses the same shape. These rows are presence-only. They
deliberately do not carry a build SHA-256 or build size because those bytes are
created by the installer, not by the Flutter or frozen-engine build. No
Flutter, CRT, launcher, frozen engine, `_internal`, or `data/**` path may use
`origin: "installer_generated"`.

## Verification

H20 still checks source, version, launcher hash, engine hash, and installed
version. It now also calls the installed payload verifier:

- every build-byte row must exist and match size plus SHA-256;
- every installer-generated row must exist;
- every installed file must be declared by the manifest;
- links, junctions, path traversal, and case collisions fail closed;
- the install root itself and its path ancestors may not be links or junctions;
- manifest relative paths are raw identifiers, not repaired strings;
- a build manifest without launcher and engine build-byte hashes is refused by
  the producer;
- legacy launcher-plus-engine manifests without `payload.files` fail H20 with
  `payload_manifest_missing`.

The verifier samples file metadata before and after hashing to catch ordinary
static-check races or accidental path swaps. This is a guardrail for an owned
installer acceptance check. It is not an adversarial filesystem-safety proof.

Existing legacy evidence remains narrower evidence. It may show launcher and
engine hash agreement, but it no longer completes installed-launch acceptance as
full payload-bound evidence.

## Producer Command

Run this after the Flutter release bundle, frozen gateway, and CRT staging roots
exist, before installed acceptance:

```powershell
python -m desktop.tool.installed_payload_binding build `
  --payload-root desktop/build/windows/x64/runner/Release `
  --payload-root desktop/build/engine/flywheel-gateway=engine `
  --payload-root desktop/build/crt `
  --installer-generated unins000.exe `
  --installer-generated unins000.dat `
  --source-commit <expected-commit> `
  --version <expected-version> `
  --out desktop/build/installer/installed-build-manifest.json
```

If Inno emits different generated paths for a candidate, list those exact paths
as additional `--installer-generated` values. Do not add generated files as
build-byte rows.

Then pass the manifest to installed-launch acceptance:

```powershell
desktop/tool/run_installed_launch_acceptance.ps1 `
  -InstallRoot <installed Flywheel directory> `
  -BuildManifest desktop/build/installer/installed-build-manifest.json `
  -SourceCommitExpected <expected-commit> `
  -ExpectedVersion <expected-version>
```

## Limits

The manifest is an operator-supplied integrity binding. It is not external
source attestation, a clean-tree claim, a signature check, an installer execution
receipt, UI acceptance, or publication evidence. In a dirty source tree, the
`source_commit` field names the expected commit only; it does not prove that all
working-tree bytes came from that commit.
