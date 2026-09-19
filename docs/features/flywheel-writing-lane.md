# Writing (Flywheel native lane)

> Scope note. The writing lane is integrated. It has a lane registry entry
> (`harness/lanes_registry.py` `LANES["writing"]`), a private HTTP adapter
> (`harness/writing_route.py`, mounted at `/api/writing/` in `harness/gateway.py`),
> a packaged CLI (`harness/writing_cli.py`), an MCP server
> (`harness/writing_mcp.py`), a desktop destination
> (`DestinationId.writing` in `desktop/lib/navigation/`), and an expected-set
> test (`tests/test_lanes.py`). Claims under "What it is", "Feature reference",
> and "Stepwise usage" are observed from that source. The cross-lane wiring in
> "How it composes" separates what runs today from what is proposed, and labels
> each.

## One sentence

The writing lane is a private, owner-local author workspace inside Flywheel that
records briefs, sources, sections, revisions, scoped edit candidates, explicit
accept and rollback decisions, and manuscript exports as hash-bound artifacts,
where every state change is a prepared proposal an operator approves once before
it commits.

## One paragraph

The writing lane gives a writer or an agent a place to build a manuscript under
recorded custody. Each project starts from a brief and a source packet, grows a
small set of sections, and accumulates saved revisions. An edit is scoped: a
card names an exact span of a base revision, a candidate proposes replacement
text for that span, and a deterministic scope check reports whether the
candidate touched only the named span or reached outside it. Nothing mutates
the manuscript on its own. Every operation first prepares a proposal, the
operator inspects the exact preview, approves it once, and then commits it
against a Journey v2 event log with an expected head. A commit against a stale
head is rejected, so a concurrent change stays visible to the writer. The MCP
server can prepare a proposal and commit an already-approved grant, and it
cannot approve, by design, so a model driving the tools cannot approve its own
mutation. The lane records deterministic custody and scope. It does not measure
prose quality, factual truth, source completeness, or publication readiness, and
every artifact carries a `does_not_prove` line that says so.

---

## Feature reference (observed, code-bound)

Each item names a capability and the source that implements it.

### Custody and approval

- **Prepare, approve, commit for every mutation.** No writing operation changes
  state directly. A prepare call writes the artifact bytes and returns a
  proposal; approval is a separate step; commit takes the approved grant.
  `WritingService._prepare_artifact` and `commit_proposal` in
  `harness/writing_service.py` implement the path over `harness/grant_route.py`
  and `harness/journey_service.py`.
- **MCP cannot approve.** The `writing.proposal_approve` operation is marked
  `mcp_available=False` with reason `APPROVAL_UNAVAILABLE`
  (`harness/writing_operations.py`). Over MCP it returns that code and the
  message to approve with the local CLI (`harness/writing_mcp.py`). Approval
  stays on the CLI or the private HTTP surface, so an MCP client cannot approve
  the mutation it just prepared.
- **Optimistic concurrency on the event log.** Each mutating call carries an
  `expected_event_head` sha256. The Journey service rejects a commit whose head
  no longer matches (`harness/journey_service.py`), so a stale writer does not
  clobber a newer commit. The returned `event_head_sha256` is the next call's
  expected head.
- **Commit revalidates the approved bytes.** `commit_proposal` re-reads the
  proposal record and runs `validate_writing_append` again before it commits
  (`WritingService._revalidate_record`), so editing a candidate or decision
  artifact after approval fails the commit.
- **Owner-bound state home.** State lives under an owner-local root
  (`state/artifacts`), keyed by an `owner_[32 hex]` owner ref
  (`harness/writing_service.py`, `harness/writing_types.py`). The installed
  launcher `flywheel-writing-workspace-mcp` refuses to start without
  `FLYWHEEL_HOME` and binds that home for the server lifetime; a tool call that
  names a different home is rejected with `HOME_MISMATCH`
  (`harness/writing_workspace_mcp.py`, `harness/writing_mcp.py`).

### Project intake

- **Brief plus source packet at init.** `writing.project_init` reads a brief
  JSON and a source-packet JSON from caller-supplied local paths, checks that
  both name the same `project_ref`, stores each as an artifact, and writes an
  intake manifest (`WritingService.prepare_init`). The two files stay
  caller-supplied local reads; the lane binds their custody once they are
  stored, and broader filesystem authority is left to the shared storage work.
- **Bounded, typed brief.** A brief is validated exactly: `mode` must be
  `nonfiction`, `form` must be one of `editorial`, `blog`, or `essay`, and the
  title, audience, reader job, author intent, voice contract, and writing
  profile fields are required (`_validate_brief` in `harness/writing_types.py`).
  Unknown or missing fields fail.
- **Bounded source packet.** A source packet holds between 1 and 32 sources,
  each with an id, title, origin, and allowed-use field, and an optional body
  ref plus body hash (`_validate_source_packet`). The packet is size-capped at
  1,048,576 bytes (`MAX_SOURCE_PACKET_BYTES`).

### Structure and revisions

- **Up to eight sections.** A section carries a heading, purpose, reader entry
  state, and promises. Adding a ninth distinct section raises `SECTION_LIMIT`
  (`WritingService.prepare_section`, `_validate_section`).
- **Saved revisions with a text-admission receipt.** A revision stores the body
  text, its sha256, a word count, and a `text_admission` receipt that reports
  CRLF or CR conversion and binds the admitted UTF-8 LF body hash used for all
  span coordinates (`WritingService.prepare_revision`, `admit_text` in
  `harness/writing_types.py`). Author-supplied text is capped at 262,144 bytes
  (`MAX_AUTHOR_TEXT_BYTES`).
- **Distinct manuscript states.** A manual revision commit becomes the accepted
  section head. A proposed candidate is not a head until an explicit accept
  decision. Export reads accepted section heads only. This separation is
  described in `docs/writing-workspace.md` and enforced by the state
  projection.

### Scoped edits

- **Exact span target.** A card names a target with `coordinate_type`
  `unicode_codepoint`, zero-based half-open `start` and `end` offsets, the base
  revision ref, the base body sha256, and the sha256 of the selected span.
  `validate_target` in `harness/writing_types.py` rejects a target whose range
  is empty, runs past the body, or whose selected span hash does not match the
  stored body, with `TARGET_SPAN_DRIFT` for the last case.
- **Deterministic scope verdict.** `scope_replacement_plan` in
  `harness/writing_reader_flow.py` compares a candidate against the stored base
  body and the target. It returns `PASS` when the candidate keeps the prefix and
  suffix around the span byte for byte and changes only the span, and `HOLD`
  otherwise, with reasons drawn from a fixed set: `target_type`,
  `candidate_length`, `prefix`, `suffix`, `base_body_sha256`,
  `selected_span_sha256`. The verdict rides on the candidate artifact as a scope
  receipt (`WritingService.prepare_candidate`).
- **Author disposition without silent change.** A `decision` record accepts,
  rejects, supersedes, or rolls back. Accept, reject, and supersede act on a
  candidate; rollback returns a section to a previously accepted revision. An
  accept fails if the current section head no longer matches the candidate's
  base revision, and a rollback target must be one of the section's previously
  accepted revisions or it raises `ROLLBACK_TARGET_INVALID`
  (`WritingService.prepare_decision`).

### Reader-flow diagnostic

- **Deterministic source-marker check.** `build_diagnostic` in
  `harness/writing_reader_flow.py` scans the revision body for bracketed source
  markers of the form `[source_id]`, checks each against the source-packet ids,
  and marks it `known_source` or `unknown_source`. An unknown marker becomes a
  `citation_gap` problem. The check pins the marker span and its hash.
- **Semantic fields stay unmeasured by default.** The diagnostic's reader-state
  summary, span units, and revision cards are empty and marked unmeasured unless
  a supported author or model annotation source is attached
  (`build_diagnostic`, `docs/writing-workspace.md`). The diagnostic does not
  claim reader reception, source truth, or writing quality.

### Review and export

- **Review binds the current state.** `writing.review_prepare` records the
  current revision refs, the latest matching reader-flow diagnostic, the source
  packet ref, and the decision refs. Source coverage and scope preservation read
  `checked` only when a matching diagnostic exists, and `unmeasured` otherwise
  (`WritingService.prepare_review`). Style lint and quality measurement are
  always `unmeasured`, and `_validate_review` in `harness/writing_types.py`
  rejects a review that claims a measured quality status. These two slots are
  the named place a prose-quality measurement would attach.
- **Export writes a private manuscript and a manifest.** `writing.export_prepare`
  concatenates the accepted section heads in section order into a manuscript
  file and writes a manifest that binds the manuscript ref and hash, the
  included sections, the decision refs, the review ref, the source packet ref,
  the journey ref, and the event head (`WritingService.prepare_export`). It
  refuses to overwrite an existing export target with `EXPORT_TARGET_EXISTS`.
  Export is local artifact creation, and the manifest itself states it is not
  publication.
- **Every artifact carries a does-not-prove line.** `WRITING_DOES_NOT_PROVE` in
  `harness/writing_types.py` reads: this writing artifact does not prove prose
  quality, factual truth, source completeness, or publication readiness. It is
  attached to revisions, candidates, decisions, diagnostics, reviews, and
  exports.

### Transports and health

- **Three transports, one contract.** The operation set in
  `harness/writing_operations.py` drives all three surfaces: a private
  bearer-auth HTTP API, a local-process CLI, and a local-stdio MCP server. The
  descriptor records each operation's availability per transport, so approval
  reads available on HTTP and CLI and unavailable on MCP from one source of
  truth.
- **MCP server facts.** `harness/writing_mcp.py` speaks JSON-RPC 2.0 over stdio,
  protocol `2025-06-18`, server name `writing-workspace`, version `0.1.0`, and
  imports the standard library only. Its portable launch argv is
  `python -m harness.writing_mcp` (`resolve_mcp_command("writing")`).
- **Doctor and status.** `writing.doctor` reports journey store and artifact
  store presence and marks semantic quality `unmeasured`
  (`WritingService.doctor`). `writing.status` lists owner-local writing projects
  in a public-safe shape.
- **Bundled lane, no install.** The registry marks `writing` as kind `bundled`,
  version `0.1.0`, organ `authoring`. It ships with the engine, so
  `install_lane` reports no install is needed (`harness/lanes.py`).

---

## Stepwise usage

The CLI sequence below is the local path. It comes from `harness/writing_cli.py`
and `docs/writing-workspace.md`. Each mutating step is prepare, then get, then
approve, then commit; the middle steps are omitted after the first for brevity.

1. **Init a project.** Prepare from a brief and a source packet:

   ```
   flywheel writing init --brief brief.json --source-packet sources.json \
     --client-request-id init-1 --prepare --json
   ```

2. **Inspect the proposal.** `flywheel writing proposal get <proposal_ref> --json`
   prints the exact command, artifact ref, artifact digest, kind, and the bound
   bodies where applicable.

3. **Approve locally.** `flywheel writing proposal approve <proposal_ref> --json`.
   This step is not available over MCP.

4. **Commit with the grant.**
   `flywheel writing proposal commit <proposal_ref> --grant <grant_ref> --json`.
   Carry the returned `event_head_sha256` into the next step's
   `--expected-event-head`.

5. **Add a section.**
   `flywheel writing section add --journey-ref <journey_ref>
   --expected-event-head <head> --section-json section.json
   --client-request-id section-1 --prepare --json`.

6. **Record a revision.**
   `flywheel writing revision record --journey-ref <journey_ref>
   --expected-event-head <head> --project <project_ref> --section <section_ref>
   --body draft.txt --client-request-id draft-1 --prepare --json`.

7. **Diagnose reader flow.**
   `flywheel writing diagnose --journey-ref <journey_ref>
   --expected-event-head <head> --project <project_ref> --revision <revision_ref>
   --client-request-id diagnose-1 --prepare --json`.

8. **Record a card, then a candidate, then a decision.** A card names the exact
   span; a candidate proposes the replacement text; a decision accepts or
   rejects it.

9. **Prepare a review.**
   `flywheel writing review --journey-ref <journey_ref>
   --expected-event-head <head> --project <project_ref>
   --client-request-id review-1 --prepare --json`.

10. **Export.**
    `flywheel writing export --journey-ref <journey_ref>
    --expected-event-head <head> --project <project_ref> --out-ref article-final
    --client-request-id export-1 --prepare --json`.

For an installed MCP client, set an operator-owned state home and start the
portable launcher:

```
FLYWHEEL_HOME=<operator-owned Flywheel state directory>
flywheel-writing-workspace-mcp
```

The launcher binds that home and does not grant approval authority;
`writing.proposal_approve` still returns `APPROVAL_UNAVAILABLE` over MCP.

---

## Piecewise reference (each capability)

Operations are grouped by transport availability. Names are the MCP tool names,
which match the CLI verbs and the HTTP routes under `/api/writing/`.

### Read

- `writing.status`: list owner-local writing projects in a public-safe shape.
  Available on HTTP, CLI, and MCP.
- `writing.doctor`: report journey store and artifact store presence, and
  semantic quality as unmeasured. Available on HTTP, CLI, and MCP.
- `writing.project_get` and `writing.project_get_post`: read a public project
  view. Available on HTTP only; both are CLI- and MCP-absent by declaration.

### Prepare a mutation proposal

Each returns a proposal ref, an artifact ref, and an artifact sha256. All are
available on HTTP, CLI, and MCP.

- `writing.project_init`: brief and source packet to an intake manifest. Over
  MCP it takes local file paths; over HTTP it takes embedded JSON objects.
- `writing.section_record`: add or update a section, up to eight.
- `writing.revision_record`: save a full-body revision for a section, with a
  text-admission receipt.
- `writing.diagnose`: run the deterministic reader-flow and source-marker check
  over a revision.
- `writing.card_record`: record a scoped edit card against a committed
  diagnostic for the same base revision.
- `writing.candidate_record`: propose replacement text for a card's span; the
  returned scope verdict is `PASS` or `HOLD`.
- `writing.decision_record`: accept, reject, supersede, or rollback.
- `writing.review_prepare`: bind the current revisions, diagnostic, sources, and
  decisions into a review, with style lint and quality measurement unmeasured.
- `writing.export_prepare`: write the accepted section heads into a private
  manuscript and a binding manifest.

### Approve and commit

- `writing.proposal_get`: inspect the exact approval preview. Available on HTTP,
  CLI, and MCP.
- `writing.proposal_approve`: approve a prepared proposal. Available on HTTP and
  CLI. Over MCP it returns `APPROVAL_UNAVAILABLE`.
- `writing.proposal_commit`: commit a proposal with an externally approved
  grant. Available on HTTP, CLI, and MCP.

### Limits and identifiers

- Sizes: author text 262,144 bytes; brief JSON 65,536 bytes; artifact JSON
  262,144 bytes; source packet and manuscript 1,048,576 bytes each
  (`harness/writing_types.py`).
- Counts: sections at most 8; sources between 1 and 32.
- Reference shapes: owner `owner_[32 hex]`, project `wpr_[32 hex]`, and opaque
  refs per kind, for example `rev_`, `card_`, `cand_`, `dec_`, `wrev_`, `wexp_`,
  each followed by 32 hex characters, and sections as `sec_` slugs
  (`OPAQUE_PATTERNS` in `harness/writing_types.py`).
- Schemas: `flywheel.writing-*/v1` for brief, source packet, section, revision,
  reader-flow diagnostic, scoped revision card, revision candidate, decision,
  review, and export (`SCHEMAS`).

---

## How it composes inside Flywheel

### Which seam it is

The writing lane is a custody lane. It is declared in
`harness/lanes_registry.py` as a bundled lane with organ `authoring`, and unlike
the pip lanes reached through the generic `POST /api/lane/<name>/<tool>` route,
it carries its own private adapter at `/api/writing/` in `harness/gateway.py`,
plus the stdio MCP server and the `flywheel writing` CLI. Its seam is the same
grant-over-journey path other Flywheel state changes use: a prepared proposal, a
single operator approval, and a commit against an expected event head. What
distinguishes it from a verification lane like crucible is the output. Crucible
emits a verdict; the writing lane emits hash-bound artifacts and, at the end, an
export manifest that binds the manuscript to the decisions and sources that
produced it.

### What it consumes from peers

- A brief JSON and a source-packet JSON at init. Today these are caller-supplied
  local file reads (observed). A source packet could be produced by the `gather`
  lane, which writes research intake with provenance receipts (proposed: no
  gather-to-writing wiring exists today).
- Author or model text bodies for revisions and candidates. A `relay` run or a
  local model could supply a candidate body before the operator decides on it
  (proposed).
- An approved grant ref from the operator grant surface
  (`harness/operation_grants.py`), which the commit step consumes.

### What it emits for peers

- Per-artifact JSON, each with a sha256 and a `does_not_prove` line, over the
  three transports.
- An export manifest that binds the manuscript hash, the included section heads,
  the decision refs, the review ref, the source packet ref, the journey ref, and
  the event head. These refs are the re-derivable surface a witnessed ledger such
  as `forum` could record, and a reader could later re-check each binding against
  the stored bytes.
- A review artifact whose `style_lint` and `quality_measurement` slots are
  explicitly unmeasured. Those two slots are the named attachment point for a
  prose-quality measurement produced elsewhere.

### Short worked example: writing to articulate (proposed)

The operator standard for this project routes all outbound publication and
product text through the prose-quality check and measures it against the writing
standard. Inside Flywheel that check is the `articulate` lane, the writing-tell
detector and editor. Articulate is a separate lane and is not wired to the
writing lane today (`docs/features/articulate.md` records it as not_integrated),
so the flow below is proposed and labeled as such. The seam it fills already
exists.

1. Draft a section body in the writing workspace and commit it through prepare,
   approve, and commit. The revision carries its text-admission receipt and body
   hash (observed).
2. Before export, run the manuscript, or each accepted section body, through
   `articulate check` under a register profile, and issue an `articulate receipt`
   that pins the text hash and the ruleset fingerprint (observed on the
   standalone articulate package; proposed as a call from the writing lane).
3. Record the articulate receipt ref in the writing review's `style_lint` slot,
   which today reads unmeasured. The slot and its validation already exist in
   `harness/writing_types.py`; filling it needs the proposed articulate bridge
   described in `docs/features/articulate.md` (proposed).
4. Export. The manifest binds the review ref, so the exported manuscript now
   carries a re-derivable prose-standard screening receipt alongside its custody
   record. A reader replays the articulate receipt against the manuscript text
   and confirms the screening without trusting the issuer (proposed).

The boundary holds either way. A clean articulate result means the prose was
screened under a named ruleset. It does not assert the manuscript is true,
complete, or ready to publish, and the writing lane's `does_not_prove` line says
the same.

### Honest nulls

- The writing lane measures deterministic custody and scope. It does not measure
  prose quality, factual truth, source completeness, or publication readiness.
  `writing.doctor` reports semantic quality as unmeasured, and the review's
  quality slots stay unmeasured.
- No wired call from the writing lane to `articulate`, `gather`, `relay`, or
  `forum` exists today. The seam slots exist; the bridges that fill them are
  proposed.
- Export writes a private local artifact. It is not publication, and the lane
  does not push text to any external surface.
- Filesystem authority beyond the current Writing-local checks waits on the
  shared workspace storage primitive (`docs/writing-workspace.md`).
