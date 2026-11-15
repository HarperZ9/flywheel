# M4.4 — the canon_check composition

M4.4 folds canon's four verdict-returning check legs into one aggregate a build
keys on. It adds no new schema, no new capability, no new refusal type: it runs
existing verdicts and composes their `ok` bits. The composition is read-only
(D-100). `reconcile` is a write action, not a check, and stays out of the
composition; a caller who wants a run-and-check composes `reconcile` on top.

Code: `src/canon/canon_check.py`. Tests: `tests/test_canon_check.py`.
Everything is stdlib-only. Every leg is optional and gates on which seams the
caller wires.

## The interface

The composition ships one function, one report dataclass, and one exit-code
mirror.

| callable | contract |
|---|---|
| `canon_check(pool, *, home=None, workspace=None, read_text=None, assess=None) -> CanonCheckReport` | run every leg whose seam is wired, fold verdicts, return the aggregate |
| `canon_check_exit_code(report) -> int` | 0 iff every wired leg passed, 1 otherwise; mirrors `drift_exit_code` and `reconcile_exit_code` |

`CanonCheckReport` is a frozen slotted dataclass. Every leg field is
`None`-able: a leg without its seam wired lands as `None` in the field and does
not affect `ok`.

| field | type | on a disabled leg |
|---|---|---|
| `drift` | `DriftReport \| None` | `None` unless `home`, `workspace`, and `read_text` are all wired |
| `vault` | `VaultVerdict \| None` | always runs (pool-only) |
| `vault_symmetric` | `VaultReadVerdict \| None` | always runs (pool-only) |
| `persona` | `tuple[DriftVerdict, ...] \| None` | `None` unless `assess` is wired |
| `ok` | `bool` | `True` iff every wired leg passed |
| `reasons` | `tuple[str, ...]` | one label per failed leg, empty on `ok` |
| `exit_code` | `int` | `0` iff `ok`, else `1` |

## The four legs

Every leg is a verdict M4 already ships. `canon_check` runs them and reads
their existing `ok` bits.

| leg | seam | source | pass rule |
|---|---|---|---|
| drift | `home` + `workspace` + `read_text` | `drift.drift_report` (V2) | every surface verdict in `_OK_VERDICTS` |
| vault | pool | `vault_fidelity.vault_roundtrip_report` (R2) | no refusals, no undeclared losses |
| vault_symmetric | pool | `vault_read_fidelity.vault_symmetric_report` (M4.2) | write leg, read leg, and pool match all clean |
| persona | `assess` | `persona_thesis.assess_persona` (V3) | every persona verdict is `MATCH` |

The drift seam is a triple: partial wiring (any of the three missing) reports
`None`, never a partial run. `read_text` accepts the same `str | None` shape
V2 already uses. The vault legs need nothing beyond the pool.

The persona leg iterates every `synthesized-persona-l3` record in the pool and
runs the injected crucible assessor once per persona. `assess` is the same
`Callable[[dict], list]` shape V3's `assess_persona` takes.

## The persona pass rule

`MATCH` is the only aggregate-ok state (D-46 fail-closed carried up).

| verdict | aggregate | reason label |
|---|---|---|
| `MATCH` | leg passes | (empty) |
| `DRIFT` | leg fails | `persona:DRIFT` |
| `UNVERIFIABLE` | leg fails | `persona:UNVERIFIABLE` |

`UNVERIFIABLE` fails closed for the aggregate, matching V2's empty-hard-list
pass signal (D-39): a caller who wants a checked build wires a real assessor,
not a permissive stub. The V3 verdict shape is preserved on the report, so a
caller reading `report.persona` alone can tell the fail class.

## What canon_check never does

It does not raise. Every leg is documented total on hostile input the leg
already handles; the composition never wraps an assertion or a filter around
a leg's return value.

A wiring fault a leg raises (an assessor that returns a mapping without the
count keys V3 reads by direct index, for instance) propagates out to the
caller. That preserves V3's D-38 / D-39 discipline: a wiring bug is a loud
bug, not a silent MATCH.

## What stays out

Honest nulls, listed so a reader knows what M4.4 does not claim:

- `reconcile` is not a leg. It writes host files and raises durable gates
  (V4). A caller who wants a run-and-check composes `reconcile` and
  `canon_check` in that order.
- No new version pin. The composition is a code seam over four existing
  verdict shapes; adding a pin here would freeze the composition against the
  first shape change one of the four legs takes. Every leg carries its own
  pin already.
- No CLI. `canon_check_exit_code` is the surface a build script drives; the
  entry point stays out of the package until the build story earns one.
- No parallel run. The four legs are cheap and pool-bound; a threadpool would
  add wiring surface for no measurable speedup on the sizes canon runs.

## Containment

The composition adds no new file write, no new filesystem read, and no new
capability. `drift` uses the injected `read_text`. `vault` and
`vault_symmetric` run on the in-memory pool. `persona` runs the injected
assessor. Nothing else touches the host.

## Totality

`canon_check` produces a `CanonCheckReport` for every input the four legs
handle. The never-raises acceptance test parametrizes over an empty pool,
personality-only pools, an empty-basis persona, a broken-basis persona, and
the full triple, with every seam wired, and asserts a `CanonCheckReport`
lands each time.
