# Coherence Membrane

*Native-feature documentation for Flywheel. Status labels below separate what is observed in code from what is proposed. This is a 0.1.0 alpha; APIs can still move.*

## One-sentence description

Coherence Membrane is the read-gate perception feature: it turns real local artifacts (files, PNGs, live screen captures, JSON, context records) into inert, re-derivable Observations carrying exact SHA-256 identity, dimensions, and a perceptual fingerprint, so an agent can ground on what actually happened instead of on its prior.

## One-paragraph description

A model's structural weakness is state-blindness: it reasons on source text and on its prior, not on the artifact in front of it. Coherence Membrane closes that gap on the read side. It perceives an artifact into a structured Observation with a full-width `identity_sha256`, witnessed dimensions, and a 64-bit perceptual hash, then compares a later observation against an operator-pinned baseline and returns a closed verdict of MATCH, DRIFT, or UNVERIFIABLE that never silently matches on difference. Live screen capture reaches the OS compositor through the Python standard library alone (`ctypes`), so it works across D3D, Vulkan, OpenGL, Metal, and software renderers with no third-party graphics stack. Every organ ships a self-test that re-derives its own claims and can fail, and machine-checked lattice proofs run on every test invocation to keep each adjudicator inside its verdict set. The package has zero runtime dependencies; the trust path is stdlib only (confirmed: `dependencies = []` in `pyproject.toml`). Inside Flywheel it is the perception seam consumed by the `accountable-surface` actuation lane, and it composes with the `proof-surface` write-gate through a shared JSON shape rather than a code dependency.

## Where it sits inside Flywheel (integration status)

**Observed.** coherence-membrane is registered as an `extra_source_repo` of the `accountable-surface` lane, not as a lane of its own. In `harness/lanes_registry.py` the `accountable-surface` Lane declares `extra_source_repos=("public/coherence-membrane", "public/proof-surface")`, which adds each sibling repo's `/src` to the lane's child `PYTHONPATH` so the actuation lane can import `coherence_membrane` at runtime. accountable-surface imports it directly:

- `world/sight.py` imports `pngview.decode_png/is_png/read_ihdr`, `ascii_view.ascii_view`, `phash.perceptual_hash`, and `color.srgb_to_oklab/delta_e_ok`.
- `surface.py` imports `membrane.build_gate_request/decide`, `observation.Observation/Provenance/Status/sha256_hex`, and `organs.web.WebDocumentOrgan`.
- `reference.py` imports `observation.sha256_hex`.

**Bound limit.** It has no entry in the `LANES` dict and no row in `tests/test_lanes.py::test_registry_covers_the_expected_lanes`. It is therefore a native feature library reached through the accountable-surface lane, not a directly addressable Flywheel lane. The "become a native lane" wiring is in the composition section below, kept explicitly as proposed.

## Feature list (each item bound to code)

- **Stdlib-only native screen capture.** `grab_png` and `grab_raw` in `native_capture.py` ask the OS compositor for pixels through `ctypes`. `RawScreenCaptureSource` and `ScreenCaptureSource` expose the frame contract; `capture_available()` gates by platform. The raw path skips PNG encoding and computes the perceptual hash from BGRA bytes. Repo claim (moderate confidence, from the README): the raw hash is bit-identical to the encoded path.
- **Change-proportional continuity loop.** `run_continuity` with `ResourceBudget` and `ContinuityEvent` (`continuity.py`) hashes every frame for identity and pays for a full decode plus perceptual hash only on a real change. A throttled change reports `UNVERIFIABLE` with a note, never a dropped frame.
- **Perception organs.** The package exports these perception organ classes (`organs/*.py`): `VisualArtifactOrgan` (PNG identity, dimensions, dHash), `WebDocumentOrgan`, `AudioArtifactOrgan` (WAV loudness envelope), `RawFrameOrgan`, `StructuredDataOrgan` (canonical JSON identity), `RegionArtifactOrgan` (per-tile drift), `AsciiViewOrgan`, `BrailleViewOrgan`, `ColorQuantizeOrgan` (OKLab palette), `ContourViewOrgan` (marching-squares vectors), and `CaptionOrgan`. The README headlines 16 perception organs; the public package exports 11 perception organ classes (the count difference is view granularity, moderate confidence). Each organ carries a `selftest()` that re-derives its claims (`organ.py`: `Organ`, `Check`, `SelftestResult`, `run_selftests`).
- **Deductive verifier organs (six).** `PropositionalVerifierOrgan`, `QuantityVerifierOrgan`, `DistributionVerifierOrgan`, `CrossCheckVerifierOrgan`, `LinearArithmeticVerifierOrgan`, and `GraphVerifierOrgan`. A model proposes a claim; a deterministic oracle returns a certificate. An undecidable claim yields UNVERIFIABLE, never a guess.
- **Three-rung baseline memory.** `Baseline`, `BaselineEntry`, `BaselineVerdict` (`baseline.py`): byte identity, then canonical (normal-form) identity, then perceptual distance. Reformatted-but-equivalent JSON is a MATCH; a changed value is a DRIFT. `save`/`load` persist drift across runs.
- **Agent loop.** `AgentLoop`, `Goal`, `AdjustmentProposal` and the dispositions `CONVERGED`, `ADJUST`, `INDETERMINATE` (`agent_loop.py`) iterate make, look, compare, adjust, then route the one consequential commit through the write-gate against the authorized baseline.
- **Consequence mediation.** `LiveMembrane` and `LiveDecision` (`live.py`) tie capture, baseline, and mediation together. `ConsequenceScope`, `DEFAULT_CONSEQUENTIAL`, and `creative_profile` (`scope.py`) define which verbs route to a gate (`publish`, `export`, `overwrite`, `spend`, `delete`, `send`, `deploy`); the operator can widen or narrow the set.
- **Tamper-evident provenance.** `ProvenanceGraph`, `ProvenanceNode`, `GraphVerdict`, `compute_binding` (`provenance.py`) form a hash-chained DAG of observations, actions, and gate decisions; altering a surviving node or edge breaks downstream binding.
- **Witness receipts.** `emit_receipt`, `verify_receipt`, `WitnessReceipt`, `ReceiptVerdict` (`receipt.py`). Each observation gets an anchor the operator can pin or sign out of band. With no anchor, verification returns UNVERIFIABLE by design.
- **Machine-checked safety laws.** `lattice.py` proves by exhaustive enumeration, on every `pytest` run, that each adjudicator stays inside its closed verdict set and that composing drift verdicts cannot launder a worse set into a better one (`prove_all`, `prove_lattice`, `ALL_LATTICES`).
- **Multimodal and temporal composition.** `perceive_composite` and `CompositeObservation` (`composite.py`) witness a frame, its audio, and its data as one instant with per-modality drift. `trace_events`, `EventTrace`, `DriftEpisode` (`events.py`) turn a continuity stream into drift episodes with peak distance and settle time.
- **External organ adapters.** `external_organs.py` maps sibling-tool JSON into native Observations: `emet_receipt_observation`, `raw_eye_observation`, `raw_health_observation`, `provenance_receipt_observations`, `external_composite`, `build_external_graph`.
- **Verified code compression.** `python -m coherence_membrane distill` (`distill.py`, `distill_cli.py`) accepts a smaller candidate for a source file only when the declared criterion survives (syntax, public API, optionally tests). Deterministic graders check; no model sits in the checking step.
- **Cross-implementation re-derivability.** A frozen conformance corpus (`conformance/vectors.json`) is re-derived by the Python reference and a Node.js core (`impl/js/`). JSON Schemas in `schemas/` pin the wire shapes. Repo-reported counts (moderate confidence, not re-run here): 16 conformance cases pass under both implementations, and the suite reports 914 passed with 3 skipped.

## Stepwise usage (how a user runs it)

Install from source (not on PyPI yet):

```bash
git clone https://github.com/HarperZ9/coherence-membrane
cd coherence-membrane
python -m pip install -e ".[test]"
```

Then, in order of increasing scope:

1. **Prove the organs before trusting them.** `python -m coherence_membrane selftest`. Exits non-zero on any failure. An unverified membrane is treated as net-negative, so this is the first step.
2. **Perceive an artifact.** `python -m coherence_membrane perceive frame.png`. Prints an Observation JSON with identity hash, dimensions, and status. Exit is advisory: non-zero if any observation could not be positively verified.
3. **Take one native screen grab.** `python -m coherence_membrane capture shot.png`. Prints `{"captured": ..., "width": ..., "height": ..., "bytes": ...}`. Returns 2 when capture is unavailable on the platform.
4. **Run the always-on loop.** `python -m coherence_membrane watch 30 --raw`. Emits one JSON event per frame with verdict, distance, throttled flag, and note. The `--raw` flag selects the encode-free fast path.
5. **Accept a compressed rewrite only if the criterion survives.** `python -m coherence_membrane distill --code --original mod.py --candidate mod_small.py [--tests tests.py]`.
6. **Re-derive the evidence.** `python -m pytest`, then `python conformance/run.py`, then `node impl/js/run.js`.

Capture and watch read the composited display output. Use them only on surfaces the operator owns or is authorized to inspect.

From Python, the smallest useful path is perceive, pin, check:

```python
from coherence_membrane import perceive, Baseline

obs = perceive(["frame.png"]).observations[0]
obs.data["identity_sha256"]           # exact, re-derivable
obs.data["width"], obs.data["height"] # witnessed dimensions
obs.data["perceptual_hash"]           # 64-bit dHash of decoded pixels

b = Baseline()
b.pin(obs)                            # the operator authorizes this state
b.check(perceive(["frame.png"]).observations[0]).verdict  # MATCH | DRIFT | UNVERIFIABLE
b.save("baseline.json")               # drift persists across runs
```

## Piecewise reference (each capability, what it does)

| Capability | Entry point | What it does |
| --- | --- | --- |
| Read API | `perceive`, `PerceptionSnapshot`, `default_organs`, `all_organs` (`perception.py`) | Reads paths or bytes into a snapshot of Observations. Inert: a test asserts the source bytes are unchanged. |
| Observation contract | `Observation`, `Provenance`, `Status`, `sha256_hex` (`observation.py`) | The witnessed record and its status enum. `UNVERIFIED` is a first-class outcome. |
| Perceptual hashing | `perceptual_hash`, `perceptual_hash_raw`, `hamming`, `compare_drift`, `DriftVerdict`, `MATCH`/`DRIFT`/`UNVERIFIABLE` (`phash.py`) | 64-bit dHash and the closed drift comparison. |
| PNG decode | `decode_png`, `is_png`, `read_ihdr`, `DecodedImage`, `PngDecodeError` (`pngview.py`); `encode_png` (`pngencode.py`) | Stdlib PNG decode/encode with fail-closed errors. |
| Baseline ladder | `Baseline`, `BaselineEntry`, `BaselineVerdict` (`baseline.py`) | Byte, canonical, then perceptual comparison against a pinned state. |
| Native capture | `grab_png`, `grab_raw`, `RawScreenCaptureSource`, `ScreenCaptureSource`, `capture_available`, `CaptureUnavailable` (`native_capture.py`) | Compositor capture via `ctypes`. |
| Continuity | `run_continuity`, `ResourceBudget`, `ContinuityEvent` (`continuity.py`) | Cheap identity per frame, full work only on change, self-throttling. |
| Perception organs | `organs/visual.py`, `audio.py`, `structured.py`, `caption.py`, `region.py`, `ascii_view.py`, `braille.py`, `contour.py`, `color.py`, `raw.py`, `web.py` | Sense-specific observers, each with a selftest. |
| Verifier organs | `organs/verifier.py`, `quantity_verifier.py`, `distribution_verifier.py`, `cross_verifier.py`, `linarith_verifier.py`, `graph_verifier.py` | Deterministic oracles that return a certificate. |
| Write-gate bridge | `build_gate_request`, `decide` (`membrane.py`) | Turns perceived state into a mediated gate request in the shared JSON shape. |
| Consequence scope | `ConsequenceScope`, `DEFAULT_CONSEQUENTIAL`, `creative_profile` (`scope.py`) | The verb set that routes to a gate. |
| Live loop | `LiveMembrane`, `LiveDecision` (`live.py`) | Continuous free perception, gate only on consequence. |
| Agent loop | `AgentLoop`, `Goal`, `AdjustmentProposal`, dispositions (`agent_loop.py`) | Iterate and route the consequential commit. |
| Provenance | `ProvenanceGraph`, `ProvenanceNode`, `GraphVerdict`, `compute_binding` (`provenance.py`) | Hash-chained DAG of observations, actions, decisions. |
| Receipts | `emit_receipt`, `verify_receipt`, `WitnessReceipt`, `ReceiptVerdict` (`receipt.py`) | Per-observation anchor for out-of-band pinning or signing. |
| Lattice proofs | `prove_all`, `prove_lattice`, `ALL_LATTICES`, `Lattice`, `LatticeProof` (`lattice.py`) | Machine-checked verdict-algebra laws on every run. |
| Composition | `perceive_composite`, `CompositeObservation`, `compare_composite` (`composite.py`); `trace_events`, `EventTrace`, `DriftEpisode` (`events.py`) | Multimodal instant and temporal drift episodes. |
| External adapters | `external_organs.py` | Map sibling-tool JSON into native Observations. |
| Memory and recall | `MemoryStore`, `MemoryRecord`, `recall`, `verify_fresh` (`memory.py`, `recall.py`) | Accountable memory with re-verification. |
| Distill | `distill_cli.main` (`distill.py`, `distill_cli.py`) | Accept a compressed rewrite only if the criterion survives. |
| CLI | `__main__.py` | `selftest`, `perceive`, `capture`, `watch`, `distill`. |

## Composition tutorial: which seam it is, and how it plugs in

### Which lane and seam

Coherence Membrane is the **perception seam** on the read side. Its natural role tag is `perception`, the same tag `gather` carries in the registry. Today it lives inside Flywheel as the perception library of the `accountable-surface` actuation lane (tier T2, because that lane actuates). accountable-surface performs the loop its desktop card names: perceive a target as structure, propose an action, pass an operator-loaded gate, act through a bounded effector, re-perceive to check what happened, and journal the whole path. Coherence Membrane supplies the two perceive steps and part of the gate-request shaping.

### What it consumes from peers

- Raw artifacts: file bytes, PNG bytes, WAV bytes, canonical JSON, and live screen frames.
- Sibling-tool JSON through `external_organs.py`: EMET verification receipts (`emet_receipt_observation`), RAW health and eye reports (`raw_health_observation`, `raw_eye_observation`), and provenance-sensorium receipts (`provenance_receipt_observations`). These become native Observations, so a peer's output enters the same re-derivable contract.

### What it emits for peers

- Observation JSON: `identity_sha256`, `width`/`height`, `perceptual_hash`, `status`.
- DriftVerdict: `MATCH`, `DRIFT`, or `UNVERIFIABLE`.
- WitnessReceipt with an operator-pinnable anchor.
- Gate requests via `build_gate_request` for a write-gate to adjudicate.

The seam is a shared JSON shape, not a package dependency. A read-gate is useful to specs that never act, and a write-gate is useful to agents with no eyes, so the two stay decoupled.

### Worked example: read-gate to write-gate inside accountable-surface

Coherence Membrane pairs with `proof-surface` (the write-gate) through the shared shape. The pattern accountable-surface runs is:

```python
from coherence_membrane import perceive, Baseline, build_gate_request, decide

# 1. Read-gate: perceive the current target and compare to the authorized baseline.
now = perceive(["target.png"]).observations[0]
baseline = Baseline(); baseline.load("baseline.json")
drift = baseline.check(now).verdict            # MATCH | DRIFT | UNVERIFIABLE

# 2. Shape a mediated request from the perceived state (the seam to the write-gate).
request = build_gate_request(observation=now, action="overwrite", baseline=baseline)

# 3. Write-gate: adjudicate. decide() is default-deny and advisory.
decision = decide(request)                     # allow | deny | needs-human, fail-closed
```

Inside Flywheel, accountable-surface composes exactly this: `world/sight.py` uses the perception primitives to read the target, `surface.py` calls `build_gate_request` and `decide` to route the one consequential action, and every step is journaled. A second lane plugs in cleanly here: `gather` (role `perception`, research intake with provenance receipts) can hand a corpus artifact to `perceive`, and the resulting Observation carries a receipt that `crucible` (role `verification`) can re-check, because all three share the receipt shape.

## Becoming a native standalone lane (proposed wiring)

The observed status is `extra_source_repo`, so the following is the gap to promote it to a directly addressable lane. It is modeled on the two registration patterns already in the tree.

**Pattern A, the chorus/satellite path (no MCP server required).** chorus is not a `LANES` entry either; it is surfaced through a bridge. To follow it:

1. Add `harness/coherence_bridge.py` that shells `python -m coherence_membrane` (for example `selftest`, `perceive`, `watch`) and returns the CLI JSON verbatim, with a named error when the CLI is absent, exactly as `harness/chorus_bridge.py` shells `chorus` and returns its digest.
2. Add gateway HTTP endpoints (for example `/api/perceive`, `/api/observe`) in `harness/gateway.py`, matching the `/api/discourse` handlers that dispatch into `chorus_bridge`.
3. Add a `LaneIdentity` card in `desktop/lib/models/lane_identity.dart` (title, identity, surface), matching the existing `accountable-surface` card.

**Pattern B, a full `LANES` lane (MCP server required).** The repo ships a CLI, not an MCP stdio server, so this path needs a new server module first:

1. Add a `Lane("coherence-membrane", ...)` to `LANES` in `harness/lanes_registry.py` with `role="perception"`, an `organ`, `source_repo="public/coherence-membrane"`, a `py_module` for the new MCP entry, and a `package_disabled_reason` (it is not on PyPI).
2. Update `tests/test_lanes.py::test_registry_covers_the_expected_lanes`, which asserts the exact lane set; without the new name the test fails.
3. Add the `desktop/lib/models/lane_identity.dart` card as in Pattern A.
4. If bundled into a frozen gateway, add an `EXPECTED_BUNDLED_LANES` descriptor in `harness/bundled_lane_expectations.py` (`source_repo`, `source_commit`, `source_manifest_sha256`, `descriptor_sha256`, `module`, `callable`, `health_tool`, `allowed_tools`), matching the `relay` payload manifest.

Pattern A is the lighter change and reuses the CLI as-is. Pattern B makes the lane directly callable over MCP but requires building and maintaining a server surface the repo does not yet have.

## Honest limits

- SHA-256 and dHash here are keyless self-consistency: re-derivable integrity, not tamper-evidence against an adversary who recomputes them. Anti-forgery needs the external anchor.
- A dHash is a coarse 64-bit fingerprint of low-frequency structure, not semantic understanding. Distance is advisory evidence.
- Capture reads the composited display output the operator can already see. It does not inject into, hook, or read another process's memory.
- Non-Windows capture backends are implemented to the API but unvalidated (repo-reported: Windows GDI validated live; macOS CoreGraphics and Linux/X11 unvalidated). Moderate confidence.
- This is a 0.1.0 alpha and is not on PyPI. The stated test and conformance counts are repo-reported and were not re-run for this document.
- Integration status is `extra_source_repo`, not a standalone lane. It is reachable through the accountable-surface lane, not by direct lane address.

---

*Coherence Membrane is one lane of an independent, evidence-first toolkit. Everything above is meant to be re-derivable from the repo rather than asserted; if a claim cannot be reproduced, that is a defect worth an issue.*