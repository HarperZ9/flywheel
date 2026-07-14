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
