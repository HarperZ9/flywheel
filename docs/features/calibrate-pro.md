# Calibrate Pro (Flywheel calibration lane)

> Native feature documentation for Calibrate Pro as it lives inside Flywheel. Every claim below is bound to code in the `calibrate-pro` repo (`public/calibrate-pro`) or the Flywheel harness (`public/flywheel`). Observed facts are stated plainly; anything proposed or in flight is marked. Calibrate Pro is an independent tool (the `calibrate-pro` package, license FSL-1.1-MIT) that Flywheel composes as a lane and declares in its roster.

## One sentence

Calibrate Pro is Flywheel's calibration lane: a read-only MCP server that hands an agent the display calibration target catalog, the characterized panel catalog, and a device-free readiness doctor, while every operation that would change a display stays behind the desktop preview-and-confirm workflow and off the lane.

## One paragraph

Inside Flywheel, Calibrate Pro is the `calibration` organ. Its Flywheel-facing surface is a read-only MCP server, `serve()` in `calibrate_pro/mcp.py`, launched by `calibrate-pro mcp`. It exposes five tools that touch no display: a liveness status, a readiness doctor, the calibration target catalog, the characterized panel catalog, and the stored primaries for one panel. Enumerating targets and panels reads bundled data, the doctor inspects installed libraries and runs pure color math, and nothing here mutates state. Actuation stays elsewhere: applying an ICC profile, writing a gamma ramp, sending a DDC/CI value, or loading a compositor LUT happens only in the desktop window after an exact preview and an explicit confirmation, and the lane exposes none of it, which is why Flywheel floors the lane at tier T1. Calibrate Pro consumes no sibling-lane output; it is a leaf source in the roster. It emits read-only JSON that another lane or agent can read: a status envelope, a schema-1 doctor report, the target and panel catalogs, and per-panel native primaries that carry an explicit estimate label. It is an independent tool under FSL-1.1-MIT that Flywheel declares and health-probes as a lane.

## Feature list

Each item names the module that implements it. Paths are relative to the `calibrate-pro` repo unless the Flywheel harness is named.

- **Read-only MCP catalog and doctor server.** `calibrate_pro/mcp.py` `serve()` speaks JSON-RPC 2.0 over stdio, newline-delimited, protocol `2025-06-18`, with zero third-party dependencies. It is launched by `calibrate-pro mcp` (`cmd_mcp` in `calibrate_pro/main.py`) or `python -m calibrate_pro.main mcp`. This is the surface Flywheel launches as the lane.
- **Five device-free tools, no actuation.** `_tool_defs()` in `calibrate_pro/mcp.py` declares exactly `calibrate-pro.status`, `calibrate-pro.doctor`, `calibrate-pro.list-targets`, `calibrate-pro.list-panels`, and `calibrate-pro.panel-info`. A `tools/call` for any name outside `_TOOL_NAMES` returns error `-32602`; a tool that raises returns an `isError` result and keeps the transport open. No calibrate, verify, DDC, or LUT tool exists on this surface, so a remote agent cannot change display state through it.
- **Liveness status.** `_status_payload()` returns `ok`, `server`, `version`, and `protocol`. The version comes from `calibrate_pro.__version__`.
- **Deterministic readiness doctor.** `_doctor_payload()` wraps `build_doctor_report()` from `calibrate_pro/diagnostics.py`. The report is `schema_version` 1, probes no hardware, and reads no display identity. The doctor catches its own faults and records them under `diagnostics`, so a broken report never fails the health probe.
- **Calibration target catalog.** `_targets_payload()` reads the preset builders in `calibrate_pro/targets`. It returns 6 profiles (each with an `hdr` flag), 8 white points (each with a CCT), 8 luminance standards (peak nits plus `hdr`), 9 gamma/EOTF presets, and 8 gamut presets (each with a `wide_gamut` flag). The profiles are sRGB Web Standard, Rec.709 Broadcast, DCI-P3 Cinema, HDR10 Mastering, Photography, and Film Grading (`get_profile_presets` in `calibrate_pro/targets/__init__.py`).
- **Characterized panel catalog.** `_panels_payload()` reads `PanelDatabase` (`calibrate_pro/panels/database.py`) and returns a count and a sorted list, each entry carrying `key`, `name`, `manufacturer`, and `panel_type`. The count is 58, what `list_panels()` returns at this revision.
- **Per-panel stored primaries with an estimate label.** `_panel_info_payload()` returns one panel's native red, green, blue, and white xy coordinates. It attaches the string `"characterized estimate for an attached unit, not a live measurement"`, so a reader cannot mistake a database value for a measurement of the panel on the desk.
- **Evidence-labeling boundary carried onto the lane.** The panel-info estimate label and the doctor's `device_presence: "not_probed"` field (set in `_capability`, `calibrate_pro/diagnostics.py`) keep database-derived and library-derived values from reading as observations. This mirrors the product's own boundary between measured and estimated values.
- **Capability probe that opens no device.** `_capabilities_report()` checks Windows library exports (`Dxva2.dll` for DDC/CI, `Mscms.dll` for ICC, `Gdi32.dll` for gamma ramp) and the presence of the `hid` module for a colorimeter. Each result reports `software_supported` while `device_presence` stays `not_probed`; the check reads a symbol table, it does not call a device.
- **PQ transfer-function self-check.** `_pq_report()` encodes 100 nits and decodes the known ST.2084 signal against fixed tolerances, so a regression in the transfer math surfaces in the doctor's `ok`.
- **Frozen-build resource audit.** In a packaged build, `_resource_report()` verifies the action manifest, the `dwm_lut` runtime files, the component policy, and the third-party notices are present. In a source or pip install the resource section is marked not applicable.
- **Remediation guidance.** `_remediation()` names the pip command that repairs a missing dependency, or, for a packaged build, reports that pip cannot repair it and the release must be reinstalled.
- **Health-tool contract match.** The server exposes `calibrate-pro.status` and `calibrate-pro.doctor`, the first two names the Flywheel probe looks for (`_probe_lane` in `harness/lanes.py`), so the roster gets a live handshake. A lane with no matching health tool reads `stale`.

## Stepwise usage

### As a standalone tool

1. Install from source. Clone the `calibrate-pro` repo and run `pip install -e ".[all]"`. Requires Python 3.10+ and Windows 10/11. The developer wheel is what answers `mcp`; the frozen Windows binary does not.
2. Serve the read-only surface: `calibrate-pro mcp` (or `python -m calibrate_pro.main mcp`). It reads JSON-RPC 2.0 lines from stdin and writes responses to stdout.
3. From an MCP client, send `initialize`, then `tools/list`, then `tools/call` with one of the five tool names. `calibrate-pro.panel-info` takes a required `panel` key from `calibrate-pro.list-panels`.
4. Run the full calibration workflow in the window, not over the lane: `calibrate-pro gui` walks detect, method, preview, apply, verify, and save. A display change requires the preview and an explicit confirmation.

Note: the packaged binary `CalibrateProCLI.exe` declines `mcp`, `list-panels`, `info`, `hdr-status`, `plugins`, and `tray` with exit code 2, since those are developer-wheel commands (README Usage, `packaging/frozen-features.json`). Serve the lane from a pip or source install.

### As a Flywheel lane

Flywheel launches the MCP server for you; a user does not spawn it by hand.

1. Install the lane. From the Flywheel harness, `install_lane("calibrate-pro")` runs `pip install calibrate-pro`; `profile="source"` installs the `public/calibrate-pro` checkout editable. The source profile is the verified path at this revision (see the bound on package distribution below).
2. Check health. `lane_status("calibrate-pro")` in `harness/lanes.py` resolves the runtime and, with `probe=True`, spawns `calibrate-pro mcp` and calls the `calibrate-pro.status` health tool; the roster reports live / declared / missing / stale.
3. Call a tool. Flywheel routes a call through `call_lane_tool("calibrate-pro", "calibrate-pro.list-targets", {})` in `harness/lane_caller.py`, which resolves the launch and speaks MCP to the child. Calibrate Pro sits at tier T1 (open access, read-only).
4. Read identity in the desktop app. The `calibrate-pro` lane card (`desktop/lib/models/lane_identity.dart`) renders title "Calibrate Pro" and surface "display catalog + readiness doctor".

## Piecewise reference

### MCP tools (`calibrate_pro/mcp.py`)

Five tools, all read-only and device-free. `status` and `doctor` are the health surface; the three catalog tools return bundled data.

| Tool | What it returns |
| - | - |
| `calibrate-pro.status` | Liveness and identity: `ok`, `server`, `version` (from `__version__`), `protocol`. |
| `calibrate-pro.doctor` | The status fields plus the tool list and the `schema_version` 1 installation and capability report. No device probe. |
| `calibrate-pro.list-targets` | The calibration target presets: profiles, white points, luminance, gamma/EOTF, gamut. Pure data. |
| `calibrate-pro.list-panels` | The characterized panel catalog: a count and, per panel, `key`, `name`, `manufacturer`, `panel_type`. |
| `calibrate-pro.panel-info` | One panel's native primaries (red, green, blue, white xy) plus the estimate label. Requires a `panel` key. |

### Doctor report fields (`calibrate_pro/diagnostics.py`, `build_doctor_report`)

| Field | Meaning |
| - | - |
| `schema_version`, `version`, `distribution_mode` | Report schema id, package version, and `frozen` or `python`. |
| `dependencies` | Each runtime dependency, the distribution that provides it, the extra that installs it, and whether it is installed. |
| `qt` | Whether the PySide6 stack (QtPy, PySide6-Essentials, shiboken6) is present. |
| `resources` | Frozen-build resource presence (action manifest, dwm_lut files, component policy, notices); marked not applicable off a frozen build. |
| `pq` | The PQ encode/decode self-check against fixed tolerances. |
| `capabilities` | Per capability, `software_supported`, `device_presence` (always `not_probed`), the probe kind, and detail. |
| `remediation` | The repair command for a missing dependency, or a note that a packaged build must be reinstalled. |
| `ok` | True only when dependencies, Qt, resources, and the PQ check all pass. |

### Target catalog shape (`_targets_payload`)

Profiles carry `name`, `description`, and `hdr`. White points carry `preset` and `cct`. Luminance carries `standard`, `peak_nits`, and `hdr`. Gamma carries `preset` and `hdr`. Gamut carries `preset` and `wide_gamut`. Counts at this revision: 6 profiles, 8 white points, 8 luminance standards, 9 gamma presets, 8 gamut presets.

### Panel catalog shape (`_panels_payload`, `_panel_info_payload`)

`list-panels` returns `{count, panels[]}` with `key`, `name`, `manufacturer`, `panel_type` per entry. At this revision the count is 58, spread across QD-OLED (17), IPS (20), WOLED (10), Mini-LED (4), VA (3), Nano-IPS (2), and OLED (2). `panel-info` adds the native primaries and the estimate label for one key.

### What the lane does not expose

The measurement and actuation names live in the CLI and the window, never on the MCP surface. `calibrate-pro` declines `calibrate`, `native-calibrate`, `refine`, `restore`, and related names in `calibrate_pro/main.py` and routes them to the preview-and-confirm workflow. The MCP server declares none of them, and the CLI's set of declined names is what the packaging gate walks to prove none is reachable as a tool.

## Composition tutorial

### Which lane it is

Calibrate Pro is registered in `harness/lanes_registry.py`:

```python
"calibrate-pro": Lane(
    "calibrate-pro", "calibrate-pro", "calibrate-pro", ("mcp",), "pip", "1.1.0",
    "evidence-labeled display calibration: color-target and characterized-panel "
    "catalog + readiness doctor (read-only over MCP; actuation stays GUI-gated)",
    "calibration", source_repo="public/calibrate-pro", py_module="calibrate_pro.main"),
```

Organ `calibration`, role the read-only catalog and doctor surface. It launches with argv `["calibrate-pro", "mcp"]` (`resolve_mcp_command("calibrate-pro")`). Flywheel leaves it at the default tier T1 in `harness/lane_caller.py`: it is not listed in `LANE_MIN_TIERS` or `TOOL_MIN_TIERS`, so `required_tier` returns the T1 floor. That is correct for a lane that only reads, and it sits below the T2 actuation lanes (`local-model`, `relay`, `accountable-surface`).

Native wiring that is present and tested:

- Lane declaration: `harness/lanes_registry.py` (above).
- Expected-set test: `tests/test_lanes.py` lists `calibrate-pro` in the expected lane roster.
- Desktop card: `desktop/lib/models/lane_identity.dart` key `calibrate-pro`, title "Calibrate Pro", surface "display catalog + readiness doctor".
- Call path: `harness/lane_caller.py::call_lane_tool` resolves `resolve_mcp_launch("calibrate-pro")` and speaks MCP to the child.

Honest nulls at this revision:

- The lane registry pins expected version `1.1.0`. The `calibrate-pro` repo sets `__version__ = "2.0.0"`, and the MCP `status` and `serverInfo` both report `2.0.0`. The probe does not gate this lane on version (only `relay` does), so it still reads live. The two numbers disagree, and the registry figure lags the package.
- Package distribution over PyPI is unverified here. The README documents install from the Windows release build or from source. It does not document a `pip install calibrate-pro` from a public index. The source profile (`install_lane(..., profile="source")`) installs the `public/calibrate-pro` checkout editable and is the path confirmed at this revision.
- Emitted payloads other than the doctor report carry no versioned schema name. The doctor report has `schema_version` 1; the target, panel, and panel-info payloads are plain read-only JSON with a stable shape but no schema id. Calibrate Pro ships no `interop.json` contract file.

### What it consumes from peers

Nothing. Calibrate Pro reads only its own bundled data (the target presets and the panel database) and the host's installed libraries. It reads no sibling lane's output, so it is a leaf source in the composition graph.

### What it emits for peers

Read-only JSON another lane or agent can read:

- The `status` envelope: `ok`, `server`, `version`, `protocol`.
- The `schema_version` 1 doctor report: dependency, Qt, resource, PQ, capability, and remediation state, with an overall `ok`.
- The target catalog: profiles, white points, luminance, gamma, and gamut presets with their derived fields.
- The panel catalog and per-panel native primaries, the latter carrying the estimate label.

### Worked example: a readiness precondition before a color-critical run

This composition uses the real generic mechanisms (`call_lane_tool` and Crucible's subprocess measurement edge). No `compose_*.py` wires it today. Treat it as a proposed composition; no pipeline ships it yet.

1. A caller asks the calibration lane for readiness: `call_lane_tool("calibrate-pro", "calibrate-pro.doctor", {})` returns the `schema_version` 1 report, including `ok` and the per-capability `software_supported` and `device_presence` fields.
2. **Crucible** (organ `verification`) registers a falsifiable claim, for example "the workstation reports display calibration readiness". A `SubprocessMeasure` (`crucible.subprocess_edges`) runs a small command that calls `calibrate-pro.doctor` and maps `ok == true` to deviation `0.0` at tolerance `1.0`, `ok == false` to a deviation outside tolerance, and a missing or malformed report to unmeasurable.
3. `verdict_for` turns that into MATCH, DRIFT, or UNVERIFIABLE, with no model in the verdict. A caller can then gate a color-critical action (a render, a grade, a generated visual) on the MATCH.
4. **Forum** (organ `orchestration`) records the handoff in its causal ledger, so the readiness check that preceded the run is replayable.

The boundary holds here as everywhere in Flywheel. The doctor's `ok` attests that the software capability probe passed on this host. It does not attest that any attached display is measured or correct. The lane labels a database value as an estimate and a capability as `not_probed`, so a downstream verdict cannot overclaim.

## Status and bounds

- The Flywheel-facing surface is read-only and device-free: five catalog and doctor tools, no actuation. This is observed in `calibrate_pro/mcp.py` and enforced by the absence of any mutation tool.
- The full calibration product (detect, measured and sensorless methods, preview, apply, verify, save, reports, DDC/CI, ICC and LUT output) lives in the CLI session driver and the desktop window, not on the lane. macOS support is planned, not shipped (README Architecture).
- Version, panel count, and distribution carry the honest nulls listed above: registry `1.1.0` versus package `2.0.0`, a panel count of 58 from `list_panels()` where the README top line says 59, and a source-checkout install as the confirmed path.
- What this does not claim. A database-derived primary is an estimate of the unit on the desk; the lane never measures that unit. A passing doctor means the software capability probe passed on this host, so it does not attest to a calibrated display. A lane handshake reports liveness. It says nothing about whether the calibration is correct. Calibrate Pro is one independent tool in a family; Flywheel composes it as a lane and does not vendor it.