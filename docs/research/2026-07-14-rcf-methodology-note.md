# RCF under the instrument lens (2026-07-14)

Reviewed: Stravica's Requirements Confidence Framework methodology
page. Frozen source sha256
`b93af8405c2323685a59503f882eaaae7917ede06efaa87b90aa3b90a2fe9840`
(store entity `ceaa3df981ed51bba9415467`), stravica.ai/rcf-methodology.

## What it is

A build-phase methodology for AI-assisted development: the slice from
an agreed PRD and TAD to a shipped feature, with claimed traceability
from business decision to line of code. Unit of work: the Functional
Build Spec. Cycle: Define, Build, Review, Test, Finalise. Structure: a
Y-shaped document chain, intent down one arm, architecture down the
other, converging at build. Discipline claim: one acceptance
criterion, one test suite, no negotiation. It names the right diseases
(AI drift, the trust gap between "an agent wrote code" and "the code
does what was asked").

## The convergence

This is the reconcile shape stated as method: the acceptance criterion
is a criterion the builder did not invent mid-build, the test suite is
the oracle, traceability is the receipt chain, and no-negotiation is
the no-rescue rule. Independent arrival at the same skeleton is
corroborating evidence for the skeleton.

## What is asserted that our machinery instruments

- **"One test suite, no negotiation" is only as strong as the suite's
  ability to refuse.** A vacuous test suite satisfies the rule
  trivially. RCF ships no falsifier; the admission discipline here
  does (oracle_can_fail: a derived stub must FAIL the suite), and the
  oracle-strength battery measures the floor after admission. This
  generalizes directly: run the non-solution battery against any
  FBS acceptance suite and the methodology's central promise becomes a
  measured number instead of a vow.
- **Traceability without hashes is testimony.** Business decision to
  line of code is exactly what a receipt chain does, but RCF's chain
  is documentary. Content-addressing the FBS, the acceptance
  criterion, and the passing test run turns the same chain into
  something a stranger can re-walk.
- **The criterion author and the builder can be the same party.** In
  team practice the FBS author often builds the FBS. RCF does not
  flag this; the robe test does. The fix is cheap: the acceptance
  suite's hash is sealed before the build starts, and the receipt
  shows whether it changed mid-build.
- **No published misses.** A methodology that never publishes a
  failure case has no calibration record. Not a robe (RCF issues no
  verdicts over others and claims no certification power), but not an
  instrument yet either: an unfalsified method.

## Worth adopting here

The Y-chain articulation is good: intent and architecture as separate
arms that converge at the unit of work is a cleaner statement of what
/api/forge's PRP already gestures at (goal in, checkable success gates
out), and the forge could name its two arms explicitly. Queue
candidate, small: PRP schema gains `intent_source` and
`architecture_source` fields, each content-addressed.

Queue candidate, larger and genuinely new: **acceptance-suite
admission for arbitrary projects**. The curator's gates and the
strength battery, today scoped to bench lanes, offered over any
repository's acceptance tests via a route: point it at a test suite
and get the measured answer to "can this suite refuse wrong code",
which is the number every RCF-shaped methodology assumes and none
measures.
