# Flywheel 1.0.0 candidate

Status: UNRELEASED CANDIDATE. This document is source-aligned for a future 1.0.0 release. It is not a release receipt, an installed-acceptance record, or a claim that the 1.0.0 artifact has been published.

Flywheel 1.0.0 brings the evaluator workflow and the general-user harness into the same native platform. Its [architectural mission](ARCHITECTURAL-MISSION.md) is independently re-derivable evaluation for consequential AI work. The required product outcome includes external evidence review, understandable everyday task execution, interruption handling, persistence, and reviewer handoff. The release is not complete until the same candidate bytes pass source, packaging, installed, and claim-boundary acceptance.

## Candidate scope

The 1.0.0 candidate line keeps the full scope visible:

- Inspect evidence import and review must preserve exact source references, producer counts, score history, invalidation, missingness, and false-success controls.
- Terminal action evidence must show completed, failed, cancelled, legacy, and unavailable-source states without turning retained writes into rollback claims.
- Process-audit and incident-simulation packets must carry source-bound evidence and verifier limits through CLI, API, and Desktop review.
- Trace and Journey persistence must survive restart, changed or missing evidence, authorized source reads, read failures, and recovery checks on installed bytes.
- Provider and auth interop must be checked for every advertised route in its supported configuration.
- Windows packaging must bind source commit, app payload, engine payload, installer hash, and installed bytes before publication.
- Android, Relay, and Plexus handoff remain required parts of the 1.0 scope. Each needs device, network, identity, interruption, and resume evidence for the supported path.
- Rowan's agent, animated interface and recorded voice cues must follow actual operation state, preserve user controls, and keep narration separate from verified outcomes.
- Long chat sessions must support source-linked outline, search, links, bookmarks and notes without losing original messages, drafts or saved navigation targets.
- Model and endpoint selection must distinguish discovered, configured, authenticated and tested routes, including compatible custom/local endpoints and explicit cross-provider child routes.
- Native Studio must connect the visual/sound instruments, accountable actuation and observed feedback. Live screen delivery must bind the selected source and delivered frame to the consuming operation.
- Shared API/MCP operations must retain permission and result semantics across their supported transports. Mediated observations for text-only models must retain their transformation provenance.

## Evidence carried forward

The candidate carries the source work already merged for external evaluation evidence and gateway-effect review, including the Inspect evidence workflow, METR/Inspect task-image controls, process-audit packet verification, Relay checkpoint persistence, and source-bound terminal-effect audit evidence.

Those merged source changes do not prove that a user has installed the 1.0.0 application, that the published package contains them, that provider routes work, or that external evaluators have adopted the workflow.

## Mandatory holds before release

Do not tag or publish 1.0.0 until these holds are cleared and receipts are retained:

1. Full Python gate must cover the final integrated source. The local rerun after gateway-auth and acceptance-recorder repairs passed with unchanged recorded inputs; later relevant source changes require another run.
2. Full Flutter gate on the final 1.0.0 source after any generated-file reconciliation.
3. Local or CI candidate build from the accepted source commit with matching source, app, engine, CRT, installer, and SHA256SUMS manifests.
4. Installed acceptance on the candidate bytes, including preflight, metadata, full engine restart, and Inspect API import/reopen receipts with H20 source binding.
5. Installed reviewer workflow coverage for source review, failure states, restart/recovery, and bounded missingness.
6. Upgrade evidence or an explicit unsupported hold for upgrade behavior.
7. Provider/auth route evidence for every required supported route. Missing evidence keeps the requirement open; editing public copy does not complete it.
8. Android, Relay, and Plexus evidence for the required handoffs. Unsupported or untested paths remain open release requirements until resolved with the operator.
9. Public claim checks after release notes, README, site, package metadata, and Product Hunt copy are aligned to the final accepted coverage.

## Release boundary

A source merge, green hosted CI, a local candidate build, and a sent outreach message are separate states from publication and installed acceptance. The 1.0.0 release can be called ready only when the accepted source commit, artifact hashes, installed receipts, and public claims all point to the same candidate.
