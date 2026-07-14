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

### Execution record
