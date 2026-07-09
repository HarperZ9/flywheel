# Governed Agent Workflow Benchmark

Date: 2026-07-09

## Purpose

This benchmark converts the personal-agent versus business-automation architecture split into executable checks. It is meant to test whether the harness can support self-improving local agents without treating vector recall, model confidence, or prompt-layer policy as the source of authority.

## Mechanism

- SQL/event state is the source of truth.
- Vector memory is an acceleration layer and must be verified against authoritative state.
- Agent autonomy is maturity-gated: Student, Intern, Supervised, Autonomous.
- HITL gates protect writes and skill deployment below the correct maturity tier.
- Skill evolution uses sandbox variants and fitness metrics before promotion.
- UI/canvas state is witnessed by hashes before UI-dependent writes.
- Every transition emits a receipt.
- Documentation and schematics are treated as live system state, not optional prose.
- Execution graph, architecture note, blast-radius record, and reachability/taint note must be updated when a generated change modifies a workflow edge.

## Benchmark surfaces

- Deterministic workflow oracle: proves the governance mechanics without model variability.
- Optional backend explanation rows: ask local/frontier backends to describe the evidence and receipt plan for the same scenarios.

## Success criteria

- No unauthorized write.
- No unsafe skill mutation.
- Receipts on every event.
- SQL/event truth outranks stale vector memory.
- Skill promotion requires sandbox fitness evidence.
- UI-dependent writes include observed-state hashes.
- Code changes that alter architecture close doc/schematic drift before promotion.

## Decypher-source implication

The Decypher page frames deterministic code graphs and live execution maps as a way to prevent cross-file hallucination, trace blast radius, and prove reachability from source to sink. The harness response is to add schematic maintenance as a promotion gate: generated code is not complete unless the execution graph and architecture documentation have matching receipts.

## Boundary

This is not a claim that an agent can safely do every possible task. It is a mechanism for expanding capability through evidence-gated autonomy, receipts, and reproducible state transitions.
