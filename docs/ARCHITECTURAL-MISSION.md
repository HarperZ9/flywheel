# Flywheel's architectural mission

Flywheel aims to make consequential AI claims independently checkable, and to
make the tools for doing that usable by evaluators and the general public.
An outside reviewer should be able to rerun a named check from its evidence,
without depending on the original evaluator's reputation.

This is the platform's architectural direction, not a claim of universal
verification or completed frontier-scale deployment. Reproducibility does not
establish that a criterion is appropriate, that evidence is authentic or complete,
or that a model, organization or action is safe.

## The shared contract

A consequential claim needs a named criterion, evidence references, a specified
method, an execution environment and a clear account of what the check cannot
establish. Verification distinguishes Match, Drift and Unverifiable. Permission
to act, execution status, delivery, playback and funding are separate facts.

The same criterion must not change with the provider, model family, organization,
country or funder being evaluated. Evidence access and observation conditions
still matter. A verifier outside the producer's system must be able to challenge
the packet, including missing evidence and a wrong result with consistent hashes.

## A research map across six layers

| Layer | Intended check | Essential limit |
|---|---|---|
| Organizations | Recompute published claims from methods and evidence | A published packet can omit inconvenient evidence. |
| Training environments | Check recorded capabilities, incentives and observed effects | Permitted behavior does not establish learned disposition. |
| Systems and training runs | Bind code, data, procedure and resulting artifacts | A manifest alone does not prove the run occurred as described. |
| Models | Check outcomes against external criteria and establish the tested identity | Proxy scores and declared independence need separate scrutiny. |
| Actions | Compare authorized intent with independently observed effects | An actuator's success message cannot certify its own outcome. |
| Claimed derivations | Check stated steps, sources and conclusions | A valid explanation does not prove it reflects internal computation. |

Coverage varies by instrument. The table names the intended research scope; it
does not describe six completed products. Internal model signals remain untrusted
readouts checked against behavior. Explanations of behavior should name evidence
about training, incentives and runtime conditions rather than inventing motives.

## One platform for work and evaluation

The consumer harness and evaluation tools share this foundation. People should be
able to carry out an ordinary task, recover its sources, understand what happened,
change models and contest an outcome without mastering the entire tool catalog.

- Rowan is the assistant interface. Voice, animation and explanations help people
  navigate; they do not replace evidence or establish task success.
- Chat supports persistent navigation through original messages, sources,
  bookmarks and notes. Summaries must not silently replace the underlying record.
- Studio brings visual and sound instruments into an observation, action and
  feedback loop. Accountable actuation connects permission to observed effects.
- Live screen input records which source and frame were delivered to which
  operation. A current preview is distinct from the input used by an earlier run.
- Models are replaceable. Cross-provider orchestration retains each child route,
  authority, cancellation state and result provenance without silent substitution.

Adapters can supply measurements or perception-model outputs to a text-only
model. That does not confer native vision or hearing, change its training, or
establish an improvement in capability. Those claims require separate evaluation.

MCP and API are first-class interfaces over shared operations, schemas, permission
checks and evidence. The native UI and CLI are clients of those operations.
Protocol compatibility must be tested for the versions and transports actually
implemented. Explicit session, artifact and operation references preserve necessary
application state; a stateless transport does not eliminate that state.

## Evidence of usefulness

The next useful proof is a bounded packet an independent reviewer can replay
outside the producer's database. Pair ordinary-success cases with deliberately
wrong results, altered evidence and missing evidence. Compare reviewer decisions
and effort against an explicit baseline, retaining null and negative outcomes.

External reproduction, useful failures found, repeated use and independently
evidenced commitments are different from test totals, messages sent or page views.
Public artifacts must respect disclosure and privacy scope. Restricted evidence
limits public audit; it must not be silently represented as publicly replayable.

The [1.0 candidate scope](RELEASE-1.0.0.md) retains the concrete product and release
requirements. This mission does not waive an unresolved acceptance gate.
