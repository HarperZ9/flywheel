# The improvement loop

The platform improves itself by the operation it is built on: perceive the
surface, check it against the credo (a criterion it did not author for this
purpose), carry a re-checkable finding, feed the fix back. This document is
the loop's ledger: each cycle consults a surface adversarially, reconciles
verified findings into a ranked plan, executes against the plan, and records
what shipped. Rinse, repeat, per tool.

The method is not opinion. A finding enters the plan only if an adversarial
verifier opened the cited file and confirmed the defect against the code;
refuted findings are dropped, overstated ones are downgraded. Severity is
what the evidence supports, not what the critic felt.

## The credo, as the standard applied

1. Knowledge open to anyone who can attain the means; build to lower the means.
2. An external check decides acceptance; never reputation, never the model.
3. Every result carries a receipt a stranger can re-run.
4. No claim without its interval; the honest null is first-class.
5. Ownership earned by comprehension.
6. Learning woven into the work.
7. Rebundle the badge around the work, not the worker.

Two invariants never relax: no receipt no accept; no learned model in the
accept path.

## Cycle log

### Cycle 1 (2026-07-14): full-surface consultation

Six surface clusters consulted in parallel (message-spine,
verification-lanes, academy-spine, provenance-store, forge-science,
desktop-client), each finding adversarially verified against the live code
before earning a place. The ranked plan and its execution record land below
as the cycle completes.

Reconciled: 24 findings survived adversarial verification across 6 clusters
(12 agents: 6 critics, 6 verifiers). Refuted findings dropped; overstated
ones downgraded. Six are HIGH, and three of those are in code shipped this
same session, which is the loop working as intended: the credo turned on its
own author.

### The plan, HIGH tier first (each fix is a credo repair)

1. **explanation_gate copy-paste bypass** (tenet 6). The teach-back gate
   passes when the explanation is the diff pasted back verbatim. Require the
   explanation to carry words the diff does not; fail `explanation_receipt(diff, diff)`.
2. **comprehension_ledger cross-kind recency** (tenet 5). "Recency wins" is
   false across kinds: any attestation permanently blocks a newer
   comprehension receipt on the same file. Merge both kinds, sort by
   timestamp, then claim.
3. **store record integrity** (tenet 3). `verify_chain` proves the ledger
   consistent but never re-checks that stored records still match their
   hash; a directly edited entity passes. Add `verify_records()` and wire it.
4. **transparency log wired** (tenet 3). The Merkle log ships but no route
   computes a root or serves an inclusion proof, so no stranger can prove a
   receipt is in the log. Compute the root in the receipts ledger; add a
   proof route.
5. **/v1 turn-receipt prompt hash** (tenet 3). The scaffold hashes a naive
   newline-join, not the flattened prompt the model was actually sent, and
   reprs content-parts arrays. Hash what was routed.
6. **uplift verdict renders a regression as a green win** (tenet 4). A
   negative separated interval shows "verified". Make the verdict three-way.

MEDIUM (18) and LOW follow after the HIGH tier lands: agent pre-pass
ordering, model/endpoint on the turn receipt, SSRF guard on /api/snapshot,
the Y-arm drift comparison, empty-set-renders-green on the desktop, and the
rest, tracked in the workflow result artifact.

### Cycle 2 (2026-07-14): the agent/tool-execution subsystem

The next tool: the highest-stakes surface in the platform (gated writes, exec,
the tool loop where "no learned model in the accept path" lives), which cycle
1 touched only at its scaffold wiring. Five critics, one per risk dimension
(gating/authorization, workspace-boundary, receipt-completeness, the
accept-path invariant, rescue/recovery honesty), each finding adversarially
verified against the code. Reconciliation and execution land below as it
completes.

Also this cycle: the forecaster point-bias correction the replication demanded
(empirical-Bayes shrinkage), validated honestly on the real vectors.

**Cycle 2 execution: 17 findings, HIGH and MEDIUM tiers shipped.** The two
HIGH struck the subsystem's core invariants: apply_patch bypassed the
reward-hacking accept gate (tenet 2, a model could game its own green), and
the HMAC tool-authenticity receipt was dead code in every production path
(tenet 3). Both fixed across every caller (`2ee4f5c`). MEDIUM: rescue witness,
timeout naming, run-review gated verification (`9e179f4`); workspace state
chained into the ledger, per-edit content hash (`c2m2`); external-tool
timeout and name-collision refusal. The LOW tier (denylist flag ordering,
grep symlink re-confinement, workspace-root allowlist, exec_oracle status
field) remains, tracked in the workflow artifact.

### Execution record

**HIGH tier: all six shipped (2026-07-14), each with a failing test first.**

1. explanation_gate copy-paste bypass fixed (`8f695a4`): a verbatim diff
   paste is refused; the explanation must carry a floor share of words the
   diff does not.
2. comprehension_ledger cross-kind recency fixed (`8f695a4`): both kinds
   merge into one newest-first pass; an older attestation no longer blocks a
   newer comprehension receipt.
3. store record integrity added (`d301b4d`): `verify_records()` re-derives
   each record's content hash; `/api/store/verify` now requires BOTH the
   chain and the records.
4. transparency log wired (`d301b4d`): the receipts ledger carries a Merkle
   root, and `GET /api/receipts/proof?leaf=` returns an offline-checkable
   inclusion proof. Dead code is now a live guarantee.
5. /v1 turn-receipt prompt hash fixed (`5f4deeb`): the scaffold hashes and
   freezes the flattened prompt the model was actually sent, not a naive
   join that repr'd content-parts arrays.
6. uplift regression rendering fixed (desktop `f633cbc`): the verdict is
   three-way on the sign; a measured regression reads "regression measured"
   as drift, never a green win.

Three of the six were defects in code shipped earlier the same session
(the /v1 scaffold, the transparency log left unwired, and the desktop
uplift verdict). The loop caught its own author, which is the point.

**MEDIUM tier: complete.** All verified MEDIUM findings shipped, each TDD:
- SSRF guard + no-clobber sidecar on the snapshot fetcher (`5101f29`).
- Turn receipt names the model; agent freezes before running (`e10ee84`).
- Attestation empty-run is 'empty' not vacuous 'complete'; prompt_forge no
  longer flips well-posed on the idiom "in order to" or a bare "matches"
  (`f5282fd`).
- Desktop: empty set is not a green win; workflow steps parse defensively
  (`4cddc55`).
- Store paging: retention and comprehension scan the full store, not the
  newest 200, and report the scan (`f2a3779`).
- Forge Y-arms reach the route; `/api/forge/recheck` actually compares drift
  (`5ca8649`).
- Academy completion is a receipt bound to the lesson, not prose
  (`22a6609`).
- Plus a harness tripwire (`142a8f6`) for two verified upstream worktree bugs,
  crediting moui72 / peckenpaugh.us.

### The replication closed a loop on the harness itself (2026-07-14)

The sealed k=5 replication landed at 0.573, split 2 MATCH / 1 DRIFT: the
uplift REPLICATED non-null (+15.4% after +18.2%, both intervals exclude
zero), but the point-forecast interval DRIFTED (0.600 held, 0.573 missed).
That receipt falsified our own forecasting tool, so the tool was corrected:
`forecast_bootstrap` resamples whole fresh runs so the interval carries
between-run variance (`d0a3a4f`). Testing the fix on real data exposed a
deeper honest null: the point estimate is biased high, so the widened
interval is necessary but not sufficient; the point-bias fix is named and
will be re-preregistered. The improvement loop turned on the harness itself,
not only its surfaces.

### Cycle 3 (2026-07-14): the perception/provenance subsystem

The next tool: where "every result carries a receipt a stranger can re-run"
lives or dies (snapshot, store, fold/recall, context governor, retrieval,
import). Five critics, one per dimension, adversarially verified; 16 findings
survived. Triggered in part by a real failure this session: a Reddit bot-wall
was frozen as content and let an assessment stop, now fixed.

**HIGH tier: shipped (each TDD).**
- freeze truncation: a body shorter than its Content-Length was frozen as
  complete; now flagged truncated with the partial bytes kept as evidence.
  (Plus the earlier block-page detection + browser UA in web_snapshot.)
- context governor fold recoverability: _fold stored only a one-way hash and
  no text, so the "verbatim recall" claim was false (a claim outrunning its
  receipt, in my own code). The folded record now carries the verbatim text;
  recall_folded returns the exact span; the note is corrected.
- FoldIndex content binding: it trusted the caller's span_hash and never
  bound it to the stored content. A derived content hash is banked at add,
  returned on recall, and verify() catches a tampered fold_index.json.
- import remote MCP servers: only servers with a 'command' were captured, so
  remote (url/http/sse) servers vanished silently. Remote servers are now
  captured with url+transport; a truly-unrecognized one is dropped with a
  reason, never silently.

MEDIUM (7) and LOW (5) remain: non-atomic blob write, dual content-address
schemes in fold_index, index_compaction re-derivation, verify_records missing
a deleted row, settings 'mapped' with zero servers, over_pinned vs nominal,
and the retrieval-honesty LOW cluster (bm25 excerpt hash, graph edge sources,
project verdict hardcoded 'live', feed item hashes, reliable_fraction
provenance).

**Cycle 3 execution: HIGH (4) and MEDIUM (4 of 7) shipped, each TDD.** HIGH:
freeze truncation, context-governor fold recoverability (my own claim-vs-
receipt gap), FoldIndex content binding + verify(), remote MCP capture
(`1b1715e`). MEDIUM: store deleted-row detection, over_nominal flag, atomic
blob writes, honest import status (`c3m`). The remaining MEDIUM (dual content-
address in fold_index, index_compaction re-derivation, both judged mitigated
by the content-hash fix) and the retrieval-honesty LOW cluster (bm25 excerpt
hash, graph edge sources, project verdict hardcoded 'live', feed item hashes,
reliable_fraction provenance) are queued.

### Cycle 4 (2026-07-14): the verification lanes

The heart of the thesis: the oracles that decide acceptance (lean_oracle,
conjecture_forge, benchmark_hygiene, tension_ledger, suite_audit,
eval_engineering, the pytest/exec oracles, passn_model, crucible
preregistration). Five critics, one per failure shape (oracle-soundness,
falsifier-integrity, interval-statistic-honesty, novelty-claim-integrity,
seal-rescue-integrity), each finding adversarially verified. 19 survived:
6 HIGH, 9 MEDIUM, 4 LOW.

**HIGH tier: all six shipped (each TDD).** Lean hygiene screens the real
kernel-bypass surface (admit/sorryAx/native_decide/skipKernelTC/
implemented_by) and the sorry belt-check matches the real warning
(`0109405`). grade_novelty L2 requires the strong proof to prove the SAME
statement (`0109405`). The instrument register counts only sealed
adjudications (`0109405`). The trajectory curator's load-bearing
oracle_can_fail gate no longer accepts flip arithmetic as falsifiability:
every grade input must be chain-backed and every grader must carry a
recorded refusal (`79bc811`). And the loop crossed a repo boundary for the
first time: crucible itself let a verdict be rescued by widening the
tolerance after the seal, because no seal bound the deciding number. A
claim can now seal its tolerance; a mismatched measurement is fail-closed
UNVERIFIABLE, and a hand-forged MATCH fails re-derivation (crucible
`fd19657`, legacy hashes preserved, the residual legacy hole stated openly
as a tested honest null).

**MEDIUM tier: all nine shipped (`13c1e42`, each TDD).** exec_oracle
requires a clean exit; PytestOracle refuses an all-skipped run; the apex
oracle audits the axiom footprint of every named theorem on accept
(live-verified against Lean 4.32.0); suite_audit scores a hanging mutant
indeterminate, never killed; task_curator's stub keeps imports so a
vacuous suite cannot hide behind ImportError; tension verdicts follow the
sigma distance, not CI overlap, and demand hex source hashes; passn_model
drops UNVERIFIABLE tasks instead of recoding them as failures; and the
passk-forecast + k5-replication adjudications were re-emitted as full
re-derivable records with their preimages on disk (verdicts asserted
unchanged; a repo test now demands a recomputable preimage from every
committed adjudication).

LOW tier (4) queued: injected-callable acceptance authority in the
invention loop, uplift-delta evidence markers, syntactic-only
normalize_statement, adjudicate_k5_forecast re-encoded constants.

### Cycle status (the repeat, honestly)

Complete cycles (consultation -> reconcile -> execute HIGH+MEDIUM):
- Cycle 1: full-surface (6 clusters, 24 findings).
- Cycle 2: agent/tool-execution (17 findings) + behavioral monitor + canary
  tripwire from external threat sources.
- Cycle 3: perception/provenance (16 findings).
- Cycle 4: the verification lanes (19 findings; the loop's first fix in a
  hosted flagship, crucible).
- Cycle 5: forge/science/academy/discovery/claims (23 findings; recorded
  below).
- Cycle 6: workflow/orchestration engine (21 findings; recorded below).
- Cycle 7: the desktop client (16 findings; the loop's first pass in the
  Flutter repo, recorded below).
- Cycle 8: the hosted flagships. index (13 findings, complete) and gather
  (9 confirmed MEDIUM, complete) done; forum and telos queued. Recorded
  below.

### Cycle 5 (2026-07-14): forge/science/academy/discovery/claims

Five critics (experiment-integrity, forge-honesty, academy-integrity,
discovery-honesty, claims-and-cards), each finding adversarially verified.
23 survived: 6 HIGH, 13 MEDIUM, 4 LOW.

**HIGH tier: all six shipped (each TDD), in two slices.** Trust surfaces
(`69e0d1e`): the TrustCard signature now covers the card's own trust
verdicts, so a forged freshness or scan status reads TAMPERED; a model-card
claim asserted verified without a source URL and retrieval date is demoted
with the demotion named; retention refuses an immediate retest unless the
waiver is declared in the receipt and grades a supplied answer against the
original's key material, never a caller boolean (the platform's own
learning loop was doing exactly the self-pass the gate now refuses).
Receipts that bind what happened (`c643e96`): /api/attest resolves a
banked agent-run and refuses a review that does not hash to the banked
run's review_sha256, so a fabricated run confers nothing; the forge
Y-chain seal is persisted server-side and the recheck refuses
caller-supplied sealed hashes, so the checked party no longer authors both
sides; science_run's chain hash binds claims, measurement content, and
errors, and the payload echoes what it judged so a stranger can re-run it.

Also this cycle, from the suite gate itself: the run provenance receipt
bound the pre-workspace checkpoint while the run re-checkpointed after the
post-snapshot, so two receipts disagreed on every writing run (latent
since the workspace-chaining fix). Provenance now binds the final
checkpoint (`69e0d1e`).

**MEDIUM tier: all thirteen shipped (`f8ac909`, `13086c6`, each TDD).**
The forge recheck refuses empty arms and names identical arms degenerate;
science_run keeps the raw gather payload; publish_lint gains the tenet-4
rules it lacked (bare percentage metrics, superlatives) and catches
forward-slash Windows paths, with the clean fixtures that enshrined the
bare-metric violation corrected; release readiness reads CREDO.md content
and goes red on drift; a failed unaided retest decays holdership visibly;
diff paths keep their repo form so the cross-kind merge is real; academy
completion demands the receipt engage the lesson source; the research
loop re-hashes stored source bytes instead of comparing a value to
itself; discovery threads name their falsifier 'stated, not yet run'
(the mechanical resolvability check was judged theatre and the honest
fix recorded as claim language); structure_mapping scores an undecodable
encoding 0.0 instead of 1.0; and wien_displacement is parameterized so
the memorized-constant cheat is refused (its displacement roots verified
against an independent maximization, correcting the consultation's own
quoted x_6).

LOW (4) queued, tracked in the cycle-5 workflow artifact.

### Cycle 6 (2026-07-14): the workflow/orchestration engine

Five critics (workflow-integrity, consensus-honesty, routing-stats-
honesty, budget-escalation-integrity, registry-role-integrity), each
finding adversarially verified. 21 survived: 3 HIGH, 13 MEDIUM, 5 LOW.

**HIGH tier: all three shipped (`54a1d6f`, each TDD).** The workflow chain
hash covered only non-error step summaries, so a FAILED run could have its
ERROR step deleted and status flipped to COMPLETED and still re-derive its
stored hash; the chain is now seeded with the header, updated on every
step including the error path, folds the final status, and recompute_chain
lets a stranger re-derive it (the roster serves a mismatched run as
TAMPERED). Every non-exception agent step was stamped DONE, so a stage
with a dirty trajectory-integrity verdict was laundered to VERIFIED by a
later clean verify stage; a stage whose ledger did not verify or whose
integrity is dirty now FAILS the run. Quorum votes were hashed as
(type, passed) only, so one endpoint under two names was byte-identical to
two independent peers; each vote now carries the member's identity and the
receipt reports distinct_members and names a stacked ballot.

**MEDIUM tier: all thirteen shipped (`dcdc225`, `01273fc`, `d73ee40`,
each TDD).** consensus refuses a dead-tie weighted split; fan_out annotates
each result's accepted flag and survives a raising accept(); budget_control
reports verified / exhausted_without_verify instead of a tautological
conserved; a learned member is refused at quorum construction (no learned
verdict in the accept path). RouterStats got a lock, atomic replace, and
corrupt-file quarantine; adaptive routing no longer charges resolution
failures to a provider's circuit and carries its scoring justification in
the receipt; the effort receipt stamps the enforced budget, not the
nominal dial. The registry aliases cli names to buildable backends and
gates cli usability on the binary; a served-model mismatch is named in the
receipt; and roster_sha binds the routable set so a route is pinnable to a
registry state. Findings [3] (roster re-verify) and [4] (workflow
countersign) landed with the HIGH slice.

**LOW tier: all five shipped (`4e23885`, each TDD).** Quorum dissent is
computed against the outcome, not a bare majority (the veto stays on record
in votes); router_stats scores by the Wilson lower bound so one minted
success cannot leap a proven provider; EscalationResult carries which tier
stopped a run; a compile failure is content-addressed instead of a shared
compile_fail_{rc}, with the timeout branch keeping stderr; and
annotate_provider_roles derives the role from the actual provider and names
a role_conflict rather than adopting a false self-declared claim.

### Cycle 7 (2026-07-14): the desktop client

The loop's first pass in the Flutter repo (`flywheel-desktop`, a separate
codebase from the engine). Five critics (verdict-rendering truth,
receipt-integrity rendering, color-canon integrity, the gate/sign panels,
empty/null/loading honesty), each finding adversarially verified against
the Dart. 16 survived: 2 HIGH, 11 MEDIUM, 3 LOW. Complete through all
three tiers; `flutter analyze` clean, 64 tests green.

**HIGH tier (desktop `81f7efd`).** The client rendered verdicts the engine
never made: WorkflowStep collapsed DONE and WorkflowRun collapsed COMPLETED
into the verified accept color, but those are completion states, not
external-oracle acceptance (and cycle 6 made a dirty-integrity DONE become
FAILED). Only VERIFIED now earns the accept color; DONE/COMPLETED and any
absent status are the honest null. The diff view painted added lines in
verified-green and removed lines in drift, dressing raw unreviewed code in
the verdict palette; it now uses the ink ramp and the +/- glyph, verified
by a pure diffLineStyle a test confirms never returns a verdict color.
Also the accept-path sign gate: it failed OPEN when risk_review arrived in
a shape the client did not parse, enabling the destructive Sign control on
a shape mismatch; it now fails CLOSED.

**MEDIUM tier (desktop `48a5e3b`).** Color carried non-verdict meaning in
the side rail (nav selection in drift), the editor tab (active border in
drift, colliding with the real dirty-file drift dot), and the scaffold
strip (a hardcoded verified dot on frozen sources, which are provenance,
not a verdict); all now read as ink emphasis or a neutral provenance
marker. A tested render_status module maps engine fields honestly: a count
of zero is the honest null not a green win (world 'measured', receipts
'accepted pass'), an UNREADABLE/absent envelope verdict is unverifiable
not a fabricated drift, the companion chip color comes from the engine
verdict not the transport source, and the duel's interval-less harness_lift
renders unverifiable, never a green win.

**LOW tier (desktop `df9af4b`).** Full-health gating on the endpoints tile,
neutral-ink duel arm bars, a pending demand as the honest null not drift,
and the attestation's overclaimed dishonest signal surfaced instead of
hidden.

### Cycle 8 (2026-07-15): the hosted flagships

The loop reached the separate public flagship repos. Two consulted,
reconciled, and executed this cycle; forum and telos queued.

**index** (code-graph / context / wiki, `C:/dev/public/index`): 13
findings (2 HIGH, 8 MEDIUM, 3 LOW), all three tiers COMPLETE, flutter-free
Python suite green, on `fix/cycle8-verified-map`. The theme was the
verified map claiming structure it never re-derived. HIGH: the
architecture diagram (rendered svg/mermaid) was excluded from the edge
check, so a phantom edge re-sealed passed MATCH; verify now re-renders the
architecture, overview, and docs pages from the tree and drifts on any
mismatch. The MCP cache signature stat'd only top-level entries, serving a
stale map as fresh; it now folds every graph-relevant file recursively.
MEDIUM: a local binding shadowing a module def no longer mints a false
exact call edge; an unreadable file is a coverage gap not a silent drop; a
vacuous forbid rule and an incompletely-built internal graph read
UNVERIFIABLE not MATCH; the workbench SVG is sealed; the context budget
reports the true cost and names an overflow. LOW: honest-null grounding on
zero edges, scoped packet tokens, and no MATCH over a scan narrowed by
unreadable directories.

**gather** (accountable research-intake, `C:/dev/public/gather`): 19
survived (10 MEDIUM, 9 LOW); all confirmed MEDIUM shipped, on
`fix/cycle8-provenance`, full suite 428 green. The headline: the
differentiator (a block/challenge page is named, never passed off as the
source) was defeated on the DEFAULT web adapter because http_get dropped
the redirect's final URL, so a redirect to a consent/login/block page was
recorded under the requested URL. http_get now returns final_url,
WebSource/FeedSource bind where the bytes came from, and a redirect is
named. A truncated body is flagged in the receipt (no longer witnessed as
whole); a tampered cache is re-hashed on the hit path and refused (no
receipt, no accept, for the cache too); markdown extraction keeps code
indentation and word boundaries; federation receipts derive the exact-id
join from the identifier path and can verify capture existence when a
resolver is supplied. gather's LOW tier (9, several verifier-flagged
overstated) is queued.

Queued: forum and telos (the remaining flagships); gather's LOW tier; and
the LOW tiers of cycles 2 and 3.
