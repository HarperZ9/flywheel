# Local client access to the bundled tool engine

Status: implementation under the operator's mature-release, full-client and BYOM instructions. No separate release or public deployment is authorized by this work.

## Problem and decision

The native client owns an engine, but the current Articulate payload is pinned to 0.5.0 and omits the calling-model edit protocol. Existing plugins can depend on console commands absent from a clean installed machine. A direct bundled-lane invocation also lacks the parent gateway's launch controls. Connect supported local clients to the packaged engine with an explicit restricted mode and clear configuration preview.

## Scope

1. Integrate the accepted Articulate 0.6.0 release source, exact merge commit 36f7e9f1f027f400b4839ec7394d64823ed1ac1d, through the existing registry and generated payload manifest. Add policy entries for local edit_plan/edit_submit. Retain explicit legacy network operations at their existing approval tier. This source includes the accepted lexical meaning guard. The local v0.6.0 tag identifies the source; local tagging does not establish remote tag or package publication.
2. Extend --bundled-lane-mcp articulate with a strictly parsed --local-only option. Admit no other lane to this mode without a reviewed contract. Force the local tool set and local-only backend behavior before serving, regardless of inherited environment. Do not expose new network listeners or credentials.
3. Add a native app-owned configuration preview beside existing plugin management. Resolve the engine through GatewayProcess.bundledEngine. Generate supported Codex TOML and MCP JSON snippets for the restricted Articulate mode. Include an honest availability reason and permission summary. Copying/exporting a snippet must not edit another client's configuration or imply a successful connection.

## Ownership

The payload worker owns registry, Articulate tool policy, payload row, notice and corresponding tests. The entry worker owns bundled entry parsing/local-only execution and tests. The UI worker owns the preview model/service, native view integration, UI tests and usage documentation. The coordinator owns this spec, source reconciliation and combined acceptance. All workers preserve prior candidate changes.

## Acceptance

- Manifest source and registry agree on the immutable accepted release source; regeneration and hash checks pass.
- Plan/submit works through the actual staged Articulate source. Explicit network/subprocess backend requests are refused in the restricted mode, without invoking them.
- Unexpected flags and other lanes fail closed. Inherited environment cannot widen the restricted profile.
- Preview uses the absolute bundled executable, refuses a missing bundle, escapes Windows paths correctly and includes no tokens, publisher endpoints or implicit write/exec grants.
- Existing gateway pairing and native provider-session workflows remain distinct.
- Actual frozen-binary and installed-client acceptance are required before claiming compatibility. Source and widget tests alone do not close those gates.

This adds tool connectivity to the full Flywheel application. It does not add a model, paid backend, public cloud service or reasoning-trace evaluation feature.
