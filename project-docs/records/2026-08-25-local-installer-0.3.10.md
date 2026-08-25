# Local enterprise release build: Flywheel-Setup-0.3.10-x64

Date: 2026-08-25
Artifact: `desktop/build/installer/Flywheel-Setup-0.3.10-x64.exe`
(20.7 MB, gitignored build output)
SHA-256: `b0e931c6d7b7d1841ec56771054dca68f3492eaaf830c1dc58e41cfd5955e233`
Source commit: be562ea on feat/p3-t6-receipt-proof (43 commits ahead of
release/0.3.10 at build time)
Built with: desktop/scripts/build_installer.ps1 -- the same script the
desktop-release CI workflow runs.

## Version gate

One platform, one version: pyproject.toml 0.3.10 == pubspec.yaml
0.3.10+10 == lib/version.dart 0.3.10.

## Gates before build

```text
flutter analyze --no-pub            # no issues
flutter test --no-pub               # 571 passed, 4 skipped
python -m pytest tests/ -q          # exit 0 (full suite)
scripts/check_file_gate.py          # clean, 0 new, 0 grown
scripts/check_verifier_stdlib.py    # clean
scripts/check_claim_language.py     # clean
python -m harness.cli_entry gate    # PASS / rewitness MATCH
```

## Toolchain (this machine)

| Stage | Tool |
|---|---|
| Flutter Windows release | flutter 3.44.6 stable |
| Engine freeze | PyInstaller 6.21.0 (the CI pin), packaging/flywheel-gateway.spec |
| CRT payload | VC143 redist 14.44.35112 (VS 18 Community Redist tree) |
| Installer compile | Inno Setup 6.7.3 at C:/dev/release-tools/inno-6.7.3 |

All four stages ran clean; ISCC compile 14.1 s.

## Frozen-engine smoke (proof the whole platform is inside)

The frozen gateway was booted from the installer's engine payload on a
scratch port and run root, authenticated with its own minted token:

```text
GET /api/world       -> 200
GET /api/subagents   -> 200 flywheel.subagent-list/v1
GET /api/skills      -> 200 flywheel.skill-list/v1
GET /api/pm/roadmap  -> 200
GET /api/hooks       -> 200 flywheel.hook-registry/v1
```

Every surface shipped in this branch's sessions answers from inside
the exe. (/api/bench/traces is a POST route; a GET probe failing there
is the probe's fault.)

## Does not prove

This is an UNSIGNED release candidate, identical in content to what
desktop-release.yml stages on a v* tag. Authenticode signing custody,
the clean-snapshot VM acceptance pass, font redistribution licensing,
and prior-signed-installer comparison remain operator-side per the
Phase 6 blocking receipt, which stands unchanged.
