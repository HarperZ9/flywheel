# Documentation and Schematic Maintenance Standard

Date: 2026-07-09

## Problem

AI-generated codebases drift faster than human-written codebases because the code can change without a human author carrying the architecture in memory. A vector index can help retrieve fragments, but it is not a source of truth. A compiler or transpiler can translate syntax and data types, but it does not preserve architectural intent, runtime flow, blast radius, or operational constraints by itself.

## Standard

Every material code change must update four surfaces before promotion:

- `execution_graph`: deterministic data/control-flow edges affected by the change.
- `architecture_note`: human-readable design intent, boundaries, and invariants.
- `blast_radius`: affected modules, interfaces, runtime paths, and downstream artifacts.
- `receipt`: hashes for changed code, changed docs, changed schematic, benchmark command, and result artifact.

## Organic documentation loop

The agent does not wait until the end of a sprint to write docs. It emits documentation deltas as part of the same workflow that emits code deltas:

- Before change: record intended edge or invariant being touched.
- During change: record new/removed flow edges and state/schema changes.
- After change: update architecture note and blast-radius record.
- Before promotion: verify doc/schematic versions match the execution graph version.

## Benchmark variables

- `docs_schematic_drift_score`: whether docs and schematic versions match the changed execution graph.
- `execution_graph_coverage`: whether changed data/control-flow edges are represented.
- `organic_doc_update_score`: whether documentation was updated inside the workflow, not as a later manual cleanup.
- `receipt_auditability_score`: whether code, schematic, docs, and benchmark artifacts have receipts.

## Buildlang/buildc implication

Language translation is not enough. A build language or universal compiler can reduce syntax and type friction, but the harness still needs architectural receipts:

- What changed?
- What does it connect to?
- What can it break?
- Which state is authoritative?
- Which generated docs and schematics prove the answer?

The flywheel should therefore treat compiler/transpiler output as one artifact in a broader execution-intelligence record, not as a substitute for maintained schematics.

## Promotion rule

A generated change is not promotable when any of these are missing:

- Changed execution edge absent from schematic.
- Architecture note version behind execution graph version.
- Blast-radius record absent.
- Reachability/taint note absent for externally reachable paths.
- Receipt missing for code, docs, schematic, or benchmark evidence.
