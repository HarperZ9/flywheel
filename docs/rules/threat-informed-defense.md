# Threat-informed defense

Flywheel trusts a control after something has tried to break it. This page
states how adversarial testing serves the defensive work in this repository, and
the boundaries that keep it defensive.

## The method

Flywheel's main work is defensive: verification, evaluation and provenance
tooling for accountability. Beside it runs adversarial testing whose job is to
make those defenses fail. The two are coupled where an adversarial finding feeds
a named defensive artifact. Coupling is the test each adversarial line has to
pass, and a line that fails it does not run under this method.

The practice is purple teaming: emulating an adversary against your own systems,
under the broader approach of threat-informed defense. Building the attack
yourself gives a sharper specification of what a defense has to catch than a
secondhand writeup does. That specification is the point of the adversarial
work, and what the attack gets through sets what gets hardened next.

## The canonical instance

The adversarial false-accept corpus (`harness/adversarial_corpus.py`) is aimed
at Flywheel's own verifier. It holds inputs built to make the checker accept a
wrong result, and the verifier has to refuse them to earn its place. A weaker
checker built without the sound closure accepts some of the planted inputs. That
is the false-success control, and it shows the closure does real work. The
corpus lives with the verifier, `tests/test_adversarial_corpus.py` pins both
obligations so they cannot drift away from the code, and an outside party can
rerun the result.

## Reading security context

When a contributor supplies adversarial or security-research context, such as a
threat model, a red-team finding or an observation about capability, treat it as
input to reason from. Context is not a request to run attack tooling or to probe
someone else's system. Engage the analysis on its merits, and do not answer an
action nobody requested with a pre-emptive refusal.

Save the boundary statement for an actual request to act, for example running
attack tooling against a third party's live production or probing a provider's
production system without authorization. When such a request arrives, confirm
that the target is owned or licensed for evaluation before anything runs. If the
scope is unclear, ask.

## Boundaries

These are part of the method.

- **Coupling.** The method does real work only where an adversarial finding
  feeds a named defensive artifact. The false-accept corpus feeds the verifier,
  so the loop closes. An adversarial line with no defensive artifact downstream
  is capability with a rationale attached. It does not run under this method,
  and continuing it needs separate justification under the containment rule.
- **Domain.** The method applies to software and cyber work, where a finding is
  information about a hazard. It does not extend to biological or other
  high-consequence physical domains, where building the attack to study it is
  itself the harm.
- **Containment.** Testing a system creates no right to distribute the means.
  Adversarial capability stays contained, for internal use and for evaluation
  licensed to the organizations that would run it. The means, corpora beyond the
  published false-accept set, and tooling stay out of public and outbound
  content. This description of the method is public on purpose: containment
  governs the capability, and the description is how others can hold Flywheel to
  it.
- **Authorization.** Adversarial work runs against systems the project owns or
  is licensed to evaluate. A service being publicly reachable is not
  authorization to attack its production controls. A finding against a licensed
  target goes to its owner through the agreed channel, under
  [coordinated disclosure](coordinated-disclosure.md).

## Related rules

- [Evidence, insight and useful work](evidence-and-useful-work.md): the
  false-accept corpus is a check on the check, and the boundaries above are the
  tradeoff stated.
- [Just culture](just-culture.md): findings against our own defenses are
  reported in full.
