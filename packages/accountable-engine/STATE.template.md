# <Platform> -- STATE - read this first

> Single source of truth for agents and humans. Read top-to-bottom before any
> work. If your work changes the state, you change this file in the same commit.
> State is a receipt, not a vibe -- every claim cites a commit, a test, or an ADR.

## 0 - How to work here (the protocol)

1. **Read.** This file, then the target component's docs. Don't re-derive what's
   recorded -- trust the receipts and build on them.
2. **Claim.** Take one unit from Section 4 Open edges. Add a row to Section 3 In flight with
   your branch and session id. One unit = one branch. First claim wins.
3. **Isolate + build.** Work on a fresh branch / worktree. Stay inside your
   claimed unit -- no "while I'm here" drift.
4. **Receipt + record.** Before you call it done, produce a receipt: a green
   build/test result, an ADR, or a verdict -- never an assertion. Move your unit
   from Section 3 to Section 6 with that receipt.

Conflict-avoidance = the claim ledger (Section 3) + branch isolation.
Compatibility = explicit contracts/interfaces + the ADR trail.

## 1 - What this is

<one paragraph: the platform, its components, the environment contract, the
component manifest.>

## 2 - The map (component - maturity - receipt)

| Component | Path | Maturity | Receipt |
|---|---|---|---|
| <name> | <path> | <honest state> | <commit / test count / ADR> |

## 3 - In flight (claimed work -- do not touch another agent's claim)

| Unit | Branch | Agent / session | Started | Status |
|---|---|---|---|---|
| _(none)_ | | | | |

## 4 - Open edges (claimable units)

| id | Component | What | Definition of done (the receipt that closes it) |
|---|---|---|---|
| <ID-1> | <component> | <the work> | <the build/test/ADR that proves it> |

## 5 - Conventions & bounds (bounded autonomy)

**Agents MAY, without asking:** read anything; create branches/worktrees; run
builds and tests; write ADRs; update this file; commit on a *feature* branch.

**Operator-gated -- do NOT without explicit sign-off:** merge to main; push to any
remote; deploy; touch live credentials; advance anything declared out-of-scope;
delete load-bearing infrastructure.

**Rules:** one unit per branch - receipt required before "done" - every
non-trivial decision becomes an ADR - keep the diff to your claimed unit.

## 6 - Ledger (append-only -- what shipped, with its receipt)

- <date> - <component> - <commit> -- <what> - receipt: <the proof>
