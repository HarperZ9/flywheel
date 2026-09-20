# Accountable Surface (Flywheel lane)

Lane id: `accountable-surface` · organ: `actuation` · tier floor: `T2` · version 0.1.0 · license FSL-1.1-MIT

> Feature registry: `harness/lanes_registry.py` · tier map: `harness/lane_caller.py` · desktop card: `desktop/lib/models/lane_identity.dart` · downstream consumer: `harness/lesson_mappers.py` · source repo: `public/accountable-surface` (composes `public/coherence-membrane` and `public/proof-surface`)

## One sentence

Accountable Surface is the Flywheel lane where an agent reads a target as witnessed structure, proposes an action, passes an operator-loaded pre-execution gate, acts through a bounded self-verifying effector, and records the whole path in a tamper-evident journal.

## One paragraph

Most Flywheel lanes perceive, verify, or remember; this is the lane that acts on the world under accountability. An agent hands it a target and a proposed action. The surface perceives the target as a content-addressed structural observation (not a screenshot), routes the proposed action through the pre-execution gate loaded from the operator's grants, and only on a gate `allow` runs the action through an effector bounded at construction time. It then re-perceives the target, verifies the effect against the intended post-condition, rolls back a reversible action that failed verification, and journals every perception and decision into an append-only, hash-chained log. The gate is default-deny: with no operator grant loaded, nothing acts, and the model cannot supply its own authorization. Because it changes real state, the Flywheel governance gate classes the lane at tier `T2`, so a `T1`-classified run cannot call it. Its per-action `ActuationOutcome` records are the evidence the Flywheel learning loop reads to derive lessons when an allowed action diverges from its intent.

## Feature list (each bound to code)

- **Witnessed perception, not screenshots.** `AccountableSurface.perceive` (`src/accountable_surface/surface.py`) returns a coherence-membrane `Observation` carrying a provenance digest; the journal records subject, status, digest, title, and link count.
- **Default-deny pre-execution gate.** `AccountableSurface.propose` bridges to proof-surface through `coherence_membrane.membrane.build_gate_request` / `decide`; the MCP `propose_impl` (`src/accountable_surface/server.py`) returns `deny` with reason "no operator grant is loaded" when no grant is present. The model never provides authorization.
- **Filesystem actuation with rollback.** `FilesystemEffector` (`src/accountable_surface/effector.py`) writes only within a resolved root, backs up prior bytes, verifies the on-disk sha256 against the authorized plan in `verify`, and restores the prior content in `rollback`.
- **OS command actuation, allowlist only.** `CommandEffector` (`src/accountable_surface/os_effector.py`) runs allowlisted commands as argv with `shell=False` in a bounded working directory; an irreversible command escalates to needs-human.
- **Native web actuation without a browser.** `WebEffector` over `HttpDriver` (`src/accountable_surface/web_effector.py`, `http_driver.py`) navigates, fills fields by visible label, and submits forms on server-rendered pages using a stdlib HTTP and HTML backend, origin-bounded by construction.
- **JS-capable browser actuation, optional.** `BrowserEffector` (`src/accountable_surface/browser_effector.py`) clicks by accessible label and runs JavaScript; tests and offline demos use `FakeBrowserDriver`, and production can inject `PlaywrightDriver` through the lazily-imported `[browser]` extra (never a hard dependency).
- **Effector construction-bound as a second gate.** `RefusedActuation` (`effector.py`) is raised when a receipt does not match the plan, content does not match the preview, or the target sits outside the bound, even on a gate `allow`; the surface catches it and records `refused-by-effector` so the process keeps running.
- **Grounding cortex with honest "ungrounded".** `ReferenceCortex` and `ArxivSource` (`src/accountable_surface/reference.py`) score reference relevance for a subject and report `grounded` / `weak` / `ungrounded`; in `AccountableSurface.actuate` an ungrounded premise escalates to needs-human and holds the action.
- **Bounded autonomy under one grant.** `AccountableSurface.pursue` (`surface.py`) runs a sequence of `Step`s inside one grant envelope with no per-step prompt, and halts on the first step that is denied, escalated, refused, or fails verification.
- **Composed action certificate.** `action_certificate` (`src/accountable_surface/certify.py`) combines the gate, effect, and grounding verdicts through the coherence-membrane lattice meet: `REFUTED` absorbs, `UNVERIFIABLE` attenuates, and an unrecognized verdict maps to `UNVERIFIABLE` and never rounds up to a pass.
- **Tamper-evident durable journal.** `journal_chain.py` hash-chains each entry; `_replay` and `verify_journal` (`surface.py`) count parse failures (`replay_errors`) and chain breaks from edit, delete, or reorder (`journal_tamper`) separately and never conflate them.
- **Content-addressed self-view.** `AccountableSurface.interocept` (`surface.py`) returns a read-only observation of the session's own perceptions and decisions with a `journal_digest` that re-derives, so the self-report cannot silently drift; it appends nothing and grants no authority.
- **Live MCP server.** `src/accountable_surface/server.py` exposes `perceive`, `propose`, `session_journal`, `interocept`, plus `status` and `doctor`, through the `[server]` extra.
- **Shared world server.** `src/accountable_surface/world/` runs a stdlib `http.server` plus SSE surface that streams the real perceive-gate-act-verify loop to open browser tabs, with optional Claude or Ollama pilots.

Evidence base: `tests/` holds 233 test functions and `examples/` holds eight runnable transcripts (the README cites 223 tests, a figure that has since grown). CI runs the Python suite and the Node web tests with sibling checkouts of coherence-membrane and proof-surface.

## Stepwise usage

### As a Flywheel lane (recommended path)

1. **Have the source present.** The lane has no PyPI build, so clone `public/accountable-surface`, `public/coherence-membrane`, and `public/proof-surface` as siblings. coherence-membrane must include `WebDocumentOrgan`.
2. **Install from source.** `install_lane("accountable-surface", profile="source")` (`harness/lanes.py`) runs an editable install; the lane's `extra_source_repos` add each sibling's `/src` to the child process path, so the lane probes live even when the siblings are not separately installed.
3. **Check the lane is live.** `lane_status("accountable-surface", probe=True)` spawns the MCP server and calls its `status` tool; the roster marks the lane `live` only when `status` answers. `probe=False` reports install and runtime selection without spawning.
4. **Load an operator grant out of band.** Point `ACCOUNTABLE_SURFACE_GRANTS` at a JSON file holding one grant or a list. With none loaded, the gate is default-deny.
5. **Call it through the gateway with a tier.** `call_lane_tool("accountable-surface", "propose", {...}, governance_tier="T2")` (`harness/lane_caller.py`). A `T1` tier is refused with `governance_denied: true`, because the lane floor is `T2`.

### As a standalone MCP server

```
python -m pip install -e ".[server]"
python -m accountable_surface.server   # or the accountable-surface-server console script
```

Set `ACCOUNTABLE_SURFACE_GRANTS` to the grants file and, optionally, `ACCOUNTABLE_SURFACE_JOURNAL` to an append-only JSONL path so the witnessed self-view spans sessions.

### From Python (the full act-verify-rollback loop)

```python
from accountable_surface import AccountableSurface, FilesystemEffector

grant = {
    "authorization_version": "0.1",
    "receipt_id": "rcpt-example",
    "kind": "authorization-grant",
    "principal": {"id": "operator-1", "role": "operator"},
    "agent": {"id": "example-agent"},
    "intent": "write the report file",
    "scope": {"allowed_actions": ["fs.write"], "allowed_targets": []},
    "granted_at": "2026-06-19T00:00:00+00:00",
    "expires_at": "2030-01-01T00:00:00+00:00",
    "revoked": False,
}

surface = AccountableSurface()
out = surface.actuate(
    FilesystemEffector("sandbox"),
    target="sandbox/report.txt",
    content=b"written natively, verified by re-perceiving",
    authorization=grant,
)
print(out.acted, out.decision, out.verified)  # True allow True
```

With `authorization={}` the same call returns `acted=False, decision="deny"` and the file is never created. A faulty effector that writes the wrong bytes is caught at verification and rolled back.

## Piecewise reference (each capability, what it does)

| Capability | Entry point | What it does |
| - | - | - |
| Perceive | `AccountableSurface.perceive` | Reads a URL, path, or bytes into a witnessed `Observation` and journals it. |
| Propose | `AccountableSurface.propose` | Routes a proposed action through the gate and returns an advisory `ActionOutcome`; `executed` is always `False`. |
| Actuate | `AccountableSurface.actuate` | Runs perceive to preview to gate to act to re-perceive to verify, rolling back a failed reversible act. Returns `ActuationOutcome`. |
| Pursue | `AccountableSurface.pursue` | Runs a `Step` sequence under one grant envelope; halts on the first denied, escalated, refused, or unverified step. Returns `GoalOutcome`. |
| Ground | `AccountableSurface.ground` | Scores reference relevance through a `ReferenceCortex`; reports `grounded` / `weak` / `ungrounded`; journals, never trusts. |
| Interocept | `AccountableSurface.interocept` | Content-addressed read-only self-view with a re-derivable `journal_digest`. |
| Verify journal | `AccountableSurface.verify_journal` | Re-derives the hash chain and reports `chain_ok`, `tamper_count`, `replay_errors`, `entries`. |
| Filesystem effector | `FilesystemEffector` | Root-bounded, reversible file writes with backup and verify-by-re-perceive. |
| Command effector | `CommandEffector` | Allowlisted argv, `shell=False`, bounded cwd; irreversible escalates to needs-human. |
| Web effector | `WebEffector` + `HttpDriver` | Native form navigation, fill-by-label, submit on server-rendered pages; origin-bound. |
| Browser effector | `BrowserEffector` | JS-capable click-by-label and script; `FakeBrowserDriver` for tests, optional `PlaywrightDriver`. |
| Certificate | `action_certificate` | Composes gate, effect, and grounding into one verdict token via the lattice meet. |
| MCP tools | `server.py` | `perceive`, `propose`, `session_journal`, `interocept`, `status`, `doctor`. |
| World server | `accountable_surface.world.server` | Live SSE surface streaming the real loop to browser tabs, with optional model pilots. |

Verdict mapping in `certify.py`: gate `allow`/`deny`/`needs-human` maps to `VERIFIED`/`REFUTED`/`UNVERIFIABLE`; effect `pass`/`failed` maps to `VERIFIED`/`REFUTED`; grounding `grounded`/`weak`/`ungrounded` maps to `VERIFIED`/`UNVERIFIABLE`/`REFUTED`.

## Composition tutorial: the lane, its seam, and a worked example

### Which lane it is

It is the `actuation` organ in the lane layer. The registry entry (`harness/lanes_registry.py`) declares kind `pip`, command `accountable-surface-server`, module `accountable_surface.server`, source repo `public/accountable-surface`, and `extra_source_repos` `("public/coherence-membrane", "public/proof-surface")`. It is the only lane in the roster whose stated purpose is to change external state, which is why `harness/lane_caller.py` sets its tier floor to `T2` alongside `relay` (execution) and `local-model` (the engine). The membership assertion lives in `tests/test_lanes.py::test_registry_covers_the_expected_lanes`, and the human-facing card lives in `desktop/lib/models/lane_identity.dart` under title "Accountable surface", surface "grant gate + action journal".

### What it consumes from peers

- **coherence-membrane** (perception + certificate types), consumed at construction: `WebDocumentOrgan`, `Observation`, `Provenance`, and the `compose` lattice meet behind `certify.py`.
- **proof-surface** (the gate), consumed through the `build_gate_request` / `decide` bridge in `propose`.
- **Operator grants**, supplied out of band as JSON (`ACCOUNTABLE_SURFACE_GRANTS`), never by the model.
- **A reference cortex** (optional), which grounds an action premise; its own `ArxivSource` reaches arXiv over the stdlib. It does not depend on the `gather` lane for this.

### What it emits for peers

- **`ActuationOutcome` records** (`decision`, `verdict`, `acted`, `verified`, `rolled_back`, `before_digest`, `after_digest`, `grounding`, `certificate`).
- **A composed action `Certificate`** with a `VERIFIED` / `REFUTED` / `UNVERIFIABLE` verdict.
- **An append-only journal** that the desktop journal view and any auditor can replay and re-check.

### Worked example: plugging into the learning loop

The concrete cross-lane seam in the code is the Flywheel organizational learning loop. `harness/lesson_mappers.py::intent_outcome_lessons` reads a list of accountable-surface `ActuationOutcome` dicts and derives a lesson only on a divergence, defined by `_is_divergence` as `decision == "allow"` together with `verdict == "failed"` or `rolled_back is True`. A denied or needs-human action is not a divergence, because there the gate did its job.

End to end:

1. An agent (or the `relay` lane) drives accountable-surface through the gateway and actuates a plan under an operator grant.
2. The surface returns an `ActuationOutcome`. A clean run produces no divergence; a run where the gate allowed the action but the re-perceived effect did not match, or the action was rolled back, is a divergence.
3. The loop passes a batch of these outcomes to `append_intent_outcome_lessons(store, outcomes)`. For each divergence it seals a `KIND_INTENT_OUTCOME` lesson whose `source_refs` carry the outcome's `after_digest` (falling back to `before_digest`), so the lesson is bound to its evidence by hash. An outcome with no witnessed digest is skipped honestly.
4. The lesson lands in the `LessonStore`, where the pattern detector lifts confidence when the same class of divergence recurs. The mapper imports nothing from accountable-surface; it reads the dict shape as an adapter, so if the shape shifts the projection shifts with it.

This mapper sits beside two peers in the same file: `drift_lessons` reads `mneme`'s drift report, and `misconception_lessons` reads `learn`'s misconceptions output. All three feed one store, which is how actuation evidence from this lane composes with memory and learning evidence from the others.

### A note on the registration model

This lane is wired more deeply than a bridge satellite such as `chorus` (`harness/chorus_bridge.py`), which the desktop drives as an external CLI and reads verbatim without a `LANES` entry. accountable-surface is a full roster lane: it carries a registry `Lane`, a tier floor, an expected-set assertion, a desktop identity card, and a downstream consumer. The apt in-family comparison is the other source-checkout lanes such as `mneme` and `relay`, which also set `package_disabled_reason` and resolve live from a source checkout.

## Honest limits

- **Source-checkout only.** There is no admitted PyPI distribution; from a package-only workstation the roster reports the lane `MISSING`. It runs live only from a source checkout with both sibling repos present.
- **Advisory over the MCP surface.** The MCP `propose` tool returns a gate decision for the operator to enforce; the effector-driven `actuate` loop runs on the Python API path only. The world server runs the real loop within its own grant.
- **No static tool manifest.** The exposed tool set is declared by decorators and discovered at probe time, not asserted by a committed manifest.
- **Grounding is relevance scoring.** The cortex reports `ungrounded` when relevance is low, so it stays honest under weak evidence. A `grounded` verdict is a relevance judgment. It does not prove the premise is correct.

## License and provenance

FSL-1.1-MIT. Copyright (c) 2026 Zain Dana Harper. An independent project; source repo `public/accountable-surface`, composed with `public/coherence-membrane` and `public/proof-surface`.