# V4 — decisions of record

The decisions that frame the reconcile loop, continuing the log in
F0-DECISIONS.md, F1-DECISIONS.md, R0-DECISIONS.md, R1-DECISIONS.md,
R2-DECISIONS.md, V2-DECISIONS.md, and V3-DECISIONS.md, and recorded in the same
shape the `adr-decision` kind captures. Each is accepted unless marked otherwise.

V4 is the reconcile band. It is the first band that decides, per surface, whether
a byte-drift is a safe mechanical fast-forward or a conflict a human must
adjudicate, and it acts on that decision: it writes the fast-forwards and raises a
durable human gate for the conflicts. It ships:

- `src/canon/reconcile_gate.py` — the pure gate/deadline kernel. `ConflictGatePolicy`
  configures how a conflict gate lapses; `resolve_with_deadline` folds a frozen
  absolute deadline against an injected clock; `reconcile_action` maps a resolution
  to the one commit bit (write or hold).
- `src/canon/reconcile.py` — the pure per-surface decision. `persona_fold` lifts
  V3's single-persona fold to a set; `classify` is the total lattice over
  (surface-drift verdict, persona fold); `classify_surface` runs the drift check,
  folds the crucible persona verdict in only on a byte-drift, and overlays any
  gate on file.
- `src/canon/reconcile_run.py` — the two-phase orchestrator. `reconcile` classifies
  every surface (reads only), then commits (writes fast-forwards and overrides,
  raises fresh durable gates for conflicts), and witnesses the run once;
  `run_witness_payload` is the path-clean receipt; `reconcile_exit_code` gates a
  build.

## D-51 — drift is measured against on-disk, no recorded base (three-way merge scoped out)
**Status:** accepted (this build, 2026-08-29).
**Context:** a git-style reconcile would carry a recorded base revision and do a
three-way merge (base against the pool render against the on-disk file) to tell a
canon edit from a hand edit inside the region.
**Decision:** V4 measures drift as V2 does, a two-way comparison of the rendered
region interior against what is on disk, with no stored base. canon owns the whole
region interior between the markers, so any interior edit is canon's to reconcile;
the hand-authored prose lives outside the markers and V2 already never scores it
(the byte boundary is the base). There is nothing a base revision would
disambiguate that the marker boundary does not.
**Consequence:** the reconcile loop needs no revision store and no base artifact.
A byte-drift inside the region is unambiguous: the pool moved, or someone edited
canon-owned bytes by hand, and either way the resolution is the same, re-render or
gate. `base_sha` stays out of the schema.

## D-52 — the reconcile target is the four catalog surfaces, the vault is not reconciled (honest null)
**Status:** accepted (this build).
**Context:** R2 mirrors the whole pool into an Obsidian vault of one note per
record. A reconcile loop could also detect and repair vault drift (a hand-edited
note body, a stale note).
**Decision:** V4 reconciles only the instruction surfaces in `SURFACE_CATALOG`
(the CLAUDE.md / AGENTS.md / SOUL.md region splices). The vault is a downstream
projection with its own fidelity verdict (`vault_fidelity.py`) and its own
one-way-body rule (D-27), so a hand-edited note body is already defined as inert,
not drift. Reconciling the vault would re-derive a second, differently-shaped
decision lattice for no new safety.
**Consequence:** one decision lattice over one surface kind. Vault reconcile is
recorded here as a deliberate scope-out, not an omission; if it is ever wanted it
is its own band over `vault_mirror.plan_vault`, which already reports orphans and
off-limits notes without deleting.

## D-53 — persona-to-surface coupling is scope-coarse
**Status:** accepted (this build).
**Context:** the hard edge folds a persona's basis health into the fast-forward
decision for a surface. That needs a rule for which personas gate which surface.
canon tracks a record's `scope` (global or workspace) but does not track which
individual block or persona authored which line of a rendered surface.
**Decision:** a persona couples to a surface by scope, through
`contributing_personas`, which mirrors the block render contribution exactly:
`pool_for` applies the authored-split, then the global-scope filter drops
non-global records for a global surface. Every persona that survives that filter
gates the surface. There is no finer per-block attribution, because canon does not
record one.
**Consequence:** the coupling is exactly as coarse as canon's real provenance. A
workspace persona gates every workspace surface in its harness set, which is the
truthful statement of what canon knows. Claiming a tighter coupling would invent
attribution the record does not carry.

## D-54 — the classification lattice, and which classifications gate a human
**Status:** accepted (this build).
**Context:** the reconcile decision is a function of two inputs: the surface-drift
verdict (match / drift / off-limits / missing / refused) and the persona fold on a
drift (none / match / unverifiable / drift).
**Decision:** `classify` is a total lattice. A match is IN_SYNC (no write to
decide, so the persona verdict does not enter). A byte-drift dispatches on the
fold: a sound or absent basis (MATCH or NONE) is a FAST_FORWARD; an honest null
(UNVERIFIABLE) is HELD; a proven drift (DRIFT) is a CONFLICT. off-limits and
missing are benign skips; refused is a structural fault. Only CONFLICT and HELD
raise a human gate; a fast-forward writes on its own, and a skip or a refusal never
gates.
**Consequence:** the fast-forward-against-conflict call is exactly the persona fold
at the byte-drift fork, which is the V3 to V4 hard edge made mechanical. A surface
canon can safely re-render never bothers a human; a surface whose basis eroded
always does.

## D-55 — an unverifiable basis holds like a conflict, it is never fast-forwarded
**Status:** accepted (this build).
**Context:** a byte-drift can ride on a persona whose basis is unmeasurable (an
empty basis, D-47, or any axis crucible could not check). The loop must choose:
fast-forward it (trust the render) or gate it (ask a human).
**Decision:** UNVERIFIABLE folds to HELD, which gates. canon does not fast-forward
a surface whose basis soundness it cannot establish. This is the "no receipt, no
accept" discipline at the reconcile edge: absence of a drift proof is not a
soundness proof.
**Consequence:** the loop errs toward a human on an honest null, never toward a
silent write. HELD is a distinct classification from CONFLICT (the fold that
produced it differs, unverifiable against proven-drift) so the witness and the gate
payload record which one held, but both route to the same human gate.

## D-56 — classify fails closed to REFUSED on any out-of-vocabulary input
**Status:** accepted (this build).
**Context:** an earlier synthesis of the lattice mapped an unrecognized
(verdict, fold) pair to HELD, on the reasoning that an unknown state is one a human
should look at. `classify` receives its verdict from `drift.py` and its fold from
`persona_fold`, both closed vocabularies.
**Decision:** an input outside either closed vocabulary maps to REFUSED, not HELD.
An unknown verdict or fold is not a state a human should adjudicate, it is a wiring
fault: canon produced a value its own lattice has no rule for. REFUSED reports the
fault, writes nothing, and raises no gate; HELD would summon a human to adjudicate
a bug, and would file a spurious gate. This is the STATE-versus-WIRING boundary:
`classify` stays total (it returns a verdict, never raises), but the verdict for a
malformed input is the structural-fault one, not the ask-a-human one.
**Consequence:** a lattice bug surfaces as a REFUSED (a red build via
`reconcile_exit_code`) with no spurious human gate and no write, which is the loud,
safe failure. The divergence from the earlier HELD synthesis is deliberate and
recorded here.

## D-57 — the persona assessor fires only on a byte-drift
**Status:** accepted (this build).
**Context:** the crucible assessor is an injected seam (D-44) and may be a real
engine call, not free. `classify_surface` could assess every surface's personas
unconditionally.
**Decision:** `classify_surface` runs `persona_health` only when the drift verdict
is DRIFT, the sole fork where the fold changes the classification (a match is
IN_SYNC whatever the fold; a skip or refusal never consults it). On every other
verdict the personas tuple is empty and the fold is NONE.
**Consequence:** the external verdict is consumed exactly at the fast-forward-
against-conflict edge and nowhere else, which is both cost-honest (no assessor call
on an in-sync or off-limits surface) and semantically exact (the persona verdict
only ever discriminates a byte-drift).

## D-58 — the block filter: render legs see blocks only, the health leg sees the full pool
**Status:** accepted (this build).
**Context:** `surface_drift` and `write_surfaces` render a surface through
`resolve_blocks`, which raises `LayeringError` on any record that is not a
personality-block. The pool `classify_surface` receives is the whole pool,
personas included.
**Decision:** the drift check and the commit write are fed
`[r for r in pool if r.kind == KIND_PERSONALITY_BLOCK]`, the only records a surface
renders. This is both a totality fix (a persona in the pool can no longer raise a
`LayeringError` out of the drift or write leg) and semantically exact (surface
bytes derive from blocks alone). The persona-health leg is fed the full pool,
because a persona's basis can resolve against any record at any scope.
**Consequence:** `classify_surface` is total over a schema-valid pool. This also
discloses a latent V2 defect: `surface_drift` is not total over a mixed pool today
(a caller who hands it personas gets a `LayeringError`, not a verdict). V4 works
around it at the call site; the root fix (filter inside `surface_drift`, or catch
`LayeringError` to REFUSED) is a separate V2 task, recorded so it is not lost.
The root fix landed in D-68 (this build): `surface_drift` catches `LayeringError`
and folds it to `VERDICT_REFUSED`, so V4's call-site pre-filter is defense in depth,
not a workaround for a still-broken drift leg.

## D-59 — the pure gate/deadline kernel, with a fail-closed lapse
**Status:** accepted (this build).
**Context:** a conflict gate carries a deadline so a stalled decision cannot hold a
build hostage forever, yet a lapsed gate must never silently ship a change no one
approved. The deadline logic is the subtle heart of that contract.
**Decision:** `reconcile_gate.py` is a pure kernel, split out to prove in isolation
with no IO, no clock, and no pool. `resolve_with_deadline` reads no wall clock: the
caller injects `now`, so the semantics are deterministic and testable. The boundary
matches forum's gate model (`forum/src/forum/gates.py`): `now == deadline` is not
strictly before the deadline, so it expires. The default `on_expiry` is reject,
forum's safe default, so a gate no one answered lapses closed. A resolution outside
the vocabulary raises from `reconcile_action` (a loud wiring fault); the kernel
still fails closed to reject if a garbage `on_expiry` slips past the policy guard.
**Consequence:** the deadline math is provable without a clock and cross-references
forum's model by shared string values, though canon imports no engine. A lapsed
gate defaults to the safe decision; an approve-on-lapse is opt-in per gate.

## D-60 — the durable deadline and on_expiry are frozen into the gate at raise time, and the read side never consults live policy
**Status:** accepted (this build; the read-side contract tightened during the
recorded audit, see finding W-1 below).
**Context:** a conflict gate raised in one run is resolved (or lapses) in a later
run. The deadline and the lapse decision could be re-derived from the live policy
at resume time, or frozen at raise time into the gate record.
**Decision:** at raise, `reconcile` freezes the absolute deadline
(`now + policy.deadline_seconds`, or None if unbounded) and the `on_expiry` into
the gate payload; `_gate_payload` always writes both keys. On resume, the read side
reads them back straight off the gate reply and evaluates them against the resume's
injected `now`. The read side takes no policy at all: `classify_surface` and
`_apply_gate` carry no `policy` parameter, so the resume structurally cannot borrow
a live value. A materialized (non-None) reply is therefore required to carry both
`deadline` and `on_expiry`; a reply missing either raises `ValueError`, a loud
wiring fault in the same class as an out-of-vocabulary resolution. Only the
resolution defaults, to PENDING, because a freshly raised gate legitimately carries
no decision yet.
**Consequence:** a gate lapses on the terms it was raised under, and it is
impossible for a later policy to leak into the lapse decision, because the read
path has no policy to leak. A build that shortened its conflict window yesterday
does not retroactively lapse a gate raised last week under a longer one. The frozen
record is the contract, and its completeness is enforced, not assumed. This
inverts the read-side default the pre-audit build carried (an absent `on_expiry`
fell back to `policy.on_expiry`), which is the W-1 fix recorded below.

## D-61 — the gate identity is the path-clean public gate_key
**Status:** accepted (this build).
**Context:** the raiser (the orchestrator, commit phase) files a gate, and the
reader (`_apply_gate`, classify phase, possibly on another machine or another run)
looks it up. They must agree on the identity, or a raised gate is never found on
resume.
**Decision:** `gate_key(surface)` is the one shared identity: `{harness, scope,
relative_path}`, path-clean, never an absolute host path. It is public so both the
raiser and the reader import the one definition rather than each spelling a key by
hand. A gate raised on one machine resolves on another because the key carries no
machine-specific path.
**Consequence:** the raise and its later resume agree on identity by construction.
The gate store is keyed by a portable identity, so a conflict raised in CI resolves
at a developer's desk against the same key.

## D-62 — two-phase: classify all (read-only), then commit, then witness once
**Status:** accepted (this build).
**Context:** the loop both reads (drift, persona health, gates on file) and writes
(fast-forwards, gate raises, the run witness). Interleaving them would let an early
write change what a later surface's classification sees.
**Decision:** `reconcile` is two-phase. Phase one classifies every surface through
`classify_surface`, which is strictly read-only (host read, assessor, gate read;
no `write_text`, no `gate_raise`). Phase two commits the decided outcomes at once:
the fast-forwards and approved overrides batch-write, then each surface that still
needs a human gets a fresh gate. The run is witnessed once, after the commit, even
when nothing changed. A surface is never both written and gated in one run:
`_WRITE` is {FAST_FORWARD, OVERRIDDEN} and `needs_gate` is only ever true for
CONFLICT or HELD, and the two sets are disjoint.
**Consequence:** every classification in a run sees the same pre-commit world, so
the run is a consistent snapshot decision. The single post-commit witness records
the whole run as one event.

## D-63 — surfaces are independent: a refusal fails the build but never rolls back a fast-forward
**Status:** accepted (this build).
**Context:** a run can mix outcomes: one surface a clean fast-forward, another a
structural refusal (a deformed marker), another a conflict. The `write_surfaces`
batch writer is all-or-nothing for the surfaces it is handed.
**Decision:** the commit hands `write_surfaces` only the write-class surfaces
(FAST_FORWARD, OVERRIDDEN), so the all-or-nothing batch covers exactly the safe
mechanical writes, which cannot refuse at write time (their render already
succeeded in the drift check, deterministically). A refusal on a different surface
is reported (`ok` is false, `reconcile_exit_code` returns 1) but does not roll back
an independent fast-forward. `ok` excludes CONFLICT, HELD, and REFUSED, and
includes OVERRIDDEN (a human approved it).
**Consequence:** a malformed surface fails the run loudly without holding a clean,
unrelated surface hostage. The granularity is the surface, which matches how the
catalog is authored: each surface is its own file with its own region.

## D-64 — the run witness is a path-clean, pool-bound receipt
**Status:** accepted (this build).
**Context:** the reconcile run is the first band that changes live files, so it
owes a receipt a re-derivation can check. That receipt must travel between machines
and must not leak an absolute host path.
**Decision:** `run_witness_payload` binds the run to its inputs and its outcomes.
`pool_digest` is a sha256 over the pool (every record's canonical `to_json()`,
sorted, joined), so the receipt names the exact record set the run read, not only
what it decided. Each surface row carries the path-clean identity
(`surface.relative_path`, never the absolute host path), the classification, the
drift verdict, the persona fold, whether it committed, and the two region hashes
from the drift check (the rendered interior and the on-disk interior). The absolute
host path is used only internally, for the committed-membership test, and never
enters the payload. The witness fires once per run, even an all-clean one.
**Consequence:** the run is a re-derivable event. Given the same `pool_digest` and
the same hosts, a re-run reproduces the same per-surface decisions, and each
decision is backed by a content hash, not a self-report. The receipt is portable,
because no machine-specific path is in it. `reconcile_exit_code` maps the same
verdict to a process status so a build gates on it.

## D-65 — the commit writes through the exact batch writer the drift check mirrors
**Status:** accepted (this build).
**Context:** `write_surface` (singular) renders the whole handed pool into one
surface, while `surface_drift` mirrors `write_surfaces` (batch) through `pool_for`.
For a two-file harness (claude-code's global and workspace files) these diverge:
the singular writer would render globals into the workspace file, the batch writer
routes them to the global file by the authored-split (D-21).
**Decision:** the commit writes through `write_surfaces(blocks, surfaces=(...))`,
the exact batch writer `surface_drift` mirrors. The write therefore renders byte-
identically to what the drift check classified, so a surface classified
FAST_FORWARD writes precisely the `expected` interior the drift check hashed, and
the run's witnessed `expected_sha256` is the sha256 of the bytes actually written.
**Consequence:** classify and commit cannot disagree about what a surface should
contain. The witness's expected hash is the write's content hash by construction,
which is what makes the receipt checkable rather than aspirational.

## D-66 — the commit phase is not transactional across seams, and that is the honest boundary
**Status:** accepted (this build; disclosed boundary, no code change).
**Context:** phase two performs three kinds of side effect through injected seams:
the batch write of fast-forwards and overrides (`write_surfaces`), a `gate_raise`
per conflict in a loop, and a single `witness` after both. The seams are separate
callables with no shared transaction. A `gate_raise` that raises partway through
the loop leaves earlier gates filed and the witness unfired, a partial commit with
no receipt.
**Decision:** V4 does not manufacture atomicity the seams cannot provide, and does
not swallow a seam failure to force the witness. A seam that raises propagates. The
reason this is safe rather than merely tolerated is the direction of the failure:
the writes run first and as one all-or-nothing batch (D-63), so a later
`gate_raise` failure cannot leave a half-written surface; it can only leave some
human gates filed without the run's summary receipt. That is a loud, incomplete
run a re-run re-derives from the same pool, not a silent wrong write. A cross-seam
transaction would require a two-phase-commit protocol the injected gate and witness
stores do not expose, which is a store-layer capability, not a reconcile-loop one.
**Consequence:** the atomicity guarantee is exactly the write batch, and it is
stated, not implied. If a future store grows a transaction handle, the loop can
bracket phase two in it; until then the honest contract is "the writes are atomic,
the gate-raise loop and the witness are best-effort after them, and a failure is
loud and re-derivable."

## D-67 — the gate is read in classify and re-read implicitly at raise; the double-read is a benign staleness window
**Status:** accepted (this build; disclosed boundary, no code change).
**Context:** `classify_surface` reads the gate in phase one to decide whether a
conflict already has a gate on file (so it does not re-raise). Phase two then acts
on that phase-one classification. Between the two phases the external gate store
could change (a human approves a gate, another run files one), so the raise
decision rests on a snapshot that may be stale by commit time.
**Decision:** V4 keeps the two-phase snapshot semantics (D-62) rather than
re-reading each gate immediately before raising. The staleness window is bounded
and its outcomes are benign in both directions. If a gate was approved between the
phases, this run still treats it as pending and does not write, and the next run
reads the approval and fast-forwards, one run late, never a wrong write. If a gate
appeared between the phases, `gate_raise` is idempotent on `gate_key` (the same
path-clean identity, D-61), so a second raise overwrites the same key rather than
forking a duplicate. Re-reading mid-commit would narrow the window but not close
it (the store can change again after the re-read) while breaking the consistent-
snapshot property that makes a run one decidable event.
**Consequence:** the loop trades a one-run latency on a race for a clean snapshot
semantics and no torn decision. The race cannot produce an unapproved write, which
is the only outcome that would matter; it can only defer a legitimate fast-forward
by a run.

## Recorded audit
An independent adversarial code review of the V4 modules ran against six contract
points: totality and the STATE-versus-WIRING boundary, the V3-to-V4 hard edge (the
reconcile decision consuming the external crucible verdict, not a self-report), the
two-phase read-then-commit split, the block-filter, the durable-deadline freeze,
and the path-clean witness. It confirmed all six as built and surfaced three items.

- **W-1 (warning, folded).** The read side defaulted an absent gate `on_expiry` to
  the live `policy.on_expiry`. Traced fail-open direction: a gate frozen under
  reject-on-lapse, whose `on_expiry` key is dropped by a lossy gate store, resumed
  under a live approve-on-lapse policy, would lapse to APPROVED and silently write a
  conflict no human saw. Folded TDD-style: the read side now takes no policy, a
  materialized reply must carry both frozen fields, and a missing field raises a
  loud wiring fault. Recorded in D-60; test
  `test_a_materialized_gate_reply_missing_a_frozen_field_is_a_wiring_fault`.
- **I-1 (info, disclosed, no change).** The commit phase is not transactional across
  the write, gate-raise, and witness seams. Judged a genuine but accepted boundary:
  the writes are atomic (D-63), so the only exposed failure is loud and
  re-derivable, and cross-seam atomicity needs a store capability the seams do not
  expose. Recorded in D-66.
- **I-2 (info, disclosed, no change).** The gate is read in classify and again
  implicitly at raise, a TOCTOU window. Judged benign in both directions: a race can
  only defer a legitimate fast-forward by one run, never produce an unapproved
  write, and `gate_raise` is idempotent on the path-clean key. Recorded in D-67.

Outcome: 0 critical, 1 warning folded, 2 info disclosed. Full suite 407 passed
after the fold. V4 is marked done for this band.

## D-68 — surface_drift folds LayeringError into a verdict, closing D-58
**Status:** accepted (this build; root fix for the V2 defect D-58 disclosed).
**Context:** D-58 recorded a latent V2 defect. `surface_drift` caught
`RegionError` and `RenderRefused` only, so a mixed pool (personality blocks
alongside any other kind, e.g. a persona synthesized from the same store or an
episodic memory) leaked a `LayeringError` out of the drift leg instead of
returning a verdict. V4 worked around it at the call site by filtering the pool
before `classify_surface` (see D-58), which fixed the reconcile path but left
the drift API itself non-total for a realistic caller.
**Decision:** `surface_drift` catches `LayeringError` alongside `RegionError`
and `RenderRefused`, returning `VERDICT_REFUSED` with a "layering refused: {exc}"
reason. The module docstring's totality guarantee ("every refusal is a verdict,
never raised") now holds over a realistic mixed pool, and the whole-catalog
`drift_report` stays total on that pool with `ok=False` and exit code one.
**Consequence:** V4's call-site pre-filter becomes defense in depth rather than
a load-bearing workaround. Two TDD-style tests pin the fix against regression:
`test_mixed_pool_with_non_block_record_is_refused_not_raised` (single-surface)
and `test_drift_report_over_mixed_pool_does_not_raise` (whole-catalog).
Full suite 409 passed (407 + 2). `drift.py` at 134 lines, under the 300-line gate.
