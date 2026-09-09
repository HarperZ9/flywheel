# Writing Workspace

Writing Workspace is a private author workflow in Flywheel. It gives a writer or agent an owned place to record briefs, source packets, sections, revisions, reader cards, scoped candidates, explicit decisions, review artifacts, and exports.

The first release is a backend, CLI, and MCP slice. It does not include desktop UI. It records deterministic custody and scope checks; it does not measure writing quality, factual truth, source support, or publication readiness.

## Workflow

Every mutation follows the same custody path:

1. Prepare a proposal with `flywheel writing ... --prepare --json`.
2. Inspect the exact approval preview with `flywheel writing proposal get <proposal_ref> --json`.
3. Approve it locally with `flywheel writing proposal approve <proposal_ref> --json`.
4. Commit it with `flywheel writing proposal commit <proposal_ref> --grant <grant_ref> --json`.

MCP tools prepare proposals and can commit a caller-supplied grant. MCP approval is unavailable by design, so an MCP server cannot approve its own writing mutation.

## Minimal CLI sequence

```powershell
flywheel writing init --brief brief.json --source-packet sources.json --client-request-id init-1 --prepare --json
flywheel writing proposal get <proposal_ref> --json
flywheel writing proposal approve <proposal_ref> --json
flywheel writing proposal commit <proposal_ref> --grant <grant_ref> --json

flywheel writing section add --journey-ref <journey_ref> --expected-event-head <head> --section-json section.json --client-request-id section-1 --prepare --json
flywheel writing revision record --journey-ref <journey_ref> --expected-event-head <head> --project <project_ref> --section <section_ref> --body draft.txt --client-request-id draft-1 --prepare --json
flywheel writing diagnose --journey-ref <journey_ref> --expected-event-head <head> --project <project_ref> --revision <revision_ref> --client-request-id diagnose-1 --prepare --json
flywheel writing card record --journey-ref <journey_ref> --expected-event-head <head> --card-json card.json --client-request-id card-1 --prepare --json
flywheel writing candidate record --journey-ref <journey_ref> --expected-event-head <head> --project <project_ref> --card <card_ref> --body candidate.txt --client-request-id candidate-1 --prepare --json
flywheel writing decision record --journey-ref <journey_ref> --expected-event-head <head> --project <project_ref> --decision accept --candidate <candidate_ref> --client-request-id accept-1 --prepare --json
flywheel writing review --journey-ref <journey_ref> --expected-event-head <head> --project <project_ref> --client-request-id review-1 --prepare --json
flywheel writing export --journey-ref <journey_ref> --expected-event-head <head> --project <project_ref> --out-ref article-final --client-request-id export-1 --prepare --json
```

Use the returned `event_head_sha256` from each committed step as the next `--expected-event-head`.

The card JSON must use a `card_[32 lowercase hex]` ID and reference a committed diagnostic for the same base revision. The generated diagnostic keeps semantic reader-state, span units, and revision cards empty/unmeasured unless a supported author/model annotation source is attached.

Local recovery drafts, immutable saved revisions, proposed candidates, and the accepted manuscript are distinct states. A manual `revision record` commit becomes the accepted section head. A candidate becomes the accepted section head only after an explicit `decision accept`. Export reads the accepted section heads only.

## Scope and safety controls

- Artifacts are stored under the local owner’s `state/artifacts` root and are referenced by opaque relative refs.
- Candidate scope is checked against the stored base revision body and an exact `unicode_codepoint` target using zero-based half-open offsets in the admitted LF text.
- Revision and candidate artifacts include a `text_admission` receipt that reports CRLF/CR conversion and binds the admitted UTF-8 LF body hash used for coordinates.
- Accepting a candidate fails if the current section head no longer matches the candidate’s base revision.
- Rejecting or superseding an out-of-scope candidate records author disposition without changing the manuscript.
- Rolling back is limited to revisions previously accepted for the same section.
- Commit revalidates artifact bytes against the proposal digest, so changing a candidate or decision artifact after approval fails.
- Review and export manifests bind the accepted revision refs, decision refs, source packet ref, Journey ref, review ref, and event head used to prepare the artifact.
- Diagnostic artifacts carry deterministic source-marker span and packet-membership checks, plus explicit unmeasured or reported semantic fields. They do not claim source truth, reader reception, or writing quality.
- Export refuses to overwrite an existing private export target.
- Review artifacts mark semantic quality as `unmeasured` unless an independent review is attached.

## Current backend limits

- `proposal get` reports the exact command, artifact ref, artifact digest, kind, artifact identity, revision body, candidate body, decision scope verdict, and review/export bindings where applicable. It is a JSON approval preview, not a desktop side-by-side editor.
- Diagnostic, review, and export artifacts use the V2 schemas. Deterministic reader-flow/source-marker checks are included, while semantic quality and factual truth remain explicitly unmeasured.
- Export writes accepted section heads into a private manuscript and manifest. It is local artifact creation, not publication.
- Filesystem root/object authority beyond the current Writing-local checks is waiting on the shared workspace storage primitive.

## MCP tools

Run the MCP server with:

```powershell
python -m harness.writing_mcp
```

The server exposes `writing.status`, `writing.doctor`, `writing.diagnose`, prepare tools for project, section, revision, card, candidate, decision, review, and export, plus `writing.proposal_get` and `writing.proposal_commit`. `writing.proposal_approve` returns `APPROVAL_UNAVAILABLE`; approve with the local CLI. If a tool call omits `home`, the server uses `FLYWHEEL_HOME` and then falls back to the normal `~/.flywheel` state root.
