# Flywheel 0.7.0 candidate

This candidate brings external evaluation records into the native evidence workflow. Packaging and installed acceptance are still pending. A source merge does not establish that an installed copy contains these changes.

## Inspect evidence in the desktop

The existing Receipts surface can import an Inspect JSON export and reopen retained evidence. Import authorization binds the uploaded bytes to a one-use Journey grant. The reviewer can inspect source hashes, JSON pointers and source values alongside producer-reported scores, completion status, coverage and invalidation.

The importer preserves the distinction between a reported score and a verified answer. Structural import and retained-byte integrity do not establish scorer independence or semantic correctness. Stored evidence checks also cannot detect a coherent rewrite of the entire local record and all its local anchors.

## Reproducible external-format checks

Versioned fixtures and producer compatibility checks cover supported Inspect exports. A separate pinned METR task-image workflow exercises a real task image through the bridge with correct, wrong and completion-fallback controls, retaining logs and import results. The fallback control is not an empty-output test. No model provider participates in that deterministic compatibility check.

These controls test interoperability and failure handling. They do not measure model capability, certify compliance with METR standards, or establish an independent ground truth.

## Process review

The incident-simulation workflow separates submitted actions, claimed scores, observed fixture effects and checker results. Its process-audit packet retains evidence locations and reconstructed receipts. Reconstructed action receipts do not prove that the actions ran on a workstation. The independence documentation records shared dependencies and the limits of the local checker.

An optional declared-access component records requested, granted, denied, unavailable, unknown and withdrawn evidence access within a caller-defined scope. Checked source pointers and redaction impacts make coverage limits inspectable. The packet verifier recomputes local section and packet digests and checks the action, work and audit receipts. Absent access assessment remains `NOT_ASSESSED`. These checks do not establish that disclosures are complete, that a stated access event happened, or that a conclusion is correct.

`flywheel incident-sim` accepts paired access-record and scope files. Its `--verify-packet` mode rechecks a saved process-audit packet offline. The command and Python verifier agree after order-only JSON reserialization, while changed values still fail verification. Raw source hashes distinguish differently serialized input files. This packet command is separate from the native Inspect import workflow.

## Relay checkpoint recovery

The bundled Relay source advances to version 0.2.1 with checkpoint snapshot persistence. The bundle continues to expose the same admitted status tool; this update does not silently widen its tool permissions. Installed recovery and physical Android handoff require their own acceptance evidence.

## Release boundary

The candidate has one version across Python packaging and the desktop. Publication requires the complete candidate gates, matching artifact hashes and installed acceptance. Native file-picker behavior, installed engine restart and evidence reopening are separate checks. This document does not claim that those release checks have completed, that external evaluators have adopted the tool, or that the whole platform is feature-complete.
