# F0 — decisions of record

The operator rulings that frame canon. These are recorded here in the same
shape the `adr-decision` kind captures, so the record schema and the project's
own decision log agree. Each is accepted unless marked otherwise.

## D-1 — Render scope is global + workspace only
**Status:** accepted (operator, 2026-08-28).
**Context:** A record could in principle be scoped to any of the ~90 repos under
the workspace, which would let canon render into per-repo instruction files.
**Decision:** Exactly two scopes, `global` and `workspace`. No `repo` scope. The
per-repo `CLAUDE.md` / `AGENTS.md` files stay hand-authored so each project repo
stays self-contained; no record is scoped to a repo and no render touches one.
**Consequence:** `scope` is a closed two-value set in the schema and the
validator. The render-scope allow-list (F0-SECTION-OWNERSHIP.md) is a fixed file
list, not a per-repo expansion.

## D-2 — One block set, per-scope overrides at render time
**Status:** accepted (operator).
**Context:** The personality could be modeled as separate global and workspace
canons, or as one set with overrides.
**Decision:** One canonical block set. A `workspace` block overrides a `global`
block of the same id at render time; global-only blocks are always present.
**Consequence:** `src/canon/layering.py` implements exactly this, keyed by record
id, current-entries-only, deterministic order. See F0-LAYERING.md.

## D-3 — SOUL.md is a projection, not a second canon (ruling b)
**Status:** accepted (operator, via the adversarial design pass).
**Context:** Hermes treats `SOUL.md` as a real shipping persona format, which
risked becoming a second source of personality truth alongside the block set.
**Decision:** `SOUL.md` is rendered *from* the single canonical block set. It is
a projection target on the render-scope allow-list, never an independent persona
canon. The reverse leg reads it back into the same block records.
**Consequence:** No record kind is "a SOUL.md"; there is one
`personality-block` kind, and SOUL.md is one of its render targets.

## D-4 — Name canon; give it a standalone public repo
**Status:** accepted (operator, 2026-08-28).
**Context:** The container is a net-new assembly and needed a name and a home
before F0's first file, respecting the never-rename-without-a-plan rule.
**Decision:** Name it **canon**. Home it at a new standalone public repository,
self-contained (it does not inherit a workspace-level canon).
**Consequence:** Container code stays out of `project-docs`. The assessment doc
in the workspace remains the plan; this repo is the build.

## D-5 — V3 → V4 verification edge is kept
**Status:** accepted (operator, 2026-08-28).
**Context:** The build plan's serial spine has an eight-deep critical path; the
V3 → V4 edge was the one sequencing question left open.
**Decision:** Keep the edge. V3 and V4 stay serial. The eight-deep spine
(F0 → R0 → R1 → R2 → V2 → V3 → V4 → M4) is a hard dependency of record.
**Consequence:** No phase after V3 starts before V3 lands; the plan does not
parallelize across that edge.

## D-6 — Build boundary
**Status:** standing (operator authorization "Go", 2026-08-28).
**Context:** "Go" lifted assessment-only and authorized the build.
**Decision:** The build proceeds phase by phase starting at F0. Every phase
lands on a branch, never on `main`. Pushing, opening a PR, and deploying each
need a separate explicit go. M4's live cross-provider transport keeps its own
deploy-go on top of that.
**Consequence:** F0 lands on `feat/f0-canonical-schema`, committed, not pushed.
Later phases each get their own branch and their own gates.
