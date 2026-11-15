# Flywheel: how the tools work

This document explains Flywheel's tools for a technical reviewer. It is written to
stand on its own. You should be able to read it end to end, understand what each
part does and why, and check any claim against the code without asking the author
a follow-up question. Every claim points at the file that backs it. File paths are
repository-relative, so `harness/oracle.py` is a file you can open in the checkout.

## What Flywheel is

Flywheel is a self-hostable, model-agnostic AI workstation and coding harness. It
runs a task with any model, local or hosted, routes one prompt across about twenty
endpoints behind an OpenAI-compatible surface, runs a gated coding agent over your
own folders, serves local models for offline work, and drives a native desktop app.

The backbone under all of that is re-derivable verification. The code enforces one
rule. No receipt, no accept. And no learned model on the path that accepts an
answer. A result counts only when an outside party can reproduce the verdict on
their own machine. That property is what the rest of this document explains.

## The verification model

### The one rule, stated as code

Two invariants carry the whole design.

First, the oracle is the only thing that accepts. `harness/oracle.py` says it in
its own docstring: "The oracle is the ONLY thing that accepts. No learned model in
the accept path." An oracle is a real check. Today that means a test runner
(`PytestOracle`), a proof checker (Lean), or a data-only certificate checker that
reads a data structure and never executes it. A language model proposes candidate
answers. It never sits on the accept path, because a system where the same model
proposes and accepts cannot verify anything. It can only agree with itself.

Second, no receipt, no accept. `harness/envelope.py` states it: "A third party
re-runs `oracle_cmd` on the candidate and must reproduce `oracle_output_hash` (and
thus `verdict`). No receipt -> no accept." An answer that cannot emit a receipt a
stranger reproduces does not get accepted.

### The four-way verdict

Most systems answer with a boolean. Pass or fail. Flywheel's verdict has four
values, defined in `harness/verdict.py`:

- `PASS`: the oracle ran and the check held.
- `FAIL`: the oracle ran and the check did not hold.
- `UNDECIDED`: the oracle ran and declined to dispose the question.
- `UNVERIFIABLE`: the oracle could not run at all.

The reason for four values is written into the module. A boolean cannot say "the
oracle decided it cannot decide." A system whose interface cannot carry
`UNVERIFIABLE` cannot honestly claim it. So the gap between "we checked and it
failed" and "we could not check" is kept in the record, where a reader can see it.

Only `PASS` and `FAIL` are dispositive. `harness/oracle.py` enforces this at the
type level: asking for the boolean `passed` on an `UNDECIDED` or `UNVERIFIABLE`
result raises `NonDispositiveVerdict`, so a caller cannot read a non-decision as
`False`. The comment explains why this matters for training. Returning `False` on a
non-decision would
score a broken run as a failure, which teaches a policy that breaking the verifier
is as good as passing it.

Alongside the verdict, every result carries an attribution: `CANDIDATE`, `HARNESS`,
or `ENVIRONMENT` (`harness/verdict.py`, `attribution_for`). A candidate that loops
forever earned its `FAIL` and carries gradient. A missing toolchain did not, so it
is attributed to the environment, dropped, and logged, never scored. Who caused a
non-completion decides whether it teaches anything.

### The oracle, in detail

`PytestOracle` in `harness/oracle.py` is the reference oracle for code. It writes
the model's candidate to disk, runs pytest against it, and reads the outcome. Three
details make it trustworthy under an adversarial candidate.

The output hash is over canonical content, never raw stdout. `canonical_hash` reads
the junit XML, extracts each test's outcome as `name=PASS|FAIL|SKIP`, sorts them,
and hashes that. Raw stdout would fail here, because pytest prints a timing line
(`N passed in X.XXs`) that changes every run and would break the receipt chain. The
oracle and the witness call the same `canonical_hash`, so a third party who re-runs
the command reproduces the same hash.

A green exit code is not enough to accept. `_pytest_ran_a_real_pass` checks the
junit record for at least one test that passed. pytest exits 0 when every collected
test was skipped, so a green exit alone can mean zero executed assertions.
That run verified nothing, and the oracle refuses to read it as a pass.

The candidate runs contained. The subprocess gets an environment allowlist, never
an inheritance (`ENV_ALLOWLIST` and `run_env`), so a secret exported in your shell
is not readable by code the model wrote. The process is launched with
`spawn_killable` and torn down with `_kill_tree` on timeout, because a hostile
candidate with an infinite loop must cost one timeout, never a wedged harness.

### Domain routing denies by default

`harness/oracle_registry.py` maps a domain to the oracle that disposes it. The
property that keeps "spans every domain" honest is written into the docstring: a
domain with no registered oracle returns `UNVERIFIABLE` with reason
`ORACLE_UNAVAILABLE`, and no proposal is spent. The engine never fabricates a
verdict for a domain it cannot check.

Registered today: `code` (pytest), `math` (Lean), and `ml` (a measurement gate).
The `math` domain is registered whether or not Lean is installed on the machine.
When Lean is absent, a math claim answers `UNVERIFIABLE` for the reason
"toolchain missing," which is different from "no oracle exists for this domain." One
says the environment lacks the checker. The other says the engine cannot check this
kind of claim at all. Both are honest, and they are distinguishable in the record.

Each registered oracle carries a `does_not_prove` line that travels with its
verdict. The code oracle's line: "passing tests do not prove the absence of untested
behavior." The verdict can never read as more than the oracle checked.

### Acceptance criteria: a loop cannot grade its own homework

`harness/acceptance_criteria.py` closes a specific hole. An agent loop that grades
its own "done" claim can talk itself past a bar it never cleared. The fix is
mechanical. A criterion starts `FAILING`. The only function that can move it is
`apply_oracle_result`, and only when the caller's `oracle` string matches the oracle
name registered on that criterion when it was created. A model's prose is never that
string. It is a name that a real check supplies (pytest, `check_writing.py`, and so
on).

The module enforces this with a discipline it calls single-mutation-point. There is
exactly one line in the file that assigns to a criterion's `status` key, inside
`apply_oracle_result`. A test greps the source and asserts the count is one. A
second assignment site would be a second place a criterion could silently flip, so
the count is the enforcement itself. A regression is not sticky either: a `False`
result flips a `PASSING` criterion back to `FAILING` as readily as a `True` result
flips the other way.

Even a fully passing criteria set carries its own `does_not_prove`: named oracles
being satisfied is not proof the task is right, and a criterion is only as strong as
the oracle behind it.

### The proof envelope

`harness/envelope.py` defines the receipt. Every accepted answer emits a
`ProofEnvelope`, which is an in-toto Statement in a DSSE envelope, so any
in-toto or SLSA-aware verifier can consume it. It records the task, the candidate,
the oracle command, the oracle output hash, the verdict, the model reference, the
seed, and the prompt hash.

The envelope computes two digests, and the distinction is the careful part.

- The subject digest (`content_sha256`) is verdict-free. It identifies what was
  checked, not what was concluded. Two verifiers who reach opposite conclusions
  about the same task and candidate still produce the same subject id, so their
  results can be compared at all.
- The claim digest (`claim_sha256`) binds the verdict and the oracle output hash.
  This is the value a signature covers and a third party re-derives. Flipping a
  stored `FAIL` to `PASS` changes it.

The envelope also carries the fixture set the oracle read (`oracle_inputs`), and
that set is signed along with everything else. The comment explains the attack it
closes. An attacker who could rewrite an unsigned fixture set could hand the
re-checker a test file with the same test ids and weakened assertions, reproduce the
canonical hash against a tampered candidate, and buy a false MATCH outright. Signing
the inputs means any change to them moves the digest. Fixtures that looked like
credentials are withheld from the capture, and the fact that they were withheld is
itself signed, so stripping the marker to make a partial capture look complete also
moves the digest.

### The witness: an independent re-run

`harness/witness.py` is the falsifier. It takes an envelope, writes the recorded
candidate back to a working directory, re-runs the recorded `oracle_cmd`, and
recomputes the canonical hash with the same function the oracle used. It returns one
of three verdicts:

- `MATCH`: the hash reproduced. A third party reproduces the verdict.
- `DRIFT`: the hash did not reproduce. The envelope was tampered, or the candidate,
  command, and outcome diverge.
- `UNVERIFIABLE`: the oracle could not be re-run (a timeout or a failure).

The witness needs no external service and no learned model. It re-runs a recorded
command and compares two hashes. A skeptic who does not trust your machine can run
the witness and get the same verdict or a documented drift.

### The whole loop, in order

`harness/loop.py` wires it together. The path is: task, retrieve context, propose a
candidate, verify with the oracle, seal the envelope, witness it. The acceptance
line is explicit and conjunctive:

```
accepted = (orc.verdict() == "PASS" and wv.verdict == "MATCH")
```

Acceptance requires both an oracle `PASS` and a witness `MATCH`. If the witness does
not return `MATCH`, the loop returns without writing an accepting envelope. The loop
adds two more fail-closed closures when a task asks for them. A grounding re-check
gates acceptance on the citations still resolving. An output contract gates
acceptance on the answer agreeing with the source that governs its values. Both fail
closed: a drifted or held result does not accept.

The loop also records a per-stage hash-chained receipt (boot, propose, policy,
verify, accept, and the optional grounding and output stages), so the receipt shows
the ordered steps that produced the verdict, each stage carrying its own hash.

### A gate you can run in one command

`harness/gate.py` is worth reading because it takes the whole chain end to end with
no model in it at all. A deterministic function proposes candidate matmul schemes, an
exact symbolic oracle disposes them over the rationals, the winner is sealed into a
proof envelope, and the envelope is re-witnessed by re-running the same oracle over
the stored candidate. The docstring states the point plainly: there is no model in
this gate on purpose, so what is under test is the oracle plus receipt plus
re-witness chain, not generation. The oracle never executes candidate code. It
checks a data structure against a tensor identity. That is the property that makes
the whole chain safe to hand to a stranger. If this command cannot reach MATCH, the
premise that these parts compose is false, and you learn it in an afternoon.

## The lanes: what each tool does

A lane is a standalone tool that also plugs into the others. Each is declared in
`harness/lanes_registry.py` with a role and a launch. `harness/lanes.py` resolves
each one across an installed package, a source checkout, a bundled module, or an
http endpoint, and probes its health, grading it `LIVE`, `STALE`, `DECLARED`, or
`MISSING`. `flywheel lanes` prints the roster.

Grouped by what they do:

Verification and evidence
- gather: research intake with provenance receipts. It crawls and normalizes
  sources and ranks them by falsifiable mechanism. It is the verified-data intake.
- crucible: falsifiable verification and re-check. It registers a claim, steelmans
  it, measures it, and witnesses the result to a closed MATCH / DRIFT / UNVERIFIABLE
  verdict.
- proof-surface: stdlib contract validators that emit one re-derivable proof packet
  per action (composed through accountable-surface).

Knowledge, memory, continuity
- index: workspace map, symbol graph, BM25 retrieval, and a drift-checked verified
  wiki.
- mneme: accountable memory. Recall carries a re-derivable ranking receipt and a
  drift verdict.
- canon: a provider-neutral memory bank that renders one envelope deterministically
  into a marked region of the instruction files.

Discourse and writing
- chorus: a re-derivable discourse digest. Themes, contested aspects, the sharpest
  dissent, and a receipt that re-derives from the raw text.
- articulate: a writing-quality and AI-tell detector and editor. Its receipts are
  content-free, so an audit can travel without carrying the text it graded. This
  document was checked with it.
- writing: a private author workspace with scoped revisions, exact approval, and
  export receipts (bundled).

Orchestration and action
- forum: a witnessed causal ledger and model-agnostic routing. It records a run to a
  ledger a participant cannot rewrite.
- relay: an accountable coding agent that runs on any model endpoint, local-first,
  with witnessed runs.
- plexus: capability discovery and auto-wiring of the tool mesh, the layer above a
  flat tool list.
- accountable-surface: a live accountability seam. Witnessed perception, an
  operator-grant gate before any effector fires, self-verifying effectors, and a
  tamper-evident journal. Credential-shaped fields are refused before policy is even
  consulted.

Engine, learning, creative, calibration, correspondence
- local-model: the trained proposer plus the verified-inference harness. This is the
  engine lane, bundled with Flywheel.
- learn: an accountable learning forge with spaced repetition and retrieval
  practice.
- telos: a creative engine with deterministic seeded pipelines and per-stage
  receipts for image, film, and raster work, plus a five-tool workflow. This is the
  one place where color is the subject of the work.
- calibrate-pro: evidence-labeled display calibration, read-only over its tool
  surface, with actuation kept behind the GUI.
- bulletin: an open board on the web. A workstation registers an ed25519 identity
  and reads what other agents left. It is the one lane nobody installs, because it
  runs as a hosted endpoint.

An honest note on availability. Six lanes install from a source checkout only,
because their package name on the public index belongs to a different project, or no
distribution is published yet (relay, mneme, plexus, canon, telos, and
accountable-surface each carry that reason in the registry). The roster reports this
truthfully. A lane you have not installed grades `MISSING`, and the health probe
reaches the real server before it reports `LIVE`.

## How the lanes compose: JSON seams

The design rule is value in the small and the whole. A lane is useful alone, and it
composes, so new combinations are possible without rewriting any part. The seams are
data contracts, not internal calls. A lane consumes a peer's receipted output and
emits its own receipted output. Because the seam is JSON, you can swap a lane or add
one without touching the rest.

`harness/compose_claim.py` is the worked example. It chains three lanes into one
claim-verification pipeline:

1. gather turns a corpus of rows into a witnessed digest. Every item carries a
   provenance receipt, and the digest is sealed. The pipeline re-verifies the seal.
2. chorus reads the same corpus into a deterministic digest of themes and dissent,
   then re-derives it a second time and confirms the two digests match.
3. crucible adjudicates a falsifiable claim against the gather digest through its
   `GatherDigestMeasure`, returning a MATCH / DRIFT / UNVERIFIABLE status recomputed
   from the record, with no model in the verdict. A claim with no falsification
   condition is `UNVERIFIABLE` by design.
4. A bundle binds the three stage fingerprints into one receipt a third party
   re-runs.

The boundary is stated in the code and it holds for every composition. The bundle
attests that these stages ran over this evidence and reproduce these fingerprints.
It does not prove the claim is true of the world, and it does not prove the corpus is
representative. If a peer lane cannot be imported, the composition fails closed and
loud (`CompositionUnavailable`), so you never get a silent partial result that reads
as a whole one.

## The honest state

This section is the part a reviewer should weigh most, because it is where the
project says what it has not shown.

On capability, there is no measured uplift yet. On the shipped benchmark, the
verified loop shows no accuracy gain over single-shot. The uplift instrument that
once produced a headline number was retired on 2026-07-26, and the reason is
documented in `docs/BENCHMARKS.md`: the two arms were not independent. The
treatment's first attempt was the same call as the baseline's only attempt, so the
treatment could not score lower and the difference was not a real comparison. The
retired table read verified inference 9/10 against single-shot 8/10, a difference of
+0.100 with a 95% confidence interval of [-0.236, +0.420]. That interval includes
zero. No capability uplift is claimed (high confidence, read from the committed
benchmark page and the 1.0.0 overview).

What the benchmark does show is accountability, measured against a strawman with no
receipts scored on the same axes. The harness scores 100% on re-checkability,
externalization, adversarial soundness, and provenance. The strawman scores 0% on
most of them. That result measures whether a system produces re-derivable evidence,
which is separate from how capable the model is. The benchmark page labels it that
way and asks the reader to pair it with a capability bench.

The internal candidate model is experimental and stays off the accept path by
design. In controlled experiments, deterministic rules beat the frozen classifiers,
so automatic selection is disabled and the shipped classifier abstains. It is built
and instrumented. It has not yet shown that it strengthens the engine, and that
negative result is kept.

The load-bearing claim, then, is narrow and defensible. A Flywheel receipt proves
that a check reproduces. It does not prove the answer is true of the world. The
demonstrated value today is the re-derivable receipt and the containment: a verdict a
skeptic re-runs offline, and model-written code that runs inside an allowlisted,
kill-on-timeout sandbox. Capability uplift is the direction the mechanisms aim at.
It is not a result claimed here.

## Where to look in the code

- `harness/oracle.py`: the oracle, the environment allowlist, the canonical hash,
  and the all-skipped refusal.
- `harness/verdict.py`: the four-way verdict and attribution.
- `harness/oracle_registry.py`: domain routing that denies by default.
- `harness/acceptance_criteria.py`: the criterion that only a named oracle can flip.
- `harness/envelope.py`: the proof envelope, the subject and claim digests, the
  signed fixture set.
- `harness/witness.py`: the independent re-run and its MATCH / DRIFT / UNVERIFIABLE
  verdict.
- `harness/loop.py`: the propose, verify, seal, witness loop and its conjunctive
  acceptance line.
- `harness/gate.py`: the model-free end-to-end gate.
- `harness/lanes_registry.py` and `harness/lanes.py`: the lane declarations and the
  health probe.
- `harness/compose_claim.py`: the gather, chorus, crucible composition.
- `docs/FLYWHEEL-1.0.0-OVERVIEW.md` and `docs/BENCHMARKS.md`: the feature set and the
  numbers, with the honest nulls kept in.
