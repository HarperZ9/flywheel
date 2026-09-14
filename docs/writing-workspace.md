# Writing Workspace

Writing Workspace is a private author workflow in Flywheel. It gives a writer or agent an owned place to record briefs, source packets, sections, revisions, reader cards, scoped candidates, explicit decisions, review artifacts, and exports.

The first release covers the backend, CLI, MCP, and an initial native desktop surface for recorded Writing state and proposal controls. It records deterministic custody and scope checks; it does not measure writing quality, factual truth, source support, or publication readiness.

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

## Prose linter: report-only structural detectors

The prose linter lives beside the workspace at `harness/writing_lint/` and scores
a draft's FORM against a register profile. Run it with
`python scripts/check_writing.py --profile NAME FILE`, or compare two drafts with
`--delta`. It scores form, never substance, and it does not try to defeat AI
detection.

The phrase-list engine sees vocabulary. Some tells in the writing standard live
in structure, so a draft can score a clean `per100w` and still read as machine
prose. `harness/writing_lint/structural.py` adds report-only detectors for those:

- `rule_of_three`: the reflexive "A, B, and C" tricolon.
- `corrective_negation`: "rather than", "instead of", and the "not X but Y" turn.
- `negative_anaphora`: the "no X, no Y" repetition.
- `landing_sentence`: a short sentence that seals a paragraph after longer ones.

The engine also reports `cadence_cv`, the coefficient of variation of sentence
lengths. A low value near or under 0.45 marks an even, machine-like beat.

These are heuristics, so they inform and never gate. They stay out of the gated
`per100w` headline and appear in `report_per100w` with the other Phase 2 checks,
which keeps a noisy signal from becoming a gate someone switches off.

## Prose linter over MCP (any harness)

The linter also runs as a stateless MCP server, so any harness can score prose
against the standard with no state root and no configuration. It is separate
from the Writing Workspace custody server above: it holds nothing, needs no
`FLYWHEEL_HOME`, and only reads text.

```powershell
python -m harness.writing_lint.mcp
```

Tools: `writing.profiles` lists the register profiles and the default;
`writing.lint` scores a `text` or a `path` against a `profile` (omit the profile
to infer it from a `writing-profile:` tag, the path, or the flavored default) and
returns `per100w`, `report_per100w`, `hard`, `cadence_cv`, and the full violation
counts; `writing.delta` scores two drafts and reports the `per100w` change.

Claude Code, in the project's `.mcp.json`:

```json
{
  "mcpServers": {
    "writing-lint": {
      "command": "python",
      "args": ["-m", "harness.writing_lint.mcp"],
      "cwd": "/path/to/flywheel"
    }
  }
}
```

Codex, in `~/.codex/config.toml`:

```toml
[mcp_servers.writing-lint]
command = "python"
args = ["-m", "harness.writing_lint.mcp"]
cwd = "/path/to/flywheel"
```

The server speaks JSON-RPC 2.0 over stdio (protocol `2025-06-18`) and depends on
the standard library only. It scores FORM, not substance, and never tries to
defeat AI detection.
