# Python Flagship Lane Payload Packaging Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the Python flagship lane payloads Gather, Crucible, Index, Forum, Plexus, Mneme, and Canon into Flywheel without relying on ambient PATH, global Python packages, stale C: checkouts, private configuration, or runtime network installation.

**Architecture:** Treat each lane as a reviewed source component first, then let the runtime/spec owners wire admitted components into the frozen gateway. The payload manifest pins owner release commits, source-file hashes, direct MCP modules, initial status/doctor tool sets, hidden imports, notice metadata, and dependency declarations. Build-only helpers now produce wheel/source payload receipts and synthetic installed-wheel fixture evidence; runtime admission still belongs to the integration owners.

**Tech Stack:** Python 3.11+, stdlib JSON validation, existing Flywheel bundled-lane descriptor schema `flywheel.bundled-lane-component/v1`, PyInstaller hidden-import lists supplied from source manifests.

**Spec:** `D:/fw-ship-sweep-20260910/ci-composition/ALL-LANES-INSTALL-MAP.md`, `D:/FlywheelBuilds/flywheel-lane-runtime-20260910/docs/bundled-lane-component-contract.md`, and `packaging/python-lane-payloads.jsonl`.

## Global Constraints

- Do not edit `packaging/flywheel-gateway.spec`, `harness/bundled_lane*`, `harness/lane_runtime*`, or runtime admission files in this payload branch.
- Public child launch stays `E --bundled-lane-mcp <compiled-name>`; no public module, path, Python executable, or package-name selector is introduced.
- No global pip or npm install, no running-app mutation, no device/provider/login/model call, no PyPI upload, and no automatic network install at app launch.
- Zero runtime dependency verifier path remains unchanged.
- Source pins come from current owner release remotes cloned to D: for inspection, not from stale C: checkouts.
- Initial admitted tool set is status/doctor only; useful workflow acceptance is recorded as build-only fixture evidence.
- Python source descriptors witness owner source files and entrypoints; the installed release receipt must bind interpreter, wheels, and complete payload closure.

---

## Files owned by this payload branch

- `packaging/python-lane-payloads.jsonl`: one JSON object per lane with the full Python source file hash manifest, descriptor candidate, hidden imports, license metadata, dependency declarations, and contract status.
- `scripts/check_python_lane_payload_manifest.py`: validates the JSONL manifest shape, descriptor digests, source manifest digests, tool pins, and known integration blockers.
- `scripts/build_python_lane_payloads.py`: verifies D: source clones against the manifest, copies notices, writes descriptor candidates, and optionally builds wheels into a D: output root.
- `scripts/run_python_lane_payload_fixtures.py`: launches installed-wheel MCP servers over stdio and runs one bounded synthetic useful workflow per lane.
- `tests/test_python_lane_payload_manifest.py`: keeps the validator and manifest wired into the test suite.
- `tests/test_python_lane_payload_build.py`: keeps the build helper and fixture catalog wired into the test suite.
- `docs/superpowers/plans/2026-09-11-python-lane-payload-packaging.md`: this strategy and implementation plan.

## Current pinned owner releases

| Lane | Owner tag | Owner commit | Owner version | Flywheel registry version | Source manifest | Descriptor digest | Contract state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gather | v1.8.2 | f72cb8ca729a2d9c273cfd1330cf0744fadeee39 | 1.8.2 | 1.6.1 | sha256:f360ef0271cd4fbcc2e778140c3396bfe7c5cc921b010b6186550f83f3d6dbb3 | sha256:8b6fb731857b23738178ecfd27791e2be5afc1b87e3174aa24a4c29a5f987831 | Accepted owner release; registry update needed in integration |
| crucible | v1.2.0 | 9aea59a8b70549581181b47a4c5e685939a4aca6 | 1.2.0 | 1.2.0 | sha256:04923ba4187425f3769a682597f9fef3cd7ed10fe3aca587ed2325e9b469a92a | sha256:857446eceb292c7ebb67b14b013c0ed3073fa2df02461d9c7833754cbd1354ce | Sync dispatcher-compatible |
| index | v2.13.0 | 6383d43dab9fd7426d5d9dc7d8beffebfb9e6461 | 2.13.0 | 2.10.0 | sha256:c56f6bf0726d90a030ef30a078bc0f06bc8d200a766c1cc8e85cec2a41f83676 | sha256:9248207f399bbad2372c9cb3e699d9a66b74dfaac5216961acd3385876ee85f2 | Accepted owner release; registry update needed in integration |
| forum | v1.14.0 | 7f8ae5e0dc3770017ec589e2825ab7bd7735ad73 | 1.14.0 | 1.13.0 | sha256:684a48d96823d296ad25ff0bf15f9a87253afb3688ef4cb20602f9e68a9e7f90 | sha256:0a9bee84cf6869f19a00bab62881e52ede4780ebca23fe59431566240ca5fd1d | Accepted owner release; async dispatcher/state-root support owned by runtime |
| plexus | v0.2.0 | 209eab3bf60a8960f7e9010219d92ec8522c7e3d | 0.2.0 | 0.2.0 | sha256:612330f3c3ca5bf5c3ac823aac35a59ac56e092768ed4c0239f7b709cacb10bf | sha256:1edf1ad892717defb38b37b2083c7eaedf555848b279d6a3eb2b65a623f4ed61 | Sync dispatcher-compatible |
| mneme | v0.3.0 | dc0356abba92c27259b0d88587b66d82297b8da7 | 0.3.0 | 0.2.0 | sha256:370b009cd30657a964c3487434e77b4ab52367453e45e0f1c429b64d1993b05d | sha256:40d2987bec62e5951e76d7d5f79d0b35e3b73661adb9652abf962f703abfc084 | Accepted owner release; registry update needed in integration |
| canon | v0.1.0 | c9ee6b33d89bd9cf8b2b214523f2b4ada77f75a0 | 0.1.0 | 0.0.0 | sha256:6de753b3158fee88e3ab344fbce3d9bae48f08a3b3e860c80b94df619d85920e | sha256:48353d55d004628438a729a5e4fc525f269f507eb1a02a604eef3be780ad644b | Accepted owner release; registry update needed in integration |

## Dependency and license closure

All seven current owner release pyprojects declare no runtime dependencies. Build backends are still build-time dependencies: Gather, Forum, Plexus, Mneme and Canon use `setuptools>=68`; Crucible pins `setuptools==82.0.1`; Index uses `hatchling>=1.25`. These build dependencies belong in a D: build-only environment or in prebuilt wheel receipts, not in the frozen verifier path.

License declarations are fair-source or FSL-to-MIT variants. The manifest records each owner LICENSE file hash, and the build helper copies those notices into the payload output. The user owns these first-party tools and has authorized Flywheel bundling; escalation is limited to an actual unresolved third-party restriction.

## Current build-only evidence

Build receipt: `D:/fw-ship-sweep-20260910/all-lanes-payloads/payload-build-20260910-225229/python-lane-payload-build-manifest.json`.

Installed-wheel fixture receipt: `D:/fw-ship-sweep-20260910/all-lanes-payloads/fixture-run-20260910-225229d/python-lane-fixture-report.json`.

| Lane | Wheel | Wheel SHA-256 | Source module files | Fixture |
| --- | --- | --- | --- | --- |
| gather | gather_engine-1.8.2-py3-none-any.whl | sha256:9b73e6db19c1bd888c508e42070b990f72e09789bff4390d7ed848894133daf8 | 64 | `gather.docs` verified one synthetic catalog row |
| crucible | crucible_bench-1.2.0-py3-none-any.whl | sha256:eef8bbc7d2af2619567561012970c17161508d219c2b2a816e68ec69d8e51f14 | 42 | `crucible.assess` returned two synthetic verdicts |
| index | index_graph-2.13.0-py3-none-any.whl | sha256:656cbac4bb0b95079ae09daf95d374e7ac318f213ddee61403b102b37d7bcdde | 117 | `index.map` mapped a tiny synthetic Python workspace |
| forum | forum_engine-1.14.0-py3-none-any.whl | sha256:1f156f11904939dd38883e783492141a2a9af32f5073aa71a3d6fda0d5ac3b70 | 70 | `forum.route` routed a synthetic verification request under a D: fixture state root |
| plexus | plexus_mesh-0.2.0-py3-none-any.whl | sha256:1c666d6ab5b404a70db51af436ec9ad05f94df1a4860c2008d79af2351d0d176 | 11 | `plexus_plan` planned the built-in `crucible` target |
| mneme | mneme_memory-0.3.0-py3-none-any.whl | sha256:f697ff02a8af117ac712e2c995906b8b9b141c6014cae08f56a399b59ba3574f | 23 | `mneme.remember` plus `mneme.recall` stored and recalled a synthetic fact |
| canon | canon-0.1.0-py3-none-any.whl | sha256:774327270e477f09eb42140f9d0fe516a9a4f48ca000a232b6de4aa7013ec8b6 | 84 | `canon.validate` accepted a synthetic canon record |

## Version policy decision

The manifest pins current owner release tags. Root accepted these as the source-of-truth packaging inputs, so the checker reports stale Flywheel registry values as `registry_updates`, not blockers. A separate registry/runtime owner should update Flywheel expected versions and compiled expectations in the integration branch.

## Runtime contract decision

Gather, Crucible, Index, Plexus, Mneme, and Canon have sync MCP callables compatible with the runtime branch's current `result = serve()` dispatcher. Forum's exact direct MCP callable is `forum.mcp_surface:serve_stdio`, and it is async. Runtime support for async execution and Forum's private ledger state root is owned by the runtime owner; this payload branch preserves the source callable and runs build-only Forum fixtures with the child working directory bound to a D: fixture state root.

## Implementation tasks

### Task 1: Promote accepted Python lane descriptors

**Files:** create or update descriptor JSON under `packaging/bundled-lanes` in the integration branch; update compiled expectations in the runtime owner's files.

- [ ] Copy the accepted descriptor objects from `packaging/python-lane-payloads.jsonl` for lanes accepted by the integration owner.
- [ ] Recompute descriptor SHA-256 from the copied descriptor text using Flywheel canonical JSON.
- [ ] Add compiled expectations for exactly those lanes, binding descriptor digest, source manifest digest, repo, commit, source path, version, module, callable, health tool, and allowed tools.
- [ ] Run the runtime owner's descriptor gate for each copied descriptor.

### Task 2: Add build-only wheel/source payload preparation

**Files:** create a build helper owned by packaging, not app launch.

- [x] Add `scripts/build_python_lane_payloads.py`.
- [x] In a D: build-only output root, build wheels from the exact owner tags or copy source modules from the exact source manifests.
- [x] Hash wheel files and source module trees.
- [x] Write an installed release receipt that binds interpreter, wheel/source payloads, descriptor JSON, hidden imports, and notice files.
- [ ] Ensure app launch only uses bundled files and never calls pip, npm, git, or a network installer.

### Task 3: Add isolated installed-process acceptance

**Files:** tests or scripts in the integration branch.

- [ ] Launch the frozen gateway copy with PATH stripped of developer Python, Node, npm, and C: source roots.
- [ ] For each admitted lane, call `initialize`, `tools/list`, status, and doctor with bounded timeout.
- [ ] Verify serverInfo version, allowed tool admission, module origin, and descriptor digest.
- [ ] Corrupt one descriptor and remove one payload module in a disposable copy; require typed failure and no PATH fallback.

### Task 4: Keep useful workflow acceptance separate

**Files:** acceptance tests/docs after descriptor admission.

- [x] Add one synthetic useful workflow per lane as installed-wheel build evidence.
- [ ] Keep provider, device, private memory, browser, and file mutation operations behind their existing reviewed operation boundaries.
- [ ] Preserve stale or missing outcomes instead of relabeling them as installed.
