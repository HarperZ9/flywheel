# Flywheel: a product history

Flywheel did not start as a platform. It started as one small program that answered a
narrow question, and it grew, piece by piece, as each answer exposed the next question.
This is the build history, dated from the repositories themselves.

## The origin: EMET, an integrity witness (June 2026)

The first piece was EMET, begun 2026-06-06. EMET answers one question: did these bytes
change. It is a byte-level integrity witness, written four independent times so the four
implementations check each other, so that a claim of "unchanged" does not rest on a single
program anyone has to trust. That is the seed of everything after it: do not ask to be
believed, make the check re-runnable by someone else.

## The pattern: no receipt, no accept (June 2026)

EMET made one habit concrete, and the habit generalized. Within two weeks the same shape
appeared as separate tools, each begun in mid-to-late June:

- index (2026-06-13): map a workspace, its symbols, and a wiki that flags its own drift.
- proof-surface (2026-06-17) and accountable-surface (2026-06-19): a proof packet per
  action, and a live seam where an agent perceives, passes an operator gate, acts through a
  bounded effector, and journals the whole path.
- forum (2026-06-24) and telos (2026-06-24): a witnessed causal ledger for multi-step work,
  and a shared workbench across the family.
- gather (2026-06-25) and crucible (2026-06-25): research intake where every item carries a
  provenance receipt, and falsifiable verification that returns MATCH, DRIFT, or
  UNVERIFIABLE and fails closed.

By the end of June the rule was explicit across the tools: a result counts only when an
outside party can re-derive it, and no learned model sits on the path that accepts an
answer.

## The engine: Flywheel composes the parts (July 2026)

Flywheel began 2026-07-06 as the engine that runs the loop the tools had each been
approaching: take a task, propose an answer with any model, verify it with a real oracle,
write a receipt, and let an independent witness re-run the check. The tools became lanes: a
gather digest feeds a crucible verdict, forum records the run, and the engine binds the
result into a receipt a stranger reproduces. More lanes followed through July: relay
(2026-07-07), a coding agent on any endpoint; mneme (2026-07-07), accountable memory; learn
(2026-06-30), an accountable learning forge; and chorus (2026-07-15), a re-derivable
discourse digest.

The engine also grew a face. A native desktop app renders the lanes, the runs, and the
verdicts, so an operator or an ordinary user can work from an application, with the
terminal as a fallback.

## Continuity and craft (August to September 2026)

Two later pieces closed gaps the earlier work had left open:

- canon (2026-08-28): a provider-neutral memory bank and personality container, so the
  record of what was decided and why survives across tools and model providers.
- articulate (2026-09-18): a writing-quality and AI-tell detector and editor, so the prose
  a system emits is held to a standard and can carry a content-free audit receipt.

## The release: 1.0 and 1.0.1 (September 2026)

The 1.0 line is the native release: the engine and its lanes run without workarounds, the
compiled desktop app passes a clean-runner installed acceptance, and the package publishes
to PyPI. 1.0.1 folds articulate and chorus in as native lanes and adds the compose
pipeline that chains gather, chorus, and crucible into one claim-verification bundle. Every
former standalone flagship is now a documented native feature that stands alone and
composes through published seams.

## What the story shows, and what it does not

The through-line is a single idea held for four months and built out in the open: trust is
a property you can check. It is not a request you grant. Each tool is one honest check. Flywheel
is the engine that runs them together.

The honest limits stay in the story. On the shipped benchmark the verified loop shows no
measured accuracy uplift over single-shot; the demonstrated value today is the re-derivable
receipt and the containment, and capability uplift is the direction the work aims at. The
internal candidate model that would speed routing and ranking is experimental and abstains,
and by design it will only ever propose, never accept. This is an independent project, built
in the open, with the nulls left in.
