# V2 — decisions of record

The decisions that frame the two verify-family gates, continuing the log in
F0-DECISIONS.md, F1-DECISIONS.md, R0-DECISIONS.md, R1-DECISIONS.md, and
R2-DECISIONS.md, and recorded in the same shape the `adr-decision` kind captures.
Each is accepted unless marked otherwise.

V2 is the first verify band over the render legs. It writes nothing. It ships two
read-only gates a build can key on:

- `src/canon/drift.py` — the rendered-surface drift check. `surface_drift`
  re-derives a managed surface from the pool and compares it to what is on disk,
  a sha256-keyed verdict per surface; `drift_report` maps the catalog;
  `drift_exit_code` turns the report into a process status.
- `src/canon/writing_gate.py` — the injected STE seam. `gate_text` scores prose
  against a profile through a caller-wired checker; a per-surface register binds
  each surface to its profile; `gate_surface` is the surface-aware entry.

## D-37 — the STE profile register binds each surface to a writing profile
**Status:** accepted (this build, 2026-08-29).
**Context:** The operator's writing standard is register-adaptive: strict for
procedures and commits, flavored for docs and READMEs and model cards, off for
essays. A rendered instruction surface is prose, so it has a register, and the
gate needs to know which profile governs which surface. The profile names come
from the external `writing_profiles` module (`procedure`, `readme`, `chat`,
`research`, `model-card`, `narrative`).
**Decision:** a fixed register, `STE_PROFILE_BY_HARNESS_SCOPE`, maps each
`(harness, scope)` to a profile name. The instruction files (CLAUDE.md,
AGENTS.md) are documentation register and take `readme`; SOUL.md is the voice
surface and takes `chat`. The strict `procedure` profile governs error messages
and commits, which are not rendered surfaces, so it is deliberately unused here
(an honest null, not an omission). An unregistered surface falls back to
`readme`, the safe documentation default.
**Consequence:** the gate scores each surface at its own register, and adding a
future surface (GEMINI.md, the global SOUL.md) is one register row. The register
is canon's; the profile bodies stay external.

## D-38 — the writing gate is an injected seam, not an import
**Status:** accepted (this build).
**Context:** canon is self-contained and stdlib-only. The STE linter
(`check_writing.py`) and its profiles (`writing_profiles.py`) live outside this
repo, under `local-model/scripts`. canon cannot import them without taking a
runtime dependency on another tree and breaking the self-contained invariant.
**Decision:** the gate defines the seam and the caller wires the checker, the
same injection shape F1 used for the store handle (D-9) and R0/R1/R2 used for IO.
canon owns three things: the `WritingChecker` callable's shape
(`(text, profile_name) -> Mapping` with a `hard` key), the per-surface register,
and the `gate_text` pipeline. The caller supplies the real checker as
`lambda text, name: check_writing.check_text(text, writing_profiles.load(name))`,
so profile loading stays on the caller's side and canon never touches the linter.
An optional `PreCleaner` runs before the check as a cheap pre-clean. The wired
instance is Forum's `forum.prose.clarify` tool, adapted by
`forum_clarify_pre_cleaner` (amended 2026-10-01; it was `forum_prose_humanize`
before Forum renamed humanize to clarify). The adapter returns the result's
`output` and accepts two schema ids during Forum's alias window:
`forum.prose-clarification/v1` and the deprecated `forum.prose-humanization/v1`.
Any other schema id, or an `output` that is not a string, raises `ValueError`
before the checker runs, the same fail-closed posture as D-39.
**Consequence:** canon stays dependency-free and the gate is provable with a fake
checker. The real linter and canon's gate agree on the verdict by construction,
since both read the same `hard` signal.

## D-39 — a file passes iff the checker reports an empty hard list
**Status:** accepted (this build).
**Context:** `check_text` returns a rich score (per-category counts, an em-dash
count, a hard-violation list). The gate needs one bit: pass or fail. Keying on
the wrong field would disagree with the linter's own CLI.
**Decision:** the gate passes iff the checker's `hard` list is empty, the exact
signal `check_writing --gate` keys on (`return 1 if (args.gate and any_hard)
else 0`). `GateResult.ok` is `not hard`, and `hard` carries the categories for a
caller that wants to report them. The gate reads the `hard` key directly and does
not catch a checker that raises: a raising checker, or a score with no `hard`
key, is a wiring fault for the caller to see, not a canon refusal to absorb.
Reading the key directly also fails closed on a malformed score, rather than
green-lighting when the pass/fail signal is absent (which a defaulted lookup
would do).
**Consequence:** the gate and the linter CLI never disagree on a verdict. The gate
is a thin, honest projection of the checker's own signal, and a broken checker
surfaces as a fault instead of a silent pass.

## D-40 — drift scores the region interior, and mirrors the batch writer
**Status:** accepted (this build).
**Context:** a managed file is `prefix + inner + suffix` (R0 region). Only
`inner` is canon's to write; the prefix and suffix are hand-authored host prose.
And there are two writers: the singular `write_surface` renders the whole pool it
is handed, while the batch `write_surfaces` applies the authored-split (D-21) per
surface. They diverge on a two-file harness's workspace file. The drift check
must compare the right bytes against the right derivation.
**Decision:** `surface_drift` compares the region interior, not the whole host
file, so a change to the host's own prose outside the markers is never drift and
a change inside the region always is. It re-derives through `pool_for`, mirroring
the deployed batch writer `write_surfaces`, so the authored-split is the on-disk
contract it enforces: a merged workspace file (what the singular writer would
produce) is itself flagged as drift. This is why `pool_for` was promoted from a
private to a public seam, so the R1 writer and the V2 verifier resolve one split.
**Consequence:** drift is scoped to canon-owned bytes and pinned to the writer
that actually deploys. Outside edits stay the host's; a divergence from the
authored-split fails the gate.

## D-41 — the verdict is sha256-keyed and the catalog is the manifest
**Status:** accepted (this build).
**Context:** the drift verdict needs a stable key a caller can log and diff
across runs, and V2's spec names a "manifest" of which blocks render to which
file.
**Decision:** `SurfaceDrift` carries the expected and actual interior sha256
(set for a match or a drift, the two cases where both interiors exist), so a
caller keys drift on a digest rather than re-diffing prose. The
`SURFACE_CATALOG` plus `pool_for` already is the manifest of which blocks render
to which file, so V2 adds no separate manifest artifact. `drift_report` maps the
catalog and `drift_exit_code` gates a build (zero clean, one on any drift or
refusal).
**Consequence:** the drift record is a content digest, and the manifest is the
catalog canon already ships.

## D-42 — both V2 gates are total and read-only
**Status:** accepted (this build).
**Context:** V2 is a verify band. It must never mutate a surface, and a
constructible input must never crash the gate mid-run (the fidelity gate's
discipline, R0 D-14).
**Decision:** `drift.py` imports no writer path and is total: every refusal (an
absent file, a deformed marker, a mis-scoped region, a render the pool cannot
represent) is returned as a verdict (`missing`, `refused`, `off-limits`), never
raised. `writing_gate.py` writes nothing either; it trusts its injected checker's
contract, which is the one place a fault surfaces to the caller rather than being
swallowed.
**Consequence:** a build can run both gates against the real allow-list with no
risk of a write and no risk of an unhandled exception from canon's own refusals.
