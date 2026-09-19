# Telos (Flywheel lane: reconciliation)

> Native-feature documentation for the `telos` lane as it lives inside Flywheel.
> Scope note: statements are marked observed (read from code in `public/telos`
> and `public/flywheel/harness`) or proposed (a change not yet in the code).
> Version claims track telos `0.2.0` and the lane registry entry at that version.

## One sentence

Telos is Flywheel's reconciliation lane: it exposes one read-only MCP surface of
41 `telos.*` tools that report workbench readiness, run the golden five-flagship
workflow across sibling lanes, run doctors over CI and presentation and
accessibility state, and assemble proof packets whose verdict recomputes from
the packet's own materials.

## One paragraph

Inside Flywheel, telos is the lane that reads the state of the other lanes and
reconciles it into one operator map. Every tool returns a
`project-telos.flagship-action/v1` envelope with a MATCH, DRIFT, or UNVERIFIABLE
status, so a host always gets a structured verdict and a next action. The
lane ships four proof lanes (agent-action, research, visual, build) where the
verdict folds out of checks the verifier recomputes, so a packet that carries
its own MATCH cannot win with it. Telos is registered as the `telos` lane in
`harness/lanes_registry.py` (organ `reconciliation`) and sits third in the
gateway spine after `flywheel` and `local-model`. It is a node lane, so Flywheel
launches `demo/telos-mcp.mjs` from a Telos source checkout at `public/telos`; no
npm distribution is admitted, and the public roster reports an empty launch hint
for it. Beyond the MCP surface, Flywheel runs telos's own creative-kernel code in
place through `harness/telos_kernels.py` and registers a Telos browser-admission
driver behind the effector seam. The Telos core is zero-dependency and node 20 or
newer; CI runs on node 24. Observed.

## Feature list (each bound to code)

- **One MCP surface, 41 read-only tools.** `demo/telos-mcp.mjs` serves a stdio
  MCP server (protocol `2025-06-18`) that lists 41 `telos.*` tools and dispatches
  each to a `demo/*.mjs` script through `spawnSync`, returning both a text block
  and `structuredContent`. Every tool is read-only and zero-auth. Observed:
  `public/telos/demo/telos-mcp.mjs`.
- **A verdict on every call.** Each tool emits a
  `project-telos.flagship-action/v1` envelope carrying MATCH, DRIFT, or
  UNVERIFIABLE and a next action. A missing dependency returns UNVERIFIABLE
  and names the gap by path. Observed:
  `public/telos/README.md`, the tool descriptions in `demo/telos-mcp.mjs`.
- **Five-flagship reconciliation.** `telos.room` and `telos.workflow` read the
  sibling gather, crucible, index, and forum source checkouts and a local python
  interpreter to summarize the room and validate the golden workflow. Without
  those siblings both return an UNVERIFIABLE envelope naming the missing
  dependency. Observed: `demo/telos-mcp.mjs` (tool descriptions),
  `demo/room.mjs`, `demo/flagship-workflow.mjs`.
- **Roster freshness and server manifest.** `telos.mcp.freshness` compares loaded
  MCP servers against expected versions, tools, and probes and returns MATCH /
  DRIFT / UNVERIFIABLE. `telos.server.manifest` emits a five-server launch map
  with ready-to-paste host config. Observed: `demo/mcp-freshness.mjs`,
  `demo/server-manifest.mjs`.
- **Nine doctors, offline.** `telos.ci.doctor`, `telos.ci.triage`,
  `telos.presentation.doctor`, `telos.accessibility.doctor`,
  `telos.performance.doctor`, `telos.compatibility.doctor`,
  `telos.operator.doctor`, `telos.doctor`, and `telos.mcp.freshness` audit CI
  runtime state, README and brand parity, static HTML accessibility, byte
  budgets, protocol coverage, and discoverability against local checkouts. CI
  triage also accepts live GitHub Actions intake through the CLI using local `gh`
  auth. Observed: `demo/ci-doctor.mjs`, `demo/ci-triage.mjs`,
  `demo/presentation-doctor.mjs`, `demo/accessibility-doctor.mjs`,
  `demo/performance-doctor.mjs`, `demo/compatibility-doctor.mjs`,
  `demo/operator-doctor.mjs`.
- **Four proof lanes with a verdict that folds out of checks.** `telos.proof`
  (agent-action), `telos.proof.research`, `telos.proof.visual`, and
  `telos.proof.build` assemble packets and recompute every load-bearing claim
  from materials embedded in the packet. Editing a load-bearing field flips the
  verdict to DRIFT; a missing recomputable basis reports UNVERIFIABLE with the
  gap named by path. An embedded MATCH over tampered materials stays DRIFT.
  Observed: `demo/proof.mjs`, `public/telos/README.md`, `docs/PROOF-LANES.md`.
- **A witness stage that can only lower a verdict.** The agent-action packet joins
  source refs, context refs, route, admission, side effects, and output digests,
  then adds an Emet witness stage: a second reader over the packet's canonical
  bytes. It can lower a verdict, never raise one, and when it cannot be reached
  the packet records `witness_coverage: not_witnessed` and the verdict stands on
  the verifier alone. Observed: `public/telos/README.md`, `demo/proof.mjs`.
- **Context packs and receipts for large-workspace handoff.**
  `telos.context.envelope`, `telos.context.pack`, `telos.action.receipt`,
  `telos.loop.ledger`, and `telos.objective.monitor` return budgeted context
  packs with hashes and verdicts, an action-receipt interface, a durable
  loop-ledger convention, and objective-drift signals. Observed:
  `demo/context-envelope.mjs`, `demo/context-pack.mjs`,
  `demo/action-receipt.mjs`, `demo/loop-ledger.mjs`, `demo/objective-monitor.mjs`.
- **A creative engine with runnable meters.** `telos.creative.engine`,
  `telos.creative.kernels`, `telos.measurement.layers`,
  `telos.rendering.capabilities`, and `telos.display.calibration` return the
  engine manifest, deterministic kernels (ordered dither, pixel sort,
  harmonograph path, clustered light bins), the meter set, a
  WebGPU/WebGL/canvas/static renderer selection contract, and a non-mutating
  display-calibration contract. Observed: `demo/creative-engine.mjs`,
  `demo/creative-kernels.mjs`, `demo/measurement-layers.mjs`,
  `demo/rendering-capabilities.mjs`, `demo/display-calibration.mjs`.
- **Model foundry and learning forge.** `telos.model.foundry`,
  `telos.learning.forge`, and `telos.learning.labs` return a bounded contract for
  routing work across hosted and local models with verifier gates, receipt-backed
  learning packets, and executable lab contracts with measurements and failure
  cases. Observed: `demo/model-foundry.mjs`, `demo/learning-forge.mjs`,
  `demo/learning-forge-labs.mjs`.
- **Research proof preflights with explicit non-claims.**
  `telos.research.seed`, `telos.research.thermodynamic`, and
  `telos.rendering.research` return source-backed research seeds and deterministic
  preflights. The causal, embodied, and quantum packets each ship negative
  controls and named non-claims. Observed: `demo/research-seed.mjs`,
  `demo/thermodynamic-ai-chip-receipt.mjs`, `demo/rendering-research.mjs`,
  `public/telos/README.md`.
- **Native workstation control, catalog-only over MCP.**
  `telos.native.control` returns the read-only capability and verb catalog for
  browser (Chrome DevTools Protocol) and native-app (Windows UI Automation)
  actuation; `telos.browser.evidence` returns a redacted browser-evidence packet.
  The actuation itself runs through the CLI (`demo/native-control.mjs`); over
  MCP the tool returns only the catalog. Observed: `demo/native-control.mjs`,
  `demo/browser-evidence.mjs`.
- **Registry, queue, and substrate intake.** `telos.revival.registry`,
  `telos.second_level.queue`, `telos.workstation.substrate`, and
  `telos.showcase.scout` return the promotion registry, the public-safe
  second-level candidate queue, the aggregate workstation-repo register, and
  OSS showcase rankings drawn from fixtures. Observed: `demo/revival-registry.mjs`,
  `demo/second-level-flagship-queue.mjs`, `demo/workstation-substrate.mjs`,
  `demo/showcase.mjs`.
- **Zero-dependency core, two bin entries.** `package.json` declares no runtime
  dependencies, `engines.node >= 20`, and bin entries `telos` and `telos-mcp`
  that route to the same demo surface. License is FSL-1.1-ALv2. Observed:
  `public/telos/package.json`.

Honest null: the catalog summary reports "69 tools across 5 flagships." Those 69
require the sibling gather, index, forum, and crucible checkouts beside telos.
The 41 `telos.*` tools are the ones telos ships and serves by itself. Treat the
larger count as a composed total, not telos's own surface.

## Stepwise usage (how a user runs it)

Telos runs the same way whether or not Flywheel is present, from a source
checkout (no npm distribution is admitted).

1. **Get the checkout.**
   ```bash
   git clone https://github.com/HarperZ9/telos.git
   cd telos
   ```
   Node 20 or newer. There is nothing to install: the core is zero-dependency.

2. **Run the falsifiable demo.**
   ```bash
   node demo/run.mjs
   ```
   It renders a 4-D cube, perceives it through independent channels, checks the
   recovered vertex and edge counts against the true criterion, and prints a
   certificate that re-checks from its own evidence. Then it feeds the loop a
   render too small to read and shows it returning UNVERIFIABLE.

3. **Orient with the two map commands.**
   ```bash
   node demo/catalog.mjs --summary          # the tool map
   node demo/server-manifest.mjs --summary  # the MCP launch map with host config
   ```

4. **Check health and current state.**
   ```bash
   node demo/status.mjs --summary
   node demo/doctor.mjs --summary
   node demo/room.mjs --json                # needs the sibling checkouts
   ```

5. **Assemble a proof packet, then replay its verification.**
   ```bash
   node demo/proof.mjs agent-action --demo --json > packet.json
   node demo/proof.mjs verify packet.json
   ```
   Expected: `verdict MATCH`, `witness witnessed / MATCH`. Edit any load-bearing
   field in `packet.json` and the replay returns DRIFT.

6. **Serve the lane to a host over MCP.**
   ```bash
   npm start            # node demo/telos-mcp.mjs, stdio MCP
   ```
   Inside Flywheel this launch is what the lane layer spawns from the source
   checkout; a user rarely runs it by hand.

Most commands accept `--summary` for a compact terminal view and `--json` for
IDE, app, and automation hosts. Observed: `public/telos/README.md`, `USAGE.md`,
`package.json`.

## Piecewise reference (each capability, what it does)

### CLI commands
Observed in `public/telos/demo/` and the README command surface.

- **Orientation:** `run.mjs`, `catalog.mjs`, `server-manifest.mjs`, `status.mjs`,
  `doctor.mjs`, `room.mjs`.
- **Doctors:** `ci-doctor.mjs`, `ci-triage.mjs`, `presentation-doctor.mjs`,
  `accessibility-doctor.mjs`, `performance-doctor.mjs`, `compatibility-doctor.mjs`,
  `operator-doctor.mjs`, `mcp-freshness.mjs`. Live CI intake is read-only:
  `node demo/ci-triage.mjs --gh-run owner/repo#run_id --summary`.
- **Proof:** `proof.mjs` with `agent-action`, `research`, `visual`, `build`,
  `verify`, and `export`; `showcase.mjs`.
- **Context:** `context-envelope.mjs`, `context-pack.mjs`, `action-receipt.mjs`,
  `loop-ledger.mjs`.
- **Creative:** `creative-engine.mjs`, `creative-kernels.mjs`,
  `measurement-layers.mjs`, `rendering-capabilities.mjs`,
  `display-calibration.mjs`.
- **Research:** `causal-workbench-proof-packet.mjs`,
  `embodied-sim2real-proof-packet.mjs`,
  `quantum-error-correction-proof-packet.mjs`,
  `thermodynamic-ai-chip-receipt.mjs`.
- **Foundry:** `model-foundry.mjs`, `learning-forge.mjs`,
  `learning-forge-labs.mjs`.
- **Workstation:** `native-control.mjs`, `browser-evidence.mjs`,
  `workstation-substrate.mjs`, `revival-registry.mjs`,
  `second-level-flagship-queue.mjs`.

### MCP tools
41 tools, observed in `demo/telos-mcp.mjs` (the `tools` array and the
`toolScripts` dispatch map). Each is read-only, zero-auth, and returns a JSON
action envelope.

- Orientation: `telos.status`, `telos.doctor`, `telos.room`, `telos.workflow`,
  `telos.catalog`, `telos.server.manifest`, `telos.mcp.freshness`.
- Doctors: `telos.ci.doctor`, `telos.ci.triage`, `telos.presentation.doctor`,
  `telos.accessibility.doctor`, `telos.performance.doctor`,
  `telos.compatibility.doctor`, `telos.operator.doctor`.
- Context and receipts: `telos.admission.telemetry`, `telos.context.envelope`,
  `telos.context.pack`, `telos.action.receipt`, `telos.loop.ledger`,
  `telos.objective.monitor`.
- Foundry and learning: `telos.model.foundry`, `telos.learning.forge`,
  `telos.learning.labs`.
- Research: `telos.research.seed`, `telos.research.thermodynamic`,
  `telos.rendering.research`.
- Rendering, creative, measurement: `telos.rendering.capabilities`,
  `telos.measurement.layers`, `telos.creative.engine`, `telos.creative.kernels`,
  `telos.display.calibration`.
- Registry and substrate: `telos.revival.registry`, `telos.second_level.queue`,
  `telos.workstation.substrate`, `telos.showcase.scout`.
- Workstation control: `telos.native.control`, `telos.browser.evidence`.
- Proof lanes: `telos.proof`, `telos.proof.research`, `telos.proof.visual`,
  `telos.proof.build`.

### Flywheel-side bridges (telos code run in place)
Observed in `public/flywheel/harness`.

- **Creative kernel bridge** (`harness/telos_kernels.py`, schema
  `flywheel.telos-kernel-run/v1`) runs four of the lane's own kernels through node
  from `demo/creative-kernels.mjs`: `plotter.harmonograph-path`,
  `lighting.cluster-light-bins`, `raster.ordered-dither`,
  `raster.pixel-sort-rows`. It hands back the kernel's own measurement and receipt
  hashes and refuses by name when the checkout or node is absent.
- **Raster bridge** (`harness/raster_fx.py`, schema
  `flywheel.telos-raster-fx/v1`) feeds the ordered-dither and pixel-sort kernels
  either a seeded aperture plate or a caller PNG, fences the size at 640 px, names
  refusals, and returns the processed PNG with the kernel's receipt hash.
- **Creative pipeline stages** (`harness/creative_pipeline.py`) call the
  harmonograph and raster kernels as pipeline stages and fold each kernel receipt
  hash into a chained pipeline receipt.
- **Browser-admission driver** (`harness/telos_browser_adapter.py`,
  `telos_browser_config.py`, `telos_browser_registration.py`) registers a
  `telos-browser` driver behind `harness/browser_control.py`. Registration is
  explicit opt-in with no discovery or launch at startup, the config is immutable
  and content-free on failure, and the reviewed CDP module is pinned by sha256.

## Composition tutorial: telos inside the application

### Which lane it is
Telos is the `reconciliation` organ in the lane layer. Observed in
`harness/lanes_registry.py`:

```python
"telos": Lane(
    "telos", "project-telos-mcp", "node", ("demo/telos-mcp.mjs",), "npm", "0.2.0",
    "the reconciliation lane: five-tool workflow + creative engine + doctors",
    "reconciliation", source_repo="public/telos",
    package_disabled_reason="No published npm distribution is available. Use a Telos source checkout."),
```

It sits third in the flagship spine, `SPINE = ("flywheel", "local-model",
"telos", "index", "forum", "gather", "crucible", "learn", "mneme", "relay",
"plexus")` in `harness/gateway.py`. Because no npm distribution is admitted, the
public roster reports an empty launch hint: `tests/test_lanes.py` asserts
`resolve_mcp_command("telos") == []`, and Flywheel spawns the child from the
`public/telos` source checkout at runtime. Observed: `harness/lanes.py`,
`harness/lane_runtime.py`, `tests/test_lanes.py`.

### What it consumes from peers
- **Sibling lane checkouts.** `telos.room`, `telos.workflow`,
  `telos.server.manifest`, and `telos.mcp.freshness` read the gather, crucible,
  index, and forum source checkouts and a local python interpreter to reconcile
  them into one map. A missing sibling becomes an UNVERIFIABLE envelope naming
  the gap.
- **A witness reader.** The proof lanes' witness stage is a second reader (Emet)
  over the packet's canonical bytes. When it is unreachable, the packet records
  coverage as lost and the verdict stands on the verifier alone.
- **Kernel inputs.** The Flywheel bridges pass kernel arguments and, for raster,
  a caller PNG or a seeded plate into the lane's own kernel code.

### What it emits for peers
- **A flagship-action envelope.** Every tool returns
  `project-telos.flagship-action/v1` with a MATCH / DRIFT / UNVERIFIABLE verdict
  and a next action that a host routes on.
- **A five-server host manifest.** `telos.server.manifest` emits the launch map
  and host config that wires gather, index, forum, crucible, and telos into one
  MCP client.
- **Kernel receipts.** The bridges return `flywheel.telos-kernel-run/v1` and
  `flywheel.telos-raster-fx/v1` receipts whose hashes Flywheel's creative pipeline
  folds into its own chained receipt.
- **A registered effector driver.** `configure_telos_browser` registers the
  `telos-browser` driver with a `binding_sha256` that Flywheel's effector surface
  can address.
- **Replayable proof packets.** The four proof lanes emit packets a third party
  re-walks to reproduce the verdict.

### Where telos is already wired into Flywheel
Observed in `public/flywheel/harness` and the desktop client.

- **Lane registry entry and spine slot** (`harness/lanes_registry.py`,
  `harness/gateway.py`): organ `reconciliation`, third in `SPINE`.
- **Creative kernel and raster bridges** (`harness/telos_kernels.py`,
  `harness/raster_fx.py`) with gateway endpoints `/api/telos/kernel` and
  `/api/telos/raster`.
- **Creative pipeline stages** (`harness/creative_pipeline.py`) and the
  Flywheel implementations of the retro-CGI and film-media creative domains
  (`harness/retro_cgi.py`, `harness/film_media.py`).
- **Browser-admission driver** registered at gateway startup from
  `FLYWHEEL_TELOS_BROWSER_CONFIG`; when the registration state is unknown the
  gateway refuses to start (`harness/gateway.py`,
  `harness/telos_browser_registration.py`).
- **Desktop card** (`desktop/lib/models/lane_identity.dart`): title `Telos`,
  surface "workbench map".
- **Tests:** `tests/test_telos_kernels.py`, `tests/test_telos_browser_adapter.py`,
  `tests/test_telos_browser_bridge.py`, `tests/test_telos_owned_launch.py`, and
  `harness/telos_browser_bridge.test.mjs`.

### Worked example: telos reconciles the roster, then hands work onward
Goal: get one verdict on whether the loaded lanes match what Flywheel expects,
then use telos's own map to route the next step.

```bash
# 1. Reconciliation lane: compare loaded MCP servers against expected
#    versions, tools, and probes. Returns MATCH / DRIFT / UNVERIFIABLE.
node demo/mcp-freshness.mjs --json

# 2. Summarize the five-flagship room before routing work.
#    Needs the sibling gather, crucible, index, forum checkouts; without
#    them this returns UNVERIFIABLE naming the missing dependency.
node demo/room.mjs --json

# 3. Emit the host manifest that wires the peer lanes into one MCP client.
node demo/server-manifest.mjs --json
```

The contract handed across the seam is the flagship-action envelope. A host reads
telos's DRIFT or UNVERIFIABLE and knows a peer lane is stale or absent before it
routes a task through that lane. The verification lane (`crucible`) and the
routing lane (`forum`) consume that verdict the same way a downstream consumer
consumes any receipt here: the reconciler names the gap by path, so a peer that
was never loaded fails closed.

For a creative task, the same lane plugs in through the
kernel bridge: Flywheel's `/api/studio/pipeline` runs a harmonograph stage whose
work is telos's own `plotter.harmonograph-path` kernel, and the stage folds the
kernel's `receipt_hash` into the pipeline's chained receipt. Observed:
`harness/creative_pipeline.py`, `harness/telos_kernels.py`.

## Native-lane wiring status

Telos is a native lane, so the roster wiring exists. Present and verified:

- **Lane registry entry.** `LANES["telos"]` in `harness/lanes_registry.py`,
  organ `reconciliation`, version `0.2.0`, `source_repo="public/telos"`, kind
  `npm`.
- **Spine slot.** `SPINE` in `harness/gateway.py`, position three.
- **Expected-set and launch-hint tests.** `tests/test_lanes.py` lists `telos` in
  the expected lane set and asserts `resolve_mcp_command("telos") == []`, since
  the unpublished package exposes no public launch hint.
- **Desktop app card.** `laneIdentities['telos']` in
  `desktop/lib/models/lane_identity.dart`.
- **In-process bridges with tests.** `harness/telos_kernels.py`,
  `harness/raster_fx.py`, and the browser adapter, covered by the telos tests
  listed above.

What is bounded or in flight:

- **No published distribution.** `package_disabled_reason` records that no npm
  distribution is admitted. Flywheel launches telos from a source checkout, and a
  clean machine without that checkout has no telos lane. Observed:
  `harness/lanes_registry.py`.
- **No Python payload pin.** `packaging/python-lane-payloads.jsonl` and its
  checker `scripts/check_python_lane_payload_manifest.py` cover Python lanes
  (schema `flywheel.python-lane-payload/v1`). Telos is a node lane, so it is not
  in that manifest and carries no source-pin row there. For a node lane this is a
  natural non-entry.
- **Version lockstep.** The `0.2.0` string in `lanes_registry.py` is a
  hand-maintained constant. It must be bumped in the same change as telos's
  `package.json` version, or `lane_status` reports STALE against the checkout.
- **Reconciliation tools need the siblings.** `telos.room` and `telos.workflow`
  return UNVERIFIABLE unless the gather, crucible, index, and forum checkouts sit
  beside telos with a local python interpreter. This is disclosed coverage loss,
  reported by path.
- **Browser driver is bound, not runtime-verified.** `configure_telos_browser`
  returns `configured_not_runtime_verified` on success: the config binding is
  checked, the live actuation is not exercised at registration. Observed:
  `harness/telos_browser_registration.py`.

## Boundary

Telos tools are read-only, zero-auth, and emit JSON envelopes; the MCP surface
performs no external writes. Native workstation actuation lives in the CLI
(`demo/native-control.mjs`), and over MCP `telos.native.control` returns only the
capability catalog. The browser adapter fences request and result bytes and caps
the timeout at ten seconds, pins the reviewed CDP module by sha256, and refuses a
dispatched request that lacks a trustworthy terminal acknowledgement. Research
packets are deterministic preflights with named non-claims: the causal packet
does not claim causal discovery, the embodied packet does not claim real-robot
safety, and the quantum packet does not claim hardware error correction.
Observed: `demo/telos-mcp.mjs`, `harness/telos_browser_adapter.py`,
`public/telos/README.md`.

Independent-project note: telos is its own repository (`project-telos-mcp`,
`public/telos` in the workspace) with its own tests, CI, and release cadence
under FSL-1.1-ALv2. It composes with Flywheel through JSON seams and in-place
code bridges; it does not absorb the platform and is not absorbed by it.