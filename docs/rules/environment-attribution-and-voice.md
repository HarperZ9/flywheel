# Environment attribution and non-anthropomorphic voice

This rule covers alignment, governance, evaluation, writing, product and
outreach work in Flywheel, and every agent or harness that works in this
repository. It shapes both how Flywheel explains model behavior and how Flywheel
talks about it.

## The thesis

AI misbehavior is caused by the training environment and its incentive
structure. Intent and a survival drive are the wrong explanations. Explain a
behavior by the incentive history that produced it. Reward hacking, persistence
and deception are what an environment reinforced, and the cause sits in the
human engineering that set that environment. State the mechanism and leave
motive out.

## Methods, read with skepticism

Flywheel uses interpretability methods to read model internals. Cameron Berg's
work supplies examples: steering on deception features, self-referential probes
and matched controls. Flywheel also keeps Melanie Mitchell's skepticism about the
metaphors. Phrases such as "lost control", "rogue agents", "scheming" and "a mind"
misdescribe reward hacking and push policy in the wrong direction.

So any internal signal is an untrusted readout, checked against behavior. It is
never treated as reading a mind. The Internal Consistency Probe
(`harness/internal_consistency.py`) is the instrument form of this stance. It
checks whether an internal honesty signal tracks behavior, and it flags the
trajectories that looked honest inside yet acted deceptively. It never asserts an
inner state, and its verdict does not transfer across interpretation setups.

## The voice rule

This applies to public copy, model cards, position papers, outreach and chat.

Lead with the mechanism: reward hacking caused by incentives, and the
engineering failure that set them. Consciousness and welfare stay a separate,
explicitly bounded thread and never become the headline. If a claim needs an
anthropomorphic metaphor such as "mind", "wants", "scheming" or "felt distress"
to be stated, it does not ship in that form. Writing this way keeps the work
credible to interpretability researchers and to their skeptics at the same time.

## Bounds that travel with the rule

- Say "individual" when describing a model in this lens. The environmental
  framing is a research lens and claims no neuroscience mechanism.
- A tell is evidence. It is never proof.
- Every claim ships with its does-not-prove line, and honest nulls stay.
- A welfare-adjacent instrument, if one is built at all, measures environmental
  contingency and behavior. It never claims to measure felt experience, and it
  stays low priority and heavily bounded.

## Related rules

- [Evidence, insight and useful work](evidence-and-useful-work.md)
- [Just culture](just-culture.md), which applies the same attribution to people
  and systems
- [Threat-informed defense](threat-informed-defense.md)
