# F0 — per-scope override layering

The operator's personality model is one canonical block set with per-scope
overrides layered at render time. `src/canon/layering.py` is that layering, and
only that: given a pool of `personality-block` records tagged `global` or
`workspace`, `resolve_blocks(pool, target_scope)` computes the effective set a
renderer would emit for that scope.

## The rules, in order

1. **Current only.** A record whose temporal block sets `valid_until` is
   superseded and excluded. No temporal block, or `valid_until` null, means
   current.
2. **Override by id.** Blocks are keyed by record id. A workspace block with the
   same id as a global block overrides it. A workspace-only id is added. A
   global-only id is always present.
3. **Scope containment.** A render at `global` sees only global blocks —
   workspace overrides never leak upward. A render at `workspace` sees global
   blocks overlaid by workspace blocks.
4. **Deterministic order.** The effective list is ordered by `create_ord`
   ascending, then by id. A record with no `create_ord` sorts after those that
   have one. A rebuild from the same pool is byte-identical.

Only `personality-block` records participate. Other kinds accumulate in a store;
they are not a canon that overrides itself, so passing a non-block record is a
caller error (`LayeringError`), reported rather than silently ignored.

## Same-id collapse

Two records can share one `(scope, id)` — the in-place supersede case, where an
edited block keeps its id and the old version carries a `valid_until`. Before
overlaying scopes, each `(scope, id)` group collapses to its surviving current
record; if several are current (a malformed pool), the highest `create_ord`
wins, and a tie on `create_ord` breaks on `source_hash` so the choice does not
depend on the pool's ordering. This keeps a superseded duplicate from shadowing
the current block.

## Retired overrides fall back, they do not suppress

There is no tombstone kind. When every workspace record for an id is superseded,
that workspace override no longer applies, so a workspace render falls back to
the current global block of the same id rather than removing the id. A workspace
override suppresses a global block only while the override itself is current.
An id is absent from a render only when no current block exists for it in any
contributing scope.

## Worked example (the test fixture)

`tests/fixtures/layering_pool.json` holds six blocks:

| id | scope | create_ord | current? |
|---|---|:---:|:---:|
| voice | global | 1 | yes |
| voice | workspace | 5 | yes |
| testing | global | 2 | no (valid_until 7) |
| testing | global | 9 | yes |
| shipping | workspace | 6 | yes |
| deprecated | workspace | 4 | no (valid_until 9) |

**Render at `global`** — global scope only; workspace blocks excluded:
- voice/global (ord 1)
- testing/global (ord 9) — the current copy wins the same-id collapse

Ordered by create_ord: **voice, testing.**

**Render at `workspace`** — global overlaid by workspace:
- voice → workspace/ord 5 overrides global/ord 1
- testing → global/ord 9 (no workspace override exists)
- shipping → workspace/ord 6 (workspace-only, added)
- deprecated → superseded, excluded

Ordered by create_ord (5, 6, 9): **voice (workspace), shipping (workspace),
testing (global).**

The expected sets are pinned in `tests/fixtures/layering_expected.json` and
asserted in `tests/test_layering.py`. That single fixture exercises override,
scope containment, in-place supersede collapse, and superseded exclusion at once.
