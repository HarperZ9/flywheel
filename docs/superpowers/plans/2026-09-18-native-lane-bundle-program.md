# Native lane bundle program (1.0.1 portability)

Goal: every lane installs and works on a fresh machine, with no sibling source
checkouts and no reference to the operator's directory layout. The desktop
installer is the vessel. Driven 2026-09-18.

## Why this exists

Lanes resolve from a source checkout via `resolve_repo` (FLYWHEEL_WORKSPACE_ROOT
or `repo.parent/<source_repo>`). On the maintainer's machine the sibling repos at
`C:/dev/public/*` make 13 lanes probe live. A fresh user has none of those, so
only the bundled set works. Bundled today: the 7 in `packaging/python-lane-payloads.jsonl`
(canon, crucible, forum, gather, index, mneme, plexus) plus the two harness-bundled
lanes (local-model, writing). Everything else needs bundling.

## Lane inventory (17)

- Bundled Python, done (7): canon, crucible, forum, gather, index, mneme, plexus.
- Harness-bundled, done (2): local-model, writing (writing "stale" is a probe
  HOME_MISMATCH artifact, not a defect; confirm and fix the probe env).
- HTTP, no local bundle (1): bulletin (remote board).
- Python, TO BUNDLE (5): chorus, articulate, relay, calibrate-pro,
  accountable-surface.
- Node, TO BUNDLE via a node path (2): learn, telos.

## Payload row schema (derived from gather's committed row)

One JSONL row per lane in `packaging/python-lane-payloads.jsonl`:
- From the registry (`harness/lanes_registry.py`): lane, registry_install_name,
  registry_source_repo, registry_package_disabled_reason,
  flywheel_registry_expected_version.
- From the lane's git checkout: owner_commit (HEAD), owner_tag, owner_describe,
  source.commit / repo / path.
- From the source tree: source.files[] (per-file path + bytes + sha256, sorted),
  source.file_count, source.bytes, source.manifest_sha256, source.algorithm
  ("sha256-canonical-source-manifest/v1").
- From the package: hidden_imports (every submodule), owner_project
  (build_system, console_scripts, imported_version, license, hashed license_files).
- Per-lane specifics: component_descriptor.entrypoint
  {argv: ["--bundled-lane-mcp", name], callable: "serve", health_tool:
  "<name>.status", module: "<name>.mcp"}, allowed_tools ["<name>.status",
  "<name>.doctor"], mcp {callable, callable_style, contract_status, doctor_tool,
  health_tool}.
- Boilerplate (same for all): does_not_prove (3 lines), packaging_boundary,
  component_descriptor.schema "flywheel.bundled-lane-component/v1".
- component_descriptor_sha256: canonical_sha256 of the descriptor.

Consumers: `scripts/build_python_lane_payloads.py` (verifies + copies),
`scripts/stage_python_lane_sources.py` (verifies hashes; --lane currently
choices=["canon"] only), `scripts/check_python_lane_payload_manifest.py` (gate),
`harness/bundled_lane_admission.py` (runtime dispatch of --bundled-lane-mcp;
currently references "relay" specifically). Test expected-set:
`tests/test_python_lane_payload_manifest.py` (registry_updates list).

## Phases

1. Keystone generator: `scripts/generate_python_lane_payload_row.py`. Given a lane
   name + its checkout, emit the full row. VERIFY by regenerating gather's and
   crucible's committed rows byte-for-byte. Recipe proven when they match.
2. Lane health (prerequisite for a valid row + launch):
   - articulate: add `articulate.status` and `articulate.doctor` tools + a `serve`
     entrypoint conforming to --bundled-lane-mcp (repo: C:/dev/articulate).
   - chorus: fix MCP launch (mcp_probe_failed) so `chorus` serves; confirm a
     status/doctor tool (repo: C:/dev/public/chorus).
   - relay: reconcile version pin vs source ("wrong Relay version") (repo:
     C:/dev/public/relay).
   - calibrate-pro, accountable-surface: confirm status/doctor + serve entrypoint.
3. Generate rows for the 5 Python lanes; add to the manifest; generalize
   `stage_python_lane_sources.py` --lane choices and
   `harness/bundled_lane_admission.py` beyond relay; update the expected-set test.
4. Node bundle path for learn + telos (separate mechanism; node runtime + src
   staging).
5. Font swap: bundle Zentropy Editorial (serif) + Zentropy Mono into the desktop
   app; replace Cascadia Mono in `desktop/pubspec.yaml` + theme tokens; align all
   public surfaces (app, media, site). Fonts + a font engine may exist in a Codex
   session and are live on harperz9.github.io.
6. Clean-env verification: probe every lane with NO FLYWHEEL_WORKSPACE_ROOT and NO
   sibling checkouts (simulate a fresh install) and confirm each comes up. Build
   the installer and run the installed-acceptance smoke.

## Verification bar

A lane counts as bundled only when it probes live from the vendored payload with
no sibling checkout present. Honest nulls: any lane that cannot reach that bar in
1.0.1 ships labeled, not hidden.
