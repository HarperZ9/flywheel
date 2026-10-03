# Conflict transparency

[Coordinated disclosure](coordinated-disclosure.md) sets the timeline. This page
covers who controls the clock and whose interest each part of it advances.
Disclosure timing already has established practice. Making hidden conflicts
legible has much less, so Flywheel states its approach here.

The purpose is to show where a claim, a measurement, a timeline or a policy
position is shaped by an interest the audience cannot see. It alleges no bad
faith. It puts the structural pressure beside the claim so the audience can weigh
both.

## Where conflicts hide

- **Self-measured capability uplift.** The party that controls the disclosure
  timeline for a class of AI-assisted vulnerability research is often the party
  whose safety case, product launch or regulatory position depends on the
  measured number being low. Self-measurement without independent replay is a
  structural conflict. Publishing the corpus, the denominators and the replay
  procedure discharges it; asserting the number does not.
- **Timelines set by the party they protect.** When the affected vendor also
  built the assisting model, or sets the timeline alone, timeline length can
  track commercial sensitivity more closely than fix complexity. Publishing the
  four endpoints (report received, vendor acknowledged, fix shipped, advisory
  published) makes the gap legible.
- **Scoped bug bounties.** A program's public scope says which findings the
  vendor wants reported, and its exclusions say which it does not. Both are
  legitimate. Keeping the exclusions in fine print while the scope sits in the
  headline is the problem. A researcher's report and the vendor's disposition
  should travel together with the scope in effect at the time.
- **Evaluator access review.** A lab that reviews evaluators' access before their
  findings publish runs an operational control and a publication filter at once.
  Which findings survived the filter, and which evaluators were denied access,
  show the filter's shape.
- **Safety-team independence.** A safety team's veto power, publication
  independence and access to the shipping decision shape every safety claim the
  lab publishes. When those facts go unstated, the claim leans on them silently.
- **Regulatory advocacy and commercial interest.** A lab advocating a rule that
  raises barriers to entry benefits incumbents. A lab opposing a disclosure
  requirement protects an information asymmetry. Either position may be right on
  the merits. The practice is to publish the pairing: the rule advocated, beside
  the commercial or strategic interest it advances, in the same document.
- **Endorsement laundering.** Academic and civil-society endorsements spread
  through press coverage without the funding, compute or model-access
  relationships that shaped them. Publishing the relationship graph next to the
  endorsement gives it the weight it has earned.
- **Benchmark selection.** A lab publishes results on the benchmarks it chose to
  run. In aggregate, the ones it chose to skip say something about its expected
  weaknesses. Publishing the split between run and not run makes the selection
  legible.

This is the outward face of the
[neutral-evaluation rule](evidence-and-useful-work.md#neutral-evaluation-of-models-and-organizations),
which Flywheel applies to its own outputs first.

## What the practice produces, step by step

- **Receipts that extend upstream.** A measurement receipt already names the
  model version, corpus, denominators, controls and replay hash. It extends to
  name who ran the measurement, who funded it, the access arrangement it ran
  under and any review the finding received before publication.
- **A shared conflict-of-interest schema.** A machine-readable declaration that
  each measurement and each policy claim can carry: funder, model-access
  arrangement, employment relationships, commercial products in the measured
  class and regulatory positions in that class. A shared schema makes cross-lab
  comparison mechanical. Flywheel applies it to its own outputs first.
- **A disclosure timeline log.** For each coordinated disclosure, a public log of
  the four endpoints with dates, so a vendor's timeline behavior is visible
  across its history.
- **An independent replay corpus.** A corpus, with tooling, that any third party
  can run against a lab's shipped model to check the lab's uplift claim without
  lab-provided evaluation access. This removes the conflict at the measurement
  step, which is why it sits at the center of Flywheel's design.
- **Regulatory comment provenance.** A public log of who commented on which
  proposed rule, in what position, and which commercial or strategic interest the
  position serves. Flywheel's own comments go in first, so the standard is
  symmetric.
- **Cross-witnessing.** An independent party witnesses a published uplift or
  safety claim under a shared protocol before publication, and the witnessing
  gets its own receipt.

Several of these exist only in part today. Measurement receipts and replay are
the technical starting point. The shared schema, the timeline log and the comment log are
directions the practice will grow into, and none of them ships yet.

## Our own work first

A transparency practice that exempts its authors is a marketing claim. One whose
authors ship their own conflict declaration beside their first published
measurement is the beginning of a standard. Flywheel's development disclosure in
the README and its [independence record](../INDEPENDENCE.md) are where that
starts.
