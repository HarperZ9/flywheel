# Crucible (Flywheel verification lane)

> Native feature documentation for Crucible as it lives inside Flywheel. Every claim below is bound to code in `public/crucible` or `public/flywheel`. Observed facts are stated plainly; anything proposed or in flight is marked. Crucible is an independent tool (`crucible-bench` on PyPI, license FSL-1.1-MIT) that Flywheel composes as a lane, not a subsystem Flywheel owns.

## One sentence

Crucible is Flywheel's verification lane: it turns a thesis into falsifiable claims, steelmans each one, measures each against a substrate oracle, and computes a MATCH / DRIFT / UNVERIFIABLE verdict that recomputes from a sealed record instead of resting on a model's assertion.

## One paragraph

Inside Flywheel, Crucible is the `verification` organ. A caller registers a thesis (claims, each paired with the observation that would refute it), independent adversaries propose the strongest test for every claim, the engine measures each against a substrate, and the weakest axis is refined across rounds. The verdict step is a pure function, `verdict_for` in `src/crucible/verdict.py`, with no model in it: a deviation within tolerance is MATCH, outside is DRIFT, absent or unmeasurable is UNVERIFIABLE, fail-closed. Every claim carries a sha256 receipt and every run writes a record, so a stranger holding the record can recompute the verdict and a tampered claim, measurement, or baseline is caught by re-hashing. Crucible consumes evidence from sibling lanes (Gather digests, Index verifications, Telos witnessed-artifact envelopes) through their JSON contracts and emits witnessed assessments that Telos and Forum surface and replay. It runs as a CLI, a Python import, and an MCP stdio server exposing 13 tools, and it ships with zero third-party runtime dependencies on the core.

## Feature list

Each item names the module that implements it.

- **Pure verdict spine.** `verdict_for(claim, measurement)` in `src/crucible/verdict.py` computes standing with no model in the step. It recomputes from `(deviation, tolerance)`, so a stored verdict row that disagrees is caught on recheck. Margin is `(tolerance - deviation) / tolerance`; `margin >= 0` is MATCH, below is DRIFT.
- **Honesty ladder, fail-closed.** The verdict function checks in a fixed order: a claim with no falsification condition is UNVERIFIABLE; a missing measurement or one binding to a different claim hash is UNVERIFIABLE; a deviation or tolerance that is None, non-finite, negative, or a non-positive tolerance is UNVERIFIABLE. UNVERIFIABLE never reads as holding.
- **Sealed-tolerance defense.** When a claim sealed its tolerance, a measurement carrying a different tolerance is UNVERIFIABLE (`src/crucible/verdict.py`, the `claim.tolerance` branch), so a verdict cannot be rescued by widening tolerance after the seal. Booleans are rejected in `_trusted` so `True` does not read as `1.0`.
- **Content-addressed registry with tamper detection.** `src/crucible/registry.py` gives every claim a sha256 receipt, re-verifies stored claims (MATCH / MISSING / CORRUPT), checks thesis seals, rejects duplicate ids with different seals, and refuses tampered theses.
- **One-command runs with cleanroom review packets.** `crucible run` (`src/crucible/run_cmd.py`) executes steelman, measurement, witnessed assessment, and on-disk recheck in one session; `--bundle DIR` writes a self-contained verifier packet (`spec.json`, `run.json`, `report.md`, `review.md`) with packet-relative paths.
- **Review-contract validation.** `crucible review` (`src/crucible/review_cmd.py`, `review_contract.py`) fails closed on missing files, extra context, a `spec.json` that drifted from the run record, or a `report.md` that no longer renders from `run.json`.
- **CI regression gate.** `crucible ci` (`src/crucible/ci_gate.py`, `ci_cmd.py`, `ci_report.py`) compares a registry's verified-latest verdicts against a sealed baseline, exits nonzero when any claim loses standing, and emits a deterministic PR-comment Markdown matrix. The baseline seals its own cells, so a hand-edited baseline is rejected on load. Added in 1.2.0.
- **Refine loop that names the weakest axis.** `crucible refine` (`src/crucible/refine.py`) grades each claim's measured margin, computes harmonic-mean cohesion, and re-measures across substrate rounds until the thesis is cohesively verified or the budget is spent. It reports the weakest claim rather than declaring a short thesis held.
- **Drift tracking.** `crucible drift` (`src/crucible/drift.py`) compares the latest two witnessed assessments and classifies each claim as held, moved, improved, or regressed.
- **LLM-as-judge with the model outside the verdict.** `JudgeMeasure` (`src/crucible/judge.py`) scores freeform output against a rubric behind an injectable backend; the judge produces a deviation once at the seam, the verdict still derives from `verdict_for`, and a judge that raises or returns garbage fails closed. Null by default. Added in 1.2.0.
- **Oracle recheck packs.** `crucible recheck` (`src/crucible/recheck_cmd.py`) lists descriptor-bearing measurements, writes `crucible.replay-template/1` templates, and validates `crucible.replay-pack/1` inputs against sealed rows. A privacy-bounded `crucible.replay-set/1` binding covers descriptor-bearing replays without exporting descriptorless rows. A missing or mismatched thesis id, assessment seal, or measurement seal fails closed before replay.
- **Typed missing-evidence explanations.** `src/crucible/explain.py` names, for each UNVERIFIABLE verdict, the exact evidence class it lacks and the concrete next action, derived from the same ladder as the verdict so the explanation cannot disagree with it. Added in 1.2.0.
- **Ill-posed measurement warnings.** `src/crucible/wellposed.py` flags measurement rows that are ill-posed; `crucible assess --strict` turns a warning into an error. Added in 1.2.0.
- **Batch and report.** `crucible batch` (`src/crucible/batch_cmd.py`) runs a manifest of theses into one registry; `crucible report` (`src/crucible/report.py`, `report_cmd.py`) renders deterministic Markdown for a witnessed assessment.
- **Creative measurement gate.** `crucible measurement-gate` (`src/crucible/measurement_gate.py`) verifies Telos creative/rendering measurement packets (`project-telos.measurement-layers/v1`) against explicit per-layer criteria.
- **Native MCP surface.** `crucible mcp` (`src/crucible/mcp.py`, `mcp_tools.py`) serves 13 tools over stdio. This is the surface Flywheel launches as the lane.
- **Publication gate.** `crucible export` (`src/crucible/gate.py`) exposes a public thesis contract; fenced material is refused at the edge.
- **Extensible measurement seams.** The steelman and measure stages are seams with a stable shape (defaults are Null, so nothing is proposed or measured and the verdict is UNVERIFIABLE). Shipped edges in `src/crucible/subprocess_edges.py`, `ecosystem_measure.py`, `telos_measure.py`, `judge.py`, `proof_measure.py`: `TableMeasure`, `SubprocessSteelman` / `SubprocessMeasure`, `TelosMeasure`, `GatherDigestMeasure`, `IndexMeasure`, `JudgeMeasure`, `ProofMeasure`. All edges map into the same `Measurement` object; the verdict step never changes.
- **Zero third-party runtime dependencies.** `pyproject.toml` declares an empty `dependencies` list; the core is standard library on Python 3.11+.

## Stepwise usage (how a user runs it)

**As a standalone tool.**

1. Install: `pip install crucible-bench`. This installs the `crucible` command and the `crucible` package (`import crucible`). For the newest commands and examples, work from a clone and `pip install -e ".[dev]"`.
2. See it run end to end: `python examples/demo.py` registers a three-claim thesis, assesses it, and shows tampering being caught.
3. Run a thesis through the full loop into a registry:
   ```bash
   crucible run examples/thesis-binary-search.json \
     --measurements examples/measurements-binary-search.json \
     --registry .crucible-registry
   ```
   Add `--json` for the machine record, `--substrate F` instead of `--measurements` to go through the table oracle, and `--bundle DIR` to write a review packet.
4. Validate a packet before handoff: `crucible review reports/my-run`.
5. Gate pull requests: `crucible ci .crucible-registry --write-baseline crucible-baseline.json` on a known-good commit, then `crucible ci .crucible-registry --baseline crucible-baseline.json --out crucible-ci.md` in CI.

**As a Flywheel lane.** Flywheel launches the MCP server for you; a user does not spawn it by hand.

1. Install the lane. From the Flywheel harness, `install_lane("crucible")` runs `pip install crucible-bench`; `profile="source"` installs the `public/crucible` checkout editable.
2. Check health. `lane_status("crucible")` (in `harness/lanes.py`) resolves the runtime and, with `probe=True`, spawns the server and calls its `crucible.status` health tool; the roster reports live / declared / missing / stale.
3. Call a tool. Flywheel routes a call through `call_lane_tool("crucible", "crucible.run", args)` in `harness/lane_caller.py`, which resolves the launch and speaks MCP to the child. Crucible sits at tier T1 (open access, no actuation).
4. Read results in the desktop app. The `crucible` lane card (`desktop/lib/models/lane_identity.dart`) renders the experiment bench and verdict matrix surface.

## Piecewise reference (each capability, what it does)

### CLI commands (`src/crucible/cli.py`)

| Command | What it does |
| --- | --- |
| `crucible run THESIS --measurements F \| --substrate F` | Full loop in one session; `--bundle DIR` writes a review packet, `--registry DIR` records and re-checks. |
| `crucible register / steelman / measure / assess` | The individual loop stages. |
| `crucible review BUNDLE` | Validate a cleanroom packet before verifier handoff. |
| `crucible refine CONFIG` | Rounds of substrate refinement toward cohesive verification. |
| `crucible drift DIR` | Classify claim movement between the latest two assessments. |
| `crucible ci DIR` | Regression gate against a sealed baseline; nonzero exit on any lost standing. |
| `crucible recheck DIR` | Inspect, template, or replay oracle measurement descriptors. |
| `crucible registry list\|verify\|stats\|search\|prune` | Registry operations, including `--require-witnessed-match`. |
| `crucible verdicts DIR [--verify]` | List or re-derive witnessed assessments. |
| `crucible report DIR` / `crucible batch MANIFEST` | Markdown reports; manifest runs into one registry. |
| `crucible export THESIS` | Publication-gated export; fenced material refused at the edge. |
| `crucible measurement-gate PACKET` | Verify a Telos creative measurement packet. |
| `crucible status / doctor / demo` | Operator envelope, readiness checks, demo pointer (`--json`). |
| `crucible mcp` | Serve the 13 tools over MCP stdio. |

Every command runs identically from a source checkout via `python -m crucible`.

### MCP tools (`src/crucible/mcp_tools.py`)

Thirteen tools, the surface Flywheel calls. `status` and `doctor` are informational and never render a verdict token; only tools that take a measurement emit MATCH / DRIFT / UNVERIFIABLE.

- `crucible.status` — the Project Telos operator-spine status envelope (`project-telos.flagship-action/v1`).
- `crucible.doctor` — readiness envelope; resolves each capability's live entry point and reports available / absent, not a verdict.
- `crucible.assess` — assess falsifiable claims against optional measurements; emits witnessed verdicts, ill-posed warnings, and missing-evidence explanations. `strict` errors on ill-posed rows.
- `crucible.run` — steelman, measure, assess, disk recheck, and optional report/run-record/bundle writes. Requires exactly one of `measurements` or `substrate`.
- `crucible.recheck` — inspect or replay oracle measurement descriptors from a registry.
- `crucible.measurement_gate` — verify a Telos measurement packet against criteria keyed by layer id.
- `crucible.review` — validate a cleanroom review bundle.
- `crucible.report` — render Markdown for a witnessed assessment.
- `crucible.batch` — assess a manifest of thesis jobs into a registry.
- `crucible.registry` — list / verify / stats / search / prune a registry.
- `crucible.drift` — compare the latest two verified assessments.
- `crucible.refine` — the deterministic refine loop over a substrate-round config.
- `crucible.verdicts` — list or re-derive witnessed assessments.

### Measurement edges (the seam vocabulary)

- `TableMeasure` — offline deviation against a provided substrate table, no model.
- `SubprocessSteelman` / `SubprocessMeasure` — configured commands over bounded JSON stdin/stdout, with timeouts, no shell strings, minimal environment, and output caps (`src/crucible/subprocess_edges.py`).
- `TelosMeasure` — consumes `telos.witnessed-artifact/v1` envelopes and re-runs the named verifier rather than trusting the carried certificate (`src/crucible/telos_measure.py`).
- `GatherDigestMeasure` — recomputes a Gather digest's seal from its receipts, then asks whether a selector matches a receipt; a verified digest with a match is deviation 0.0, without is 2.0, malformed or missing fails closed (`src/crucible/ecosystem_measure.py`).
- `IndexMeasure` — replays an `index.verification/1` record against a supplied graph pack, checks the pack hash, and reproduces the structural verdict (`src/crucible/ecosystem_measure.py`).
- `JudgeMeasure` — rubric-scored LLM judging behind an injectable backend, deterministic stub in tests, null by default (`src/crucible/judge.py`).
- `ProofMeasure` — a proof or type checker (Lean, Coq, a type checker, any command) as the oracle for formal claims: an accepted proof is MATCH, a rejected one DRIFTs, an absent or erroring checker is UNVERIFIABLE; the measurement binds the exact command and artifact hash so a stranger replays the identical check (`src/crucible/proof_measure.py`).

## Composition tutorial (how it plugs into Flywheel)

### Which lane it is

Crucible is registered in `harness/lanes_registry.py`:

```python
"crucible": Lane(
    "crucible", "crucible-bench", "crucible", ("mcp",), "pip", "1.2.0",
    "falsifiable verification + re-check (register -> steelman -> measure -> witness)",
    "verification", source_repo="public/crucible", py_module="crucible.cli"),
```

Organ `verification`, role the register-to-witness loop. It launches with argv `["crucible", "mcp"]` (`resolve_mcp_command("crucible")`). Flywheel floors it at tier T1 in `harness/lane_caller.py` (open access, no actuation): Crucible measures and re-checks, it does not change the world, which is why it sits below the T2 actuation lanes (`local-model`, `relay`, `accountable-surface`).

Native wiring is present and tested:

- Lane declaration: `harness/lanes_registry.py` (above).
- Expected-set test: `tests/test_lanes.py::test_registry_covers_the_expected_lanes` includes `crucible`, and `test_install_name_to_command_asymmetry_is_mapped` pins `install_name == "crucible-bench"`, `command == "crucible"`.
- Desktop card: `desktop/lib/models/lane_identity.dart` key `crucible`, with title "Crucible", a feature-first identity line, and surface "experiment bench + verdict matrix".
- Call path: `harness/lane_caller.py::call_lane_tool` resolves `resolve_mcp_launch("crucible")` and speaks MCP to the child.

Honest null: the frozen-gateway Python-lane payload manifest (`packaging/python-lane-payloads.jsonl` with `scripts/check_python_lane_payload_manifest.py`) is present only in a Codex worktree at this checkout, not on the main tree. A crucible row for the packaged desktop bundle is in flight, not landed. This affects the frozen build only; pip-installed and source-checkout runs probe live today.

### What it consumes from peers

Crucible reads sibling lanes through their JSON contracts, never their internals (`crucible.interop.json` declares this boundary):

- `crucible.thesis/1` and `crucible.measurements/1` — its own inputs (`src/crucible/commands.py`).
- `gather.digest/1` — a sealed Gather research digest as evidence (`GatherDigestMeasure`).
- `index.verification/1` — an Index structural verdict replayed against a graph pack (`IndexMeasure`).
- `telos.witnessed-artifact/v1` — a Telos artifact whose named verifier Crucible re-runs (`TelosMeasure`).

### What it emits for peers

- `crucible.assessment/1` — the witnessed assessment (`src/crucible/assess.py::Assessment.to_dict`).
- `project-telos.crucible.measurement-gate/v1` — the creative measurement gate result (`src/crucible/measurement_gate.py`).
- `crucible.thesis-export/1` — the public thesis contract (`src/crucible/gate.py`).
- `project-telos.flagship-action/v1` — the operator envelope (`src/crucible/flagship.py`), whose `next_actions` hand verified claims onward: `telos workflow` (carry verified claims into the shared room) and `forum ledger.summary` (record the verification handoff).

The interop boundary is deliberately narrow: Crucible exposes claim ids, criteria, verdicts, evidence hashes, and redacted references. It does not require raw prompts, private evidence, verifier internals, or full result payloads (`USAGE.md`, Boundary section).

### Worked example: Gather to Crucible to Telos/Forum

A two-lane composition, evidence intake feeding measured judgment.

1. **Gather** (organ `perception`) runs a research intake and emits a sealed digest, `gather.digest/1`: a list of receipts, each with a source hash, under one seal.
2. **Crucible** registers a thesis whose claim carries a falsification condition, for example "receipt X with sha256 abcd... exists in the sealed corpus". A selector maps that claim to the receipt fields.
3. `GatherDigestMeasure` recomputes the digest's seal from its receipts. If the seal matches and the selector finds the receipt, it returns deviation `0.0` at tolerance `1.0`; if the receipt is absent, `2.0`; if the digest is malformed or the seal mismatches, deviation is None and the claim is unmeasurable.
4. `verdict_for` turns that measurement into MATCH (evidence present), DRIFT (evidence absent), or UNVERIFIABLE (seal could not be recomputed). `crucible run --bundle` writes the assessment and a cleanroom packet.
5. The `flagship-action` envelope's `next_actions` route the verified claim to **Telos** (surface it in the shared room) and **Forum** (record the handoff in its causal ledger). Anyone holding the bundle re-runs `verdict_for` and gets the same answer, and a tampered digest or claim is caught by re-hashing.

The same shape holds with **Index** in step 2 (`IndexMeasure` replaying an `index.verification/1` record against a graph pack) or with a formal claim (`ProofMeasure` running a proof checker). The intake lane and the oracle change; the verdict spine does not.

## Status and bounds

- `crucible-bench 1.2.0` covers the full loop, one-command runs, cleanroom review packets, oracle replay, registry operations, creative measurement gates, and the MCP bridge, plus what landed since 1.1.0: the CI regression gate, LLM-as-judge, missing-evidence explanations, ill-posed measurement warnings, and the MATCH-provenance gate.
- Test count: the packaged `README.md` states 330 tests; the current source checkout collects 361 (`python -m pytest --co`). The README figure lags the checkout.
- What this does not claim: exposition is not correctness, a receipt is not compliance, and a passing verifier is not semantic truth. UNVERIFIABLE is a first-class outcome, kept rather than smoothed over. Crucible is one independent tool in a family; Flywheel composes it as a lane and does not vendor it.
