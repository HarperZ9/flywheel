# Verifying formalization and instrument work

Date: 2026-09-04

Scope: what the recent formalization and laboratory-autonomy publications ask of
a verification backend, what this repository could already carry, what was
missing, and what shipped on `feat/workstream-composition` to close the gap.

## Sources read

Every number below was taken from the source on 2026-09-04, not from
recollection. Confidence is stated per claim.

- Anthropic, "Formalizing Fermat's Last Theorem",
  <https://www.anthropic.com/research/formalizing-fermats-last-theorem>.
  Linked from it: the repository at <https://github.com/anthropics/fermats-last-theorem>,
  the Imperial College blueprint at
  <https://imperialcollegelondon.github.io/FLT/blueprint.pdf>, the
  Darmon-Diamond-Taylor expository paper, and Prove2Me.
- Chen, Marwaha, Lu, Yuen, Peng, "Prove2Me: An Open Collaborative Platform for
  Scaling Math Formalization", arXiv 2608.28433v2. Read as PDF, 15 pages.
- Anthropic, "Model Hardware Standard research preview",
  <https://www.anthropic.com/news/model-hardware-standard-research-preview>,
  announced 2026-08-27, begun with HHMI Janelia Research Campus.

### Facts carried forward

From the FLT page (high confidence, figures as printed):

- The run took 11 days and produced roughly 13 million lines of Lean.
- The final proof contains 29,500 intermediate theorems, out of 30,300 written.
- About 7% of non-boilerplate lines in the final proof came from attempts that
  failed on their first pass.
- The result is verified using Lean's three standard axioms.

From Prove2Me (high confidence, mechanisms stated in the paper):

- A theorem is a standalone immutable object, stated once, and it may carry many
  independent proofs.
- A proof submission is a Lean file declaring `solution` whose type matches the
  target exactly, containing no `sorry` and introducing no new axioms.
- A proof may import theorems that are still open. Such a proof is a
  proof-sketch and establishes its target conditional on the imports. Property 1
  in the paper: the parent is verified if all imported child lemmas are verified.
- Every statement and proof-sketch is persistent and cannot be edited after
  submission, which is what makes the conditional guarantee compose.
- Verification environments are each pinned to a specific Mathlib and toolchain
  version, fully isolated, and the submitting agent selects one.
- The audit surface is fixed in advance. Humans review the goal statement, the
  definitions it rests on, and the milestone lemmas. Agents introduce the
  remaining intermediate theorems freely.
- Sub-agent read-back: an independent auditor agent receives the Lean
  declaration and its dependent definitions without the original source, renders
  it back into ordinary mathematics, and a human compares that rendering against
  the source statement.

From the MHS preview (high confidence, figures as printed):

- A driver exposes a small primitive set, described in the preview as commands
  like read and write.
- A driver carries natural-language tags for machine characteristics not
  discernible from code, the example given being the weight of a robot arm.
- The driver generates a reference file specifying device capabilities,
  adjustable parameters, and enforced safety limits.
- Safety limits are enforced by the driver at the device. The preview quotes an
  operator saying excess laser power is not something the agent can reach.
- Agents reach devices through MCP, a command-line interface, and code files.
- Reported partner results include QuEra laser frequency recovery moving from
  58% to 99.3%, with recovery time falling from 150 s to 6 s; Carnegie Mellon
  dose-response runs 3x faster at R-squared above 0.98; and Tetsuwan Scientific
  measuring 9,143 dispenses at compiler precision 12% to 17% better than the
  manufacturer specification. These are vendor-reported, single-site, and carry
  no interval in the source.

## What these sources ask of a verification backend

Four requirements fall out, and they are the same four in mathematics and in the
laboratory.

1. **Composition.** A result at the top of a stack means something only in terms
   of what holds up every node beneath it. Prove2Me states this as Property 1.
   An assay result has the same shape. It means what it means given the
   calibration, the conversion, and the instrument that produced it.
2. **Environment as part of identity.** Prove2Me isolates environments so a
   result carries the context needed to reproduce it. MHS drivers carry a
   version and a calibration date. A verdict that does not name where it was
   decided is not reproducible.
3. **Disclosure of what is carried rather than checked.** FLT reports its three
   standard axioms. A proof-sketch names the open theorems it imports. An MHS
   run rests on a safety limit enforced somewhere else. All three are the same
   move, which is to name the unchecked thing inside the record.
4. **A bounded human audit surface.** Nobody reads 29,500 theorems. The audit is
   fixed to a curated core, and the machinery has to make the rest safe to
   delegate.

## What this repository already had, and what was missing

Strong per-artifact verification was already here. The Lean oracle treats the
kernel as the sole acceptance authority, refuses admitted holes before the
kernel runs, and audits the axiom footprint. Receipts carry Merkle inclusion
proofs. Domain packs cover units, currency rounding, and citation shape. The
evidence journey hash-chains a claim graph.

Composition was missing. `harness/evidence_journey.py` carries a claim DAG with
`depends_on`, but `project_journey` reports each claim's asserted verdict as
given, so a claim could read PASS while resting on a FAIL and nothing objected.
`harness/pipeline.py` is a scheduler and says in its own docstring that it is not
on the accept path. What was absent is the rule that turns a graph of checked
artifacts into a statement about the goal.

## What shipped

`harness/workstream.py` and the three modules beside it. The design rule is that
a standing is derived and never asserted.

Seven standings: `verified`, `refuted`, `blocked`, `undecided`, `unverifiable`,
`pending`, `assumed`. Only `verified` and `assumed` satisfy a parent. Anything
else under a node makes that node `blocked`, and the reason names which
dependency and what it was. A refuted node stays refuted whatever holds it up.

Identity folds the subtree. Each obligation digest folds in the digests of its
dependencies, so editing a lemma statement, or moving the environment a lemma
was checked in, moves the identity of everything above it. The goal digest is
the workstream id.

`does_not_prove` is computed from what settled. It cannot be authored by whoever
wants the record to read well, and it is never empty.

The runner never hands a checker an obligation whose dependency is unsatisfied.
For a stack of thirty thousand lemmas with one withdrawn near the bottom, that is
one proof-assistant invocation and a skip list. The receipt reports what was
checked and what was skipped, so a cheap run can be told apart from a run that
gave up early.

### Mapping the source mechanisms onto obligation kinds

| Source mechanism | Obligation kind | Environment string |
| --- | --- | --- |
| Closed Lean theorem | `lean` | `lean4:v4.9.0+mathlib:2026-08-01` |
| Open theorem imported by a proof-sketch | `assumed` | the board and revision it was stated on |
| The three standard axioms | `assumed` | the toolchain that admits them |
| Instrument reading under an MHS driver | `instrument` | `mhs:<device>/<driver or calibration>` |
| Driver-enforced safety limit | `assumed` | `mhs:<device>/driver-<version>` |
| Unit conversion inside one family | `dimensional` | `flywheel.units/v1` |
| Quantity against a stated interval | `arithmetic` | the instrument or pack that produced it |
| Statute or source text | `citation` | the corpus edition |

Two worked declarations ship under `examples/workstreams/`.
`formalization.json` is a milestone over one closed Lean theorem and one open
lemma carried as an assumption. `instrument.json` is a delivered dose over a
conversion, a plate-reader interval, a driver safety limit, and a calibration,
with the last two carried and disclosed. Run either with
`flywheel workstream run examples/workstreams/instrument.json`.

### Correspondence with Property 1, and where it stops

Property 1 and the workstream satisfaction rule are the same statement. An open
theorem imported by a proof-sketch behaves exactly like an `assumed` obligation.
It satisfies its parent, it is named in the footprint, and when it later closes
the parent resolves without being rewritten.

The guarantee behind them is not the same strength. Prove2Me checks a type match
in a shared Lean environment, so the import is verified by the kernel. A
workstream `assumed` obligation is bookkeeping. It records that something is
being carried and makes the carrying visible, and it does not establish that the
statement carried is the statement the parent needs. That reading belongs in any
use of this layer.

One consequence is worth stating. An assumption that names dependencies is
conditional on them, so if what it rests on is refuted, the assumption cannot
satisfy its parent. Otherwise a withdrawn lemma would launder itself through the
one node nothing checks. The generated-graph test in
`tests/test_workstream_run.py` found this against an earlier implementation, and
the rule now matches.

### The environment binding

Prove2Me pins each environment to a Mathlib and toolchain version. Since the
environment string is folded into workstream identity, a receipt naming a
version the check did not run in reads stronger than it is. The Lean checker now
confirms the pin. When the environment names a Lean version and the toolchain
that answered reports a different one, the obligation settles `unverifiable`
with both versions named. A refusal on the wrong toolchain is not evidence about
the pinned environment either, so the rule applies in both directions.

Only the Lean version is confirmed. A library revision written into the same
string is carried into the identity and is not checked against what was on the
path. An environment naming no version passes, and the receipt says on that row
that nothing pins the result.

## The cost argument, carried with its caveat

Prove2Me Table 1, reproduced as printed (high confidence, read from the PDF):

| Mission | Lines | Cost | Agents | Days |
| --- | --- | --- | --- | --- |
| Algebraic Combinatorics Textbook, centralized swarm | 130K | $100,000 | 30,000 | 7 |
| Exact Matrix Completion Paper | 81K | $600 | 9 | 16 |
| Sipser-Gacs-Lautemann Paper | 55K | $400 | 3 | 8 |
| Bandit Algorithms Textbook | 151K | $400 | 6 | 13 |
| Introduction to Linear Optimization Textbook | 17K | $200 | 4 | 7 |

The paper's own caveat has to travel with the table. It reports case studies and
not a controlled experiment. Corpora, difficulty, working patterns, and model
generations differ across rows. The two cost conventions are not comparable: the
first row is metered API inference estimated in another paper, and the rest are
flat-rate consumer subscriptions at roughly $200 per month per human
contributor. Any chart built from these numbers has to carry that sentence, and
the claim-language gate in this repository should refuse one that does not.

The mechanism behind the cost gap is a build-system fact, stated plainly in the
paper. Lean recompiles the entire downstream cone when a module changes, even
for a proof-only edit, so a monolithic repository serializes integration through
one merge queue. Atomizing statements removes the queue. The skip economy in
`run_workstream` is that observation applied to checking rather than compiling.

## What this does not do

- It does not establish that a statement says what a reader takes it to say.
  That is the faithfulness problem, and the Prove2Me answer is the sub-agent
  read-back with a human comparison. Nothing here implements read-back yet.
- It does not verify a library revision, only a Lean version.
- It does not talk to an instrument. There is no MHS driver client in this
  repository, so an `instrument` obligation needs a caller-supplied checker, and
  with none registered it settles `unverifiable` rather than passing.
- It does not host anything. There is no board, no submission queue, and no
  shared corpus. This is the composition rule and the runner for a stack that
  someone else assembles.
- It makes no claim about the FLT run or the Prove2Me missions. Those numbers
  are cited as design input, and nothing here has re-derived them.

## Next

1. A read-back obligation kind, where the checker is an agent given the formal
   statement without its source, and the receipt carries both renderings for a
   human to compare. This is the highest-value item, because faithfulness is the
   one requirement the layer currently records rather than tests.
2. An MHS driver checker, so an `instrument` obligation can settle against a
   reference file rather than being carried.
3. A library-revision probe, so the rest of the environment string binds the way
   the Lean version now does.
