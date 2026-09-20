# Native decision contract

Status: first experimental slice, authorized routing-first direction. This does not claim a trained model, a mounted native UI, or superiority over any vendor.

## Problem

Provider-call success is not task success. Flywheel's existing adaptive routing records transport health, latency and optional cost. A decision experiment needs bounded candidate choices, explicit abstention and outcome evaluation without giving a learned scorer authority over actions or acceptance.

## Architecture

Add a small stdlib contract in the existing harness. Reuse canonical evidence hashing. A caller supplies a bounded state, choices, deterministic eligibility result and source references. Any existing model may propose a choice. Strict parsing produces a selected or abstained proposal and a replayable validation receipt. This layer does not call providers, execute tools, grant permissions, write a memory store or certify semantic correctness.

The gateway integration follows later through the existing exact-grant path. Audit optional adaptive-chain fields against the actual grant schema before mounting; presence of a low-level helper does not establish public authenticated support. Canon stores linked context/decision evidence, Plexus supplies declared compatibility, and Relay remains the execution boundary.

## Contract

Request schema `flywheel.decision-request/v1`: `decision_ref`, `state`, `choices` (unique id and description), `eligible_choice_ids`, `evidence_refs`. All fields required, exact keys, bounded strings and cardinality. State is plain text in this first slice. Choices are opaque identifiers, never shell commands. Eligibility is a caller-provided decision input, not proof of permission. Empty eligibility is a legitimate abstain case.

Proposal JSON: exact keys `choice_id` (eligible declared id or null) and `evidence_refs` (subset of supplied references). A null choice means abstain. No free-form rationale or generated confidence is necessary for the first contract. Optional probabilistic scorers require a separately versioned calibration/evaluation contract; do not pretend a verbal confidence number is calibrated.

Malformed/extra/duplicate-key JSON, NaN/Infinity, undeclared/ineligible choices, invented evidence references and over-budget responses must produce explicit abstention with fixed non-echoing reason codes. Invalid requests fail before proposal processing. Valid syntax is not evidence of decision quality. Validate a copied snapshot so later caller mutation cannot change receipt meaning.

Result schema `flywheel.decision-result/v1`: selected/abstained disposition, choice id or null, reason code, validated evidence references, request SHA256, response SHA256, scorer reference and clear does-not-prove. It is a proposal for independently authorized execution, never an authorization or acceptance result. Preserve a bounded malformed response hash without echoing arbitrary source text. Oversized or nonstring responses have `response_sha256: null` and an explicit `response_oversize` or `invalid_shape` reason; do not hash unbounded input or fabricate a digest for it. Response type and size preflight precedes every result path, including empty eligibility and invalid scorer reference. Hashing records bytes; it does not establish their truth.

## Evaluation

Create a separate offline evaluator over held-out task labels and candidate outputs. Distinguish eligible-choice adherence, correct selection, incorrect selection and abstention. Report task count, coverage, accuracy among selected tasks, overall successful fraction and unsafe/ineligible selection count; a router that abstains everywhere must not look perfect. Latency/cost fields are optional observed inputs and remain unknown if absent. Never invent estimates as measurements.

Contract fixtures use deterministic stub outputs and prove validation only. Model quality, real provider latency, multimodal perception and competitive comparisons need separate runs with actual model responses and independent outcome checks. The first benchmark must include an always-abstain and a deliberately wrong but schema-valid baseline.

## Boundaries and next stages

No new dependency, database, product name or provider credentials. No model on the verifier accept path. Keep files below the repository300-line limit. Future stages add real provider/local scorers, measured abstention thresholds, live gateway/UI integration and multimodal observation adapters. Perception and routing errors must be measured separately. Paid inference, training and distribution are not implicit in this source-only experiment.
