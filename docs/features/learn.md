# Learn (Flywheel lane: learning)

> Native-feature documentation for the `learn` lane as it lives inside Flywheel.
> Scope note: statements are marked observed (read from code in `public/learn`
> and `public/flywheel/harness`) or proposed (a change not yet in the code).
> Version claims track learn `1.6.0` (`src/index.mjs`, `package.json`) and the
> lane registry entry at that version.

## One sentence

Learn is Flywheel's learning lane: it turns the operator's own material into a
runnable study loop and drives course logistics for a credential, while it halts
at every graded step and writes a hash-chained receipt that keeps automated
work and the operator's own graded work in structurally separate channels.

## One paragraph

Inside Flywheel, learn is the education organ. It carries two engines over one
accountability spine. The tutor engine runs a study loop: it schedules spaced
review, builds retrieval prompts from claims the operator already wrote, tracks
where the operator keeps getting an objective wrong, gates objectives on their
prerequisites, and reports a mastery verdict computed only from the operator's
own scored practice attempts. The credential engine drives a declarative course
workflow through a browser and stops at every graded `assess` step, and at
consent, CAPTCHA, payment, and account creation, so the graded work stays the
operator's. The spine under both is small: a `witness` hash, an append-only
`Ledger` that recomputes, and a `gate` that denies any step kind it was not
told about. Learn is registered as the `learn` lane in
`harness/lanes_registry.py` (organ `learning`), reachable over MCP stdio, and it
sits in the flagship spine in `harness/gateway.py`. The core is Node standard
library with zero third-party runtime dependencies. The load-bearing rule is one
line: no command produces, hints, or auto-fills an answer to a graded
assessment, and `mastery()` reads witnessed attempts only, never a render, a
schedule, or a pending prediction. Observed.

## Feature list (each bound to code)

- **One-command study plan.** `learn tutor study <id> --now <t>` composes the due
  list, the ranked misconceptions, an interleaved study order, per-objective
  prerequisite readiness, and the mastery verdict into one plan, all from
  `session.attempts`. Observed: `src/tutor/study.mjs` (`studyPlan`),
  `src/cli.mjs`.
- **Mastery gate over witnessed attempts only.** `mastery()` marks an objective
  ready when it has at least `minAttempts` attempts (default 3) at or above the
  `threshold` accuracy (default 0.8), and the session ready when every objective
  is. It reads `session.attempts` and nothing else. Observed: `src/tutor/tutor.mjs`.
- **Spaced repetition by default.** An SM-2-lite / Leitner ladder
  (`[1,2,4,7,14,30,60]` days, indexed by the consecutive-correct streak) over the
  practice log; `tutor due` reports overdue objectives, most-overdue first. `now`
  is injected, so there is no `Date.now()` and every schedule is deterministic.
  Observed: `src/tutor/schedule.mjs`.
- **Opt-in adaptive per-item scheduler.** With `--enable-fsrs`, an FSRS-class
  scheduler tracks per-item difficulty, stability, and retrievability, decays each
  item on its own curve, and ranks the item most likely to be forgotten against a
  retention target. It is a scheduling hint. `itemState` never feeds the mastery
  gate, and a corrupt entry self-heals (clamped, or re-initialized) before it can
  ship a nonsensical interval. Observed: `src/tutor/fsrs.mjs`,
  `src/tutor/itemscheduler.mjs`.
- **Re-derivable schedule with a drift audit.** `tutor derive-schedule` replays the
  witnessed graded attempt log from a fresh state and compares the result field by
  field to the cached `itemState`. It returns MATCH, DRIFT (with a per-field diff),
  or NO_FSRS_LOG, plus a hash-chained ledger over the graded attempts. The
  log-derived state is authoritative, so a stale or tampered cache is caught rather
  than trusted. `--optimize` fits a per-learner initial-difficulty prior from the
  learner's own accuracy; it is advisory and does not move the verdict or the
  gate. Observed: `src/tutor/fsrsderive.mjs`.
- **Retrieval practice from the operator's own material.** `clozePrompts` blanks a
  salient span (a number, then a mid-sentence capitalized term, then the longest
  word) out of a claim the operator already wrote through `assist()`. It withholds
  the term and attaches a source (a cited URL or the assist content hash), so the
  operator retrieves from memory and checks afterward. It never adds an answer
  field. Observed: `src/tutor/retrieval.mjs`, `src/assist/assist.mjs`.
- **Deterministic interleave.** `interleave` mixes objectives with a seeded
  mulberry32 Fisher-Yates shuffle (no `Math.random`), so the same seed reproduces
  the same order. Observed: `src/tutor/retrieval.mjs`.
- **Misconception targeting.** `misconceptions` aggregates wrong attempts and their
  feedback per objective, ranked by count, so the next session prioritizes the
  weakest objective. It surfaces only what the operator already saw. Observed:
  `src/tutor/misconception.mjs`.
- **Predict-then-observe.** `recordPrediction` stores the operator's prediction as a
  pending attempt with `correct: null`; `scorePrediction` sets the verdict only
  after the operator compares it to a rendered observation, and throws on an
  out-of-range index or a non-pending attempt, so a real attempt is never
  overwritten and a typo index is never swallowed. A pending prediction counts as an
  attempt but never as correct. Observed: `src/tutor/predict.mjs`.
- **Self-explanation with a real check.** `explanationThesis` wraps the operator's
  own explanation into a crucible thesis; `gradeExplanation` buckets the returned
  verdicts into grounded (MATCH), shaky (DRIFT), and unverifiable, and fails closed
  on any unrecognized verdict string. Observed: `src/tutor/explain.mjs`.
- **Concept map with prerequisite gating.** Objectives are plain strings or
  `{id, text, requires}`. `learningPath` topologically sorts them and throws when
  the prerequisites form a loop; `readiness` unlocks an objective only when every
  prerequisite is itself mastered. Observed: `src/tutor/map.mjs`.
- **Proof-packet lessons.** `tutor prooflesson --packet <p.json>` validates a
  proof-surface-style packet and derives a frozen lesson: a scaffold that prompts
  the operator to derive the reasoning, retrieval questions built from the packet's
  own fields, and a verifier binding (verdict, `packet_id`, source hashes). The
  lesson verdict is copied from the packet verdict with no override path, a forged
  verdict enum is rejected, and a DRIFT or UNVERIFIABLE packet also yields a typed
  misconception record (contradicted, overclaim, or missing_evidence). Observed:
  `src/tutor/prooflesson.mjs`.
- **Re-verifiable receipts.** `tutor reverify` ignores a receipt's self-reported
  booleans and recomputes its own evidence: the hash chain must recompute (a
  break is typed CHAIN_BROKEN with the offending seq), and the mastery verdict must
  re-derive from the recorded practice under the recorded policy (VERDICT_MISMATCH
  otherwise). A receipt with no chained entries is UNVERIFIED, never verified.
  Observed: `src/tutor/reverify.mjs`.
- **Credential-logistics engine.** `learn run <workflow.json>` executes a declarative
  workflow and halts at every graded `assess` step, and at any `submit`, `fill`
  marked sensitive, cost, or irreversible step. The gate default-denies any step
  kind absent from the engine's own allowlist (`STEP_KINDS`); the workflow's own
  declared kinds never widen it. Observed: `src/accountability/gate.mjs`,
  `src/runtime/runner.mjs`, `src/workflow/schema.mjs`.
- **Two submission modes, neither of which touches graded work.** `manual` halts at
  each `submit`; `witnessed-auto` performs the `submit` under recorded operator
  authorization and stores a digest of the exact pre-submit page state. `assess`
  halts in both modes. Observed: `src/accountability/gate.mjs`,
  `src/runtime/runner.mjs`.
- **Hash-chained, tamper-evident ledger.** Every step is witnessed by a SHA-256
  content digest and appended to a `Ledger` whose each row hashes the previous
  hash plus the entry; `verify()` walks the chain and reports the first break.
  Observed: `src/accountability/ledger.mjs`, `src/accountability/witness.mjs`.
- **Credential receipt with separated channels.** `learn receipt` writes JSON,
  Markdown, and HTML that separate automated logistics, human assessments,
  witnessed-auto submissions, manual submissions, and aid visualizations into
  distinct sections, so a reader cannot mistake one channel for another. Observed:
  `src/receipt/receipt.mjs`.
- **Aid renders that cannot satisfy graded work.** `learn visualize` turns a concept
  into a telos scene-spec request, delegates the render over `LEARN_TELOS_CMD`, and
  files the result as an `aid-visualization` ledger entry tagged `provenance: "aid"`.
  The render is fail-closed (UNVERIFIABLE when no engine is configured) and never
  enters a graded receipt channel. Observed: `src/interop/telos.mjs`,
  `src/receipt/receipt.mjs`.
- **Assist wrapper that authors nothing.** `learn assist` takes the operator's draft
  and emits a content hash, heuristically extracted claims to verify, and cited
  sources, plus a crucible thesis and a gather manifest. It writes no content of its
  own. Observed: `src/assist/assist.mjs`, `src/interop/crucible.mjs`,
  `src/interop/gather.mjs`.
- **Runtime integrity self-check.** `learn doctor` re-derives ten integrity
  invariants at runtime (the assess gate, default-deny, ledger tamper detection,
  fail-closed render, render-independent mastery, the re-verifier failing on
  known-bad input, the proof-lesson pipeline, and the drift audit) and reports MATCH
  or DEGRADED. Observed: `src/doctor.mjs`.
- **Adapter pack, no graded logic anywhere.** A config-driven generic adapter plus
  named packs for Coursera, Udemy, LinkedIn Learning, edX, Credly, Microsoft Learn,
  NonprofitReady, and a self-paced fallback. Each pack is CSS-selector config and a
  `locateAssessment` that tells the workflow author which steps to tag `assess`.
  Observed: `src/adapters/lms.mjs`, `src/adapters/generic.mjs`.
- **Two drivers.** `FakeDriver` is offline and deterministic and records every call;
  `NativeDriver` attaches to a real browser over native-control and is imported
  lazily, so the CLI and the tests never require it. Observed:
  `src/actuation/driver.mjs`, `src/cli.mjs`.
- **Zero-dependency MCP surface.** `src/mcp.mjs` exposes the read and advisory tools
  over stdio JSON-RPC. The MCP surface never performs a real course action and never
  answers a graded step. Observed: `src/mcp.mjs`.

Honest null: the README lists fourteen MCP tools, but the current `src/mcp.mjs`
`TOOLS` array declares fifteen (it adds `learn_tutor_derive_schedule`). Treat the
prose count as lagging the code. The README also states 298 tests; the `tests/`
tree has grown past that figure since, so treat 298 as a floor; the current
count is higher.

## Stepwise usage (how a user runs it)

Learn runs the same whether or not Flywheel is present.

1. **Install.**
   ```bash
   git clone https://github.com/HarperZ9/learn.git
   cd learn
   node --test        # zero dependencies, nothing to build
   ```
   Or install the published release: `npm install -g @harperz9/learn`. The
   repository can run ahead of the npm publish; the repo is the source of truth.
   Node 20 or newer. Library use is available through the package exports
   `@harperz9/learn`, `@harperz9/learn/doctor`, and `@harperz9/learn/status`.

2. **Check readiness.**
   ```bash
   node src/cli.mjs status           # version, capabilities, integrity invariants
   node src/cli.mjs doctor           # re-derives every invariant; MATCH or DEGRADED
   ```

3. **Run the study loop.**
   ```bash
   node src/cli.mjs tutor plan mysession --topic "derivatives" --objectives "power-rule,chain-rule"
   node src/cli.mjs tutor record mysession --objective power-rule --prompt "d/dx x^3" --answer "3x^2" --correct true
   node src/cli.mjs tutor study mysession --now 2026-06-30T00:00:00Z
   node src/cli.mjs tutor mastery mysession
   ```
   `tutor study` is the one command to run first. It composes what is due, what the
   operator keeps missing, a mixed order, prerequisite readiness, and the mastery
   verdict, all from recorded attempts.

4. **Use the adaptive scheduler when you want retention targeting.**
   ```bash
   node src/cli.mjs tutor plan sess --topic "SC-900" --objectives "identity,compliance" --enable-fsrs
   node src/cli.mjs tutor record sess --objective identity --grade 3 --now 2026-06-30T00:00:00Z
   node src/cli.mjs tutor study sess --now 2026-07-15T00:00:00Z --use-fsrs --desired-retention 0.9
   node src/cli.mjs tutor derive-schedule sess          # re-derive the schedule from the log; MATCH/DRIFT
   ```
   Grade 0 to 4 (0 fail, 1 slip, 2 lapse, 3 review, 4 easy). `--now` is required
   whenever `--grade` is given. On a session created without `--enable-fsrs` the
   `--use-fsrs` flag falls back to the Leitner path.

5. **Emit and re-verify a study receipt.**
   ```bash
   node src/cli.mjs tutor study-receipt mysession --now 2026-06-30T00:00:00Z
   node src/cli.mjs tutor reverify mysession            # VERIFIED only if the evidence recomputes
   ```

6. **Drive a credential workflow, halting at every graded step.**
   ```bash
   node src/cli.mjs run examples/course.json --id run1     # FakeDriver by default
   node src/cli.mjs resume run1 --attest "completed Quiz 1 myself"
   node src/cli.mjs verify run1                            # chain ok, or the break
   node src/cli.mjs receipt run1                           # runs/run1.receipt.{json,md,html}
   ```
   Add `--native` to attach a real browser over native-control, and
   `--submit witnessed-auto` to authorize automated non-graded submissions. `assess`
   halts regardless of submission mode. See `docs/smoke.md` for an operator-run
   live-LMS walkthrough.

7. **Serve the lane to a host over MCP.**
   ```bash
   node src/mcp.mjs
   ```
   Inside Flywheel this launch is what the lane layer spawns; a user rarely runs it
   by hand.

## Piecewise reference (each capability, what it does)

### CLI verbs
Observed in `src/cli.mjs`.

- **Credential engine:** `run <workflow.json> [--id ID] [--native] [--url U]
  [--match M] [--submit witnessed-auto|manual]`, `resume <id> [--attest NOTE]
  [--submit ...]`, `verify <id>`, `receipt <id>`.
- **Operator spine:** `status`, `doctor`.
- **Authoring aid:** `assist <draft> [--out DIR] [--title T] [--crucible]
  [--gather]`, `visualize <concept.json> [--out DIR]`.
- **Tutor loop:** `tutor <plan|record|mastery|receipt|reverify|prooflesson|due|
  misconceptions|retrieval|explain|predict|score|path|study|study-receipt|
  derive-schedule> <id> ...`.

Each verb returns an exit code that carries meaning: `verify` exits non-zero on a
broken chain, `mastery` exits non-zero when not ready, `derive-schedule` exits
non-zero on DRIFT, and `reverify` exits zero only when every checked receipt is
VERIFIED.

### MCP tools
Fifteen tools, observed in `src/mcp.mjs` (`TOOLS`). The surface is read and
advisory: it reports, previews, and re-verifies, and the tutor plan and record
tools persist a study session, but no tool runs a live course action or answers a
graded assessment.

- `learn_doctor`, `learn_status` health and capability envelopes.
- `learn_verify`, `learn_receipt` re-check and read a saved run's ledger and
  receipt.
- `learn_dry_run` previews where a workflow halts under the Fake driver, touching
  no live site.
- `learn_tutor_plan`, `learn_tutor_record`, `learn_tutor_mastery` create a session,
  record a practice attempt, and read the mastery gate.
- `learn_tutor_due`, `learn_tutor_studyplan`, `learn_tutor_misconceptions` return
  the due list, the composed study plan, and the ranked misconceptions.
- `learn_tutor_reverify`, `learn_tutor_derive_schedule` re-verify emitted receipts
  and audit the FSRS schedule against the witnessed log.
- `learn_tutor_prooflesson` derives a lesson from a proof packet.
- `learn_visualize_dry_run` returns the telos scene-spec request that a render would
  send, rendering nothing.

### Library exports
Observed in `package.json` and `src/index.mjs`. The package exports are `.`
(`src/index.mjs`, currently the version string), `./doctor` (`doctor()`), and
`./status` (`status()`). Internal seams (the tutor modules, the ledger, the
receipt builder) are imported by path within the package.

### Composition seams (each fail-closed, present-only)
Learn reaches a peer engine over a configured command and never fakes a result
when the command is absent. Observed in `src/interop`.

- **telos render** (`LEARN_TELOS_CMD`, `src/interop/telos.mjs`) turns a concept into
  a `learn.telos.scene-request/v1` request and delegates the render. Every result is
  tagged `provenance: "aid"`; a missing engine returns UNVERIFIABLE and never throws.
- **crucible assess** (`LEARN_CRUCIBLE_CMD`, `src/interop/crucible.mjs`) turns
  assist-extracted claims into a `{title, disposition, claims}` thesis and optionally
  shells out for MATCH / DRIFT / UNVERIFIABLE verdicts.
- **gather run** (`LEARN_GATHER_CMD`, `src/interop/gather.mjs`) turns assist-extracted
  sources into a manifest and optionally mints one source receipt per source.
- **organ-bundle interchange** (`src/interop.mjs`) maps a learn credential receipt,
  a mastery verdict, or a ledger row into the proof-surface organ-bundle entry shape
  (`entry_id, organ_id, receipt_kind, status, payload_sha256, summary, payload_ref`),
  with `organ_id` fixed to `learn` and `receipt_kind` to `learn-receipt`.

## Composition tutorial: learn inside the application

### Which lane it is
Learn is the `learning` organ in the lane layer. Observed in
`harness/lanes_registry.py`:

```python
"learn": Lane(
    "learn", "@harperz9/learn", "node", ("src/mcp.mjs",), "npm", "1.6.0",
    "accountable learning forge (spaced repetition + retrieval practice)",
    "learning", source_repo="public/learn"),
```

It is one of the flagship spine entries (`SPINE` in `harness/gateway.py`), it is
declared as a flagship in `harness/superproject.py`, and it is a T1 (open access,
read-only proxy) lane in `harness/lane_caller.py`. Because it is an npm lane, the
lane layer spawns `node src/mcp.mjs` from a source checkout of `public/learn`.
Observed: `harness/lanes.py`, `tests/test_lanes.py`, `tests/test_lane_launch.py`.

### What it consumes from peers
- **A proof packet from a verification peer:** `tutor prooflesson` validates and
  reads a proof-surface or crucible packet (`version`, `packet_id`, `claim`,
  `verdicts.overall` in MATCH / DRIFT / UNVERIFIABLE, `sources[{ref, sha256}]`,
  optional `scope`) and turns it into a lesson. It reads refs and hashes only, never
  a source body.
- **Crucible verdicts:** the self-explanation grader consumes MATCH / DRIFT /
  UNVERIFIABLE verdicts (from a shelled crucible run, or supplied directly) and
  buckets them.
- **A telos render, when one is wired:** the visualize and predict-then-observe
  paths consume a telos render as an aid. Absent an engine, the render is
  UNVERIFIABLE and the study path continues.
- **Gather source receipts, when one is wired:** the assist path routes its
  extracted sources to gather for receipts.

### What it emits for peers
- **A credential receipt** (JSON, Markdown, HTML) whose hash-chained ledger a third
  party re-verifies, with logistics and human assessment in separate channels.
  Observed: `src/receipt/receipt.mjs`.
- **Tutor mastery and study receipts** that re-derive from their own recorded
  evidence through `tutor reverify`. Observed: `src/tutor/tutor.mjs`,
  `src/tutor/study.mjs`, `src/tutor/reverify.mjs`.
- **A proof-lesson receipt** bound to its packet's verdict and source hashes.
  Observed: `src/tutor/prooflesson.mjs`.
- **Organ-bundle interchange entries** in the shared cross-tool receipt shape, so a
  learn receipt composes into the same spine gather, crucible, index, and forum use.
  Observed: `src/interop.mjs`.
- **A crucible thesis and a gather manifest** from `assist`, which route claims to
  crucible and sources to gather. Observed: `src/assist/assist.mjs`.

### Where learn is already wired into Flywheel
Observed in `public/flywheel`:

- **Lane registry and spine** (`harness/lanes_registry.py`, `harness/gateway.py`):
  the `learn` lane entry, organ `learning`, and membership in the flagship `SPINE`.
- **Flagship declaration** (`harness/superproject.py`): learn declared as a flagship
  ("accountable learning forge (education flagship)", `public/learn`).
- **Tier floor** (`harness/lane_caller.py`): `learn` at T1, callable through the
  generic MCP lane proxy.
- **Desktop card** (`desktop/lib/models/lane_identity.dart`): a presentation
  identity (title `Learn`, surface "tutor + courses + mastery").
- **Manim bridge** (`harness/manim_lesson.py`, gateway route `/api/learn/animate`):
  turns an equation-bearing lesson into a runnable manimgl scene and reports an
  honest null (`renderable: false`) when manimgl is not installed. This is
  Flywheel-side pedagogy code that names the learn lane, stdlib generation only.

### Worked example: crucible to learn, both native lanes
Goal: take a verification peer's verified-claim packet and turn it into a lesson
the operator studies from, then re-check that the lesson binds to the verdict the
packet recorded.

```bash
# 1. A verification lane (crucible / proof-surface) emits a proof packet:
#    {version, packet_id, claim, verdicts:{overall:"DRIFT"}, sources:[{ref, sha256}]}
#    say the checks came out against the claim, so the verdict is DRIFT.

# 2. Learning lane: derive a lesson and a hash-chained lesson receipt from the packet.
node src/cli.mjs tutor prooflesson lesson1 --packet packet.json
#    -> verdict DRIFT, a scaffold that prompts the operator to derive the reasoning,
#       retrieval questions built from the packet's own fields, and a typed
#       misconception record (contradicted) about why the proof failed.

# 3. Re-verify the emitted lesson receipt from its own recorded evidence.
node src/cli.mjs tutor reverify lesson1 --file tutor/lesson1.prooflesson.json
```

The contract handed across the seam is the packet's `verdicts.overall` and its
source hashes. The lesson verdict is copied from the packet verdict with no
override path, and the derived lesson is deep-frozen, so a lesson claiming MATCH
from a DRIFT packet is impossible by construction; a forged verdict enum is
rejected at validation. `reverify` recomputes the lesson receipt's hash chain and
re-derives the bound verdict, so a hand-edited receipt fails closed. Observed:
`src/tutor/prooflesson.mjs`, `src/tutor/prooflessonverify.mjs`,
`src/tutor/reverify.mjs`.

On the emit side, the same run's receipt maps into the organ-bundle entry shape
through `src/interop.mjs`, so the lesson outcome carries into the shared receipt
spine that crucible, forum, and proof-surface read. The bundle attests that this
lesson was derived from this packet and reproduces these hashes. It does not
attest that the claim is true of the world, and it does not attest that the
operator learned the material; that is what the unaided retest and the mastery
gate are for.

## Native-lane wiring status

Learn is a registered, health-probed lane, so the lane-layer wiring exists.
Present and verified (observed):

- **Lane registry entry** in `harness/lanes_registry.py`, organ `learning`,
  version `1.6.0`, `source_repo="public/learn"`.
- **Expected-set test** in `tests/test_lanes.py`
  (`test_registry_covers_the_expected_lanes` includes `learn`), and
  `resolve_mcp_command("learn") == ["node", "src/mcp.mjs"]`.
- **Launch resolution** exercised in `tests/test_lane_launch.py`.
- **Desktop app card** in `desktop/lib/models/lane_identity.dart`.
- **Spine, flagship, and tier** membership in `harness/gateway.py`,
  `harness/superproject.py`, and `harness/lane_caller.py`.

Missing or in flight (proposed, not present on the working checkout's main):

- **No gateway route calls learn's own tutor or receipt tools.** The gateway
  academy runs a parallel Python learning loop (`harness/academy_pipeline.py`
  with `harness/explanation_gate.py` and the retention module over
  `harness/store.py`), a distinct implementation related to learn by philosophy,
  not the `@harperz9/learn` package. The learn lane is reachable only through the
  generic MCP proxy (`harness/lane_caller.py`) and the health probe
  (`harness/lanes.py`). A dedicated route that composes learn's mastery or
  study-receipt tools is proposed work.
- **No learn readiness receipt.** `scripts/` carries `run_gather_readiness.py`
  and peers, but no `run_learn_readiness.py`. Proposed.
- **Version lockstep.** The `1.6.0` string in `lanes_registry.py` is a
  hand-maintained constant. It must be bumped in the same change as learn's
  `package.json` version, or `lane_status` reports STALE against the installed
  package.

## Boundary

Learn is a learning aid. It is never a bypass. No command produces, hints, or
auto-fills an answer to a graded assessment. `assess` steps halt in both
submission modes; credentials, payment, CAPTCHA, and account creation halt for the
operator; the `mastery()` verdict is a function of the operator's own scored
practice attempts, never of a render, a schedule, or a pending prediction. Aid
renders are witnessed in their own channel and cannot satisfy a graded step. The
FSRS schedule is a hint that never feeds the gate, and its drift audit flags a
tampered cache as DRIFT. If any command can be made to cross that line, that is
the most useful bug report the tool can receive, and every such path has a
falsifiable test in `learn doctor`. Observed: `src/doctor.mjs`, `src/status.mjs`,
`README.md`.

Independent-project note: learn is its own repository (`@harperz9/learn` on npm,
`public/learn` in the workspace) with its own tests and release cadence. It
composes with Flywheel through published JSON seams and MCP; it does not absorb
the platform and is not absorbed by it.