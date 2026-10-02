# Flywheel 1.2.1

Release workflow fix; no runtime changes from 1.2.0.

This release carries every 1.2.0 feature listed below and is the first build of
that code with a Windows installer. The 1.2.0 tag published the PyPI package,
but its release workflow stopped before it built an installer, so 1.2.0 has no
GitHub release. The 1.2.0 tag is unchanged.

## Release workflow fix

- The release job installs `pytest-timeout` before it runs pytest. The 1.2.0
  tag run failed there, because `pytest.ini` passes timeout flags (#319,
  cherry-picked as d59d5008).
- Installed acceptance accepts patch tags such as `v1.2.1`. It used to accept
  only `vX.Y.0` tags, so a fixed 1.2.0 could not ship as a patch. Pre-release
  and build suffixes are still refused.
- `SHA256SUMS.txt` and the plugin checksum file end each line with LF. Earlier
  Windows release files used CRLF, which GNU `sha256sum -c` reads as part of
  the file name.
- Version declarations move to 1.2.1. The engine, desktop app, lanes and
  companions are built from the 1.2.0 source.

## If you run 1.1.2 or earlier

Two changes affect you directly. Upgrading to 1.2.1 fixes both.

- Earlier installers contacted the publisher's hosted Bulletin board by default.
  The lane probe that runs after each lane install sent a request to that board
  with no setup. Flywheel now sends no Bulletin request until you set
  `FLYWHEEL_BULLETIN_URL`.
- Earlier Windows installers shipped C++ runtime 14.29, older than the compiler
  that built the app. 1.2.0 test builds that used this runtime crashed when the
  window closed. This installer bundles a runtime at least as new as the
  compiler, and publication refuses a candidate that does not.

## Carried from 1.2.0

- Bulletin setup is explicit. The Bulletin lane reads needs setup until you set
  `FLYWHEEL_BULLETIN_URL`. Identity registration and public outcome posts need
  `FLYWHEEL_BULLETIN_BASE_URL` or an explicit origin.
- Rowan's completion and monitor work is included with a grading-integrity
  repair. A check that rewrites its protected grading files cannot adopt those
  changes as a trusted baseline. Incomplete or unreadable protected-file coverage
  prevents a trusted completion, even when the command reports success.
- Desktop Chat can speak completed Rowan replies after you enable speech.
  Installed Windows and macOS voices supply playback; Linux reports unavailable.
  Speech starts off, skips restored history and partial responses, and has mute,
  Stop and interruption handling. Typed replies remain available when speech
  fails.
- Publication reads the C++ runtime receipt and refuses a candidate whose runtime
  is older than its compiler or whose installed runtime files differ from the
  receipt.
- The Plugins view can preview a local-client connection command using the
  bundled engine. It shows whether the engine is available and keeps connection
  status untested until a client exercises the command. It does not write client
  settings.
- A restricted Articulate launch mode exposes local checks and host edits and
  refuses external editing backends. The connected model writes the rewrite;
  Articulate checks protected content and returns a receipt.
- The evidence-task skill and plugin move to 0.2.0, with portable metadata plus
  Codex and Claude compatibility manifests.
- The native tool companion uses the same engine payload as the Windows
  installer. Its restricted profile exposes local identity, receipt inclusion
  verification and two public skill resources. It grants no model, network,
  execution or write access.
- Release checks install the tag-built Windows installer in disposable CI and
  exercise the installed engine, Canon context, restricted tool profiles and
  bundled lanes before the release is staged.

## Assets

- `Flywheel-Setup-1.2.1-x64.exe` with `SHA256SUMS.txt`: the full Windows client.
- `flywheel-tools-1.2.1-source-plugin.zip` with `source-plugin-SHA256SUMS.txt`:
  the restricted two-tool profile for clients that already have Python 3.11 or
  later. It is a release asset only, is not submitted to any directory, and does
  not replace the full client.
- The native MCP companion (`.mcpb`) and the skill-only plugin ZIPs, each with
  its own checksum file. Both are additional surfaces, not the full client.
- `flywheel-verify` 1.2.1 on PyPI: `pip install flywheel-verify==1.2.1`.

## Limits

- Installed acceptance does not exercise a configured Bulletin endpoint; a
  source-level test covers that path.
- Speech tests cover simulated engines and control behavior. Audible output and
  interruption reliability on real devices are not yet measured.
- Protected-file snapshots do not provide filesystem isolation or detect a change
  restored between snapshots. Passing a check does not prove the test is
  adequate.
- macOS installation, model providers and clean-device operation are separate
  checks. Marketplace approval and universal harness compatibility are not
  established. No competitive-leadership claim follows from these tests.
