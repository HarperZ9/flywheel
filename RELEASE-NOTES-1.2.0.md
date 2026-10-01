# Flywheel 1.2.0

Draft release notes. Source integration, the final tagged build and installed
acceptance remain open. These notes do not identify a published release.

Flywheel remains a full native harness client with its engine, local task state,
model routing and permission controls. Articulate and Rowan use the model chosen
by the host; neither adds a model or publisher-funded backend. Flywheel's existing
local-model support remains part of the harness.

## What changed

- Rowan's completion and monitor work is included with a grading-integrity repair.
  A check that rewrites its protected grading files cannot adopt those changes
  as a trusted baseline. Incomplete or unreadable protected-file coverage prevents
  a trusted completion, even when the command reports success.
- Desktop Chat can speak completed Rowan replies after the user enables speech.
  Installed Windows and macOS voices supply playback; Linux reports unavailable.
  Speech starts off, skips restored history and partial responses, and has mute,
  Stop and interruption handling. Typed replies remain available when speech fails.
- The Windows installer bundles a C++ runtime at least as new as the compiler that
  built the app. Installers 1.0.4 through 1.1.2 bundled runtime 14.29. Release
  candidates built that way crashed in the runtime when the window closed.
  Publication now reads the runtime receipt and refuses a candidate whose runtime
  is older than its compiler or whose installed runtime files differ from the receipt.
- The Plugins view can preview a local-client connection command using the bundled
  engine. It shows whether the engine is available and keeps connection status
  untested until a client exercises the command. It does not write client settings.
- A restricted Articulate launch mode exposes local checks and host edits while
  refusing external editing backends. The connected model writes the rewrite;
  Articulate checks protected content and returns a receipt.
- The secondary evidence-task skill and plugin move to 0.2.0. Their ZIPs include
  portable metadata plus Codex and Claude compatibility manifests, and travel
  with the Windows product release candidate under reviewed checksums.

The accompanying native MCP package is undergoing integration and frozen-binary
qualification. Its intended surface is public skill resources, local identity
and receipt inclusion checks, using the same engine as the desktop installer.
Its final asset and acceptance status must be checked before these notes ship.

## Release boundaries

The final lane pins and payload receipts must be regenerated from accepted
Articulate source before the tagged build. The full client, native MCP package
and skill-only plugin are separate distribution surfaces with separate checks.
Marketplace approval and universal harness compatibility are not established.

Protected-file snapshots do not provide filesystem isolation or detect a change
restored between snapshots. Passing a check does not prove the test is adequate.
Rewrite guards can miss meaning changes and refuse valid paraphrases.

Speech tests cover simulated engines and control behavior. Audible output, voice
quality and interruption reliability still need installed-device receipts. The
final Windows installer needs acceptance in the supported install modes. Model
providers, macOS installation and clean-device operation remain separate checks.
No competitive-leadership claim follows from these tests or packaging changes.
