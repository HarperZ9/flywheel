# Flywheel features: the composed flagship

Flywheel is one application that composes a family of formerly standalone tools into
native features. Each feature is a lane: it stands alone, and it plugs into the others
through published JSON seams. This page is the map, and each linked doc is the full
feature reference (description, feature list, stepwise use, piecewise reference, and a
composition tutorial).

The design rule: value in the small and the whole. A lane is useful by itself, and it
composes, so new combinations are possible without rewriting any part. Verification lives
at the seams: a peer emits a receipt a consumer re-derives.

## The feature docs

Verification and evidence
- [crucible](crucible.md): falsifiable verification and re-check to a closed MATCH /
  DRIFT / UNVERIFIABLE verdict.
- [gather](gather.md): research intake with provenance receipts; the verified-data intake.
- [proof-surface](proof-surface.md): stdlib contract validators and domain proof-packet
  wedges; one re-derivable proof packet per action (composed via accountable-surface).

Knowledge, memory, continuity
- [index](index.md): workspace map, symbol graph, and verified wiki.
- [canon](canon.md): provider-neutral memory bank and personality container.

Discourse and writing
- [chorus](chorus.md): re-derivable discourse digest (themes, dissent, receipt).
- [articulate](articulate.md): writing-quality and AI-tell detector and editor with
  content-free audit receipts.

Orchestration and action
- [forum](forum.md): witnessed causal ledger and model-agnostic routing.
- [accountable-surface](accountable-surface.md): witnessed perception, an operator-grant
  gate, self-verifying effectors, and a tamper-evident journal.
- [coherence-membrane](coherence-membrane.md): externalized perception organs into
  receipt-shaped observations (composed via accountable-surface).

More lane docs (telos, mneme, relay, plexus, learn, calibrate-pro, bulletin, writing, and
the bundled local-model engine lane) are being added; each lane is declared and health-
probed in the lane roster (harness/lanes_registry.py).

## How they compose: a worked example

The claim-verification pipeline (harness/compose_claim.py) chains three lanes through
their seams:

1. gather turns sources into a witnessed digest. Every item carries a provenance receipt,
   and the digest is sealed.
2. chorus reads the same corpus into a deterministic digest: themes, the sharpest dissent,
   and a receipt that re-derives from the raw text.
3. crucible adjudicates a falsifiable claim against the gather digest with an arithmetic
   MATCH / DRIFT / UNVERIFIABLE verdict, recomputed from the record, no model in the
   verdict.
4. A bundle binds the three stage fingerprints into one receipt a third party re-runs.

The bundle attests that these stages ran over this evidence and reproduce these
fingerprints. It does not prove the claim is true of the world. That boundary is the whole
point, and it holds for every composition. A receipt proves a check reproduces. It does
not prove the answer is correct.

## The general seam

A lane consumes a peer's receipted output and emits its own receipted output. gather emits
a digest that chorus, index, and crucible consume. crucible's GatherDigestMeasure consumes
a gather digest and turns it into a measurement. forum records the whole run to a witnessed
ledger. accountable-surface gates and journals any action a composition takes. Because the
seams are data contracts, not internal calls, you can swap a lane or add one without
touching the rest.

## See also

- [FLYWHEEL-1.0.0-OVERVIEW.md](../FLYWHEEL-1.0.0-OVERVIEW.md): the engine overview, the
  full feature set, and an install-to-first-verdict walkthrough.
