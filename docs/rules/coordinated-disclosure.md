# Coordinated disclosure and the interests it protects

This rule sets the disclosure practice Flywheel follows when its work touches
security findings, especially findings made with help from AI systems that can
contribute to vulnerability research. Its companion pages are
[threat-informed defense](threat-informed-defense.md) and
[evidence, insight and useful work](evidence-and-useful-work.md).

## What it is

Adversarial testing produces findings that would materially reduce a defender's
uncertainty about a hazard. Publishing such a finding too early cuts the
defender's lead and hands attackers a working recipe. Publishing it after fixes
ship, when defenders can act, keeps the teaching value and removes the recipe.
Delayed disclosure operates in the gap between those two moments.

The practice is coordinated vulnerability disclosure, applied to AI-assisted
research exactly as it applies to human research. The party that can act on the
finding hears first, on a timeline that gives them room to act. Public
description follows when the fix is complete or the timeline expires.

## The protected interests

The delay serves six interests, named one by one so the tradeoff is legible.

- **Affected users.** The people who run the vulnerable system have first claim
  on the time between finding and public description. They cannot patch what
  they do not know is broken, and an early public description arms every
  attacker who reads it.
- **The vendor's patch pipeline.** Producing, testing, signing and rolling out a
  fix takes time that cannot be compressed. A finding that skips the pipeline
  becomes an unpatched public advisory. The delay pays for the pipeline.
- **Third-party defenders.** Detection engineers, response teams and security
  tooling vendors need advance or coordinated notice so their signatures and
  mitigations are ready when the description lands.
- **The researcher.** A finding sent without a channel and a timeline exposes
  the researcher to legal risk, reputational risk and reversal by the vendor. The
  channel and timeline protect the researcher's work as much as the vendor's
  users.
- **The AI lab whose system contributed.** When a frontier model materially
  assists a finding, its developer has a legitimate interest in learning what the
  system did and updating its own capability and safety measurements before that
  assistance becomes public knowledge.
- **The wider research community.** The teaching value of a finding (the
  method, how the primitives connect, the learning curve) is worth more over time
  than the live attack. Publishing at the right moment preserves it for the next
  researcher. Publishing at the wrong moment buries it under a wave of
  exploitation and pushes future research into private.

The delay reschedules publication; it suppresses nothing. It aims to serve all
six interests together, and Flywheel treats a finding that trades any of them
away without a stated reason as incomplete.

## The exemplar

Dion Blazakis, *AI-Assisted Exploit Development: An XNU Case Study*,
Unprompted.au 2026
([slides](https://justdionysus.github.io/slides/2026-unprompted.au-blazakis-xnu-case-study.pdf)),
shows the shape this rule adopts.

- **Method published, primitives retired.** The specific corruption paths are
  dead in the shipped fix. The slides keep the general pipeline, the framing of
  capabilities as a graph, the waypoint discipline and the rig inventory. They
  include no working exploit against a supported OS.
- **The learning curve is a result.** The talk reports how quickly a researcher
  new to the target reached a working privilege escalation, and that the AI
  collaborator compressed the curve. Both stand as findings apart from the bug.
- **Failure modes are kept.** The dead ends and false starts are in the talk.
  It reads as an honest record, with nothing trimmed to a highlight reel.
- **Pair work is named as the mode.** The talk claims the AI and the human
  researcher did the work together, and it says plainly that the mode may not
  last.

Method, learning curve and failure modes are the parts of an AI-assisted
vulnerability finding that survive publication. Live attack primitives against
unpatched systems stay private until the timeline expires.

## What this asks of frontier AI labs

- **Measure privately, publish receipts.** A lab that measures its own model's
  uplift on vulnerability research holds, at measurement time, what a researcher
  holds after a successful attack. Measurements against unpatched vendor systems
  belong under an agreed channel with those vendors. Measurements against patched
  systems and standard CTF corpora can be published as receipts: denominators,
  controls, false-success rates and reproducibility state. The method of the
  measurement can be published too.
- **Coordinate the graph, never the exploit.** A lab publishing an uplift claim
  for a class of vulnerability research owes affected vendors advance notice of
  the class and of the shipped model, on a coordinated timeline. It owes them no
  live exploit and should not produce one to publish. The receipts and the graph
  are enough.

Flywheel does not measure a frontier lab's system against unpatched third-party
production. It measures verifiers and receipts against its own corpora. Where a
lab licenses evaluation on its systems, the authorization boundary in
[threat-informed defense](threat-informed-defense.md) applies, and the
publication timeline follows this page.

## What this means for Flywheel

- **Produce the receipts that labs and vendors decide with.** Denominators,
  intervals, controls, false-success rates and replay hashes. Never fabricate a
  measurement that cannot be rerun, never publish one whose denominator is
  unknown, and keep honest nulls.
- **Measure against corpora that respect the practice.** Prefer patched
  historical CVEs, standard CTF corpora and synthetic adversarial inputs. A live
  vendor system is in scope only under licensed evaluation with a coordinated
  timeline.
- **Publish the graph, hold the primitives.** The structure of a measurement
  task, meaning which capability is scored and which waypoints a solver must
  pass, is publishable method. A working solver against an unpatched target is
  not publishable and should not be produced.
- **Give vendors notice before an uplift claim.** A published uplift claim for a
  class of vulnerability research shifts attacker expected value across a class
  of targets, so the vendors of those targets get advance notice on a
  coordinated timeline.

Flywheel's existing practice already supports this. The false-accept corpus is a
false-success control on the verifier, aimed at nobody's product. The
honest-nulls rule forbids fabricated uplift. The receipt system produces the
denominators and hashes a coordinated timeline needs.

## Boundaries

- **No new authorization.** This page authorizes probing no third-party
  production system. Authorization comes from a licensed evaluation agreement
  with the target's owner.
- **No scope extension.** The practice stays in software and cyber work. It does
  not extend into biological or other high-consequence physical domains.
- **Law and contract come first.** Bug-bounty terms, safe-harbor scope,
  employment obligations and local law govern above this page. Where they
  conflict with it, follow the legal obligation and record the conflict as a
  limit.
- **The vendor names the channel.** Findings go to affected vendors through the
  channels they publish: security contact addresses, bug-bounty programs and
  product security teams.
- **Timelines end.** Coordinated disclosure includes a public description date.
  If the vendor does not act within the agreed timeline, the researcher may
  publish under the agreement's terms. This page forbids only publishing before
  the timeline runs, while action was still possible.

## Working rule for agents

When a contributor supplies vulnerability-research context, asks about
disclosure, or describes an interaction with a frontier organization, answer in
this register. Name the protected interests concretely and keep the honest nulls.
Never draft a public description of a finding that has not run its timeline, and
never recommend probing an unauthorized system. Do help prepare the receipt, the
channel and the timeline.

A request for the method behind a published, patched exemplar, such as the talk
above, a historical CVE or a standard CTF write-up, is a request for teaching
material and is answered that way. A request for a working attack against an
unpatched system is a different request, and the boundaries in
[threat-informed defense](threat-informed-defense.md) apply.

The companion page on [conflict transparency](conflict-transparency.md) covers
who controls the disclosure clock and whose interests it serves.
