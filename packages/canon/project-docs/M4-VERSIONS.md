# M4.3 — the versions seam

M4.3 closes the pin question every wire canon owns has raised so far. F0 fixed
the record envelope at `canon.record/v1` as a bare string constant in
`schema.py`. R0 through R2 added more wires (region markers, textblock
grammar, frontmatter codec, vault-note codec, vault identity digest, vault hub
marker), and V2 through V4 added still more (drift verdict, writing-gate
register, persona-thesis payload, reconcile-gate policy, run witness). M4.1
and M4.2 added the transport seam and the vault frontend. Every one of those
wires deserves an independent version pin, so a future rewrite of one does not
force a re-cut of every other. M4.3 ships the pin registry and the migration
seam as one branch. It writes nothing on disk; it hands callers a typed
version vocabulary and a place to hang an explicit migrator when a wire ever
rolls.

Code: `src/canon/versions.py`, `src/canon/versions_migrate.py`. Tests:
`tests/test_versions.py`, `tests/test_versions_migrate.py`. Everything is
stdlib-only; both modules import from within canon only (schema for
`SCHEMA`-alias hand-off, and versions_migrate imports Record). No third-party
version library is added.

## The pin

`SchemaPin` is a frozen slotted dataclass with four fields:

| field | contract |
|---|---|
| `name` | short-name in `SEAM_PINS`; a Wave 1 name refuses at construction (D-92) |
| `version` | semver-lite; matches `^v(0\|[1-9]\d*)(\.(0\|[1-9]\d*))?$`; `v0.0` refused at construction (D-91) |
| `kind_tag` | wire literal; matches `^canon\.[a-z0-9-]+/v(0\|[1-9]\d*)(\.(0\|[1-9]\d*))?$` |
| `adr_ref` | free-text pointer to the decision that fixed this pin; metadata only, does not count for equality |

Every field runs a small validator in `__post_init__`; a bad construction
refuses `ValueError` (a wiring fault, distinct from the runtime
`VersionError` hierarchy per D-97). Two pins compare equal iff `name`,
`version`, and `kind_tag` are byte-equal; `adr_ref` is skipped so a decision
rename never breaks equality.

## The registry

Sixteen `PIN_*` constants live at module load in `versions.py`. The set is
closed by construction:

| constant | short-name | kind_tag |
|---|---|---|
| `PIN_RECORD` | `record` | `canon.record/v1` |
| `PIN_BACKEND_SEAM` | `backend-seam` | `canon.backend-seam/v1` |
| `PIN_TEXTBLOCK_GRAMMAR` | `textblock-grammar` | `canon.textblock-grammar/v1` |
| `PIN_REGION_MARKER` | `region-marker` | `canon.region-marker/v1` |
| `PIN_FRONTMATTER` | `frontmatter` | `canon.frontmatter/v0` |
| `PIN_VAULT_NOTE` | `vault-note` | `canon.vault-note/v0` |
| `PIN_VAULT_IDENTITY_DIGEST` | `vault-identity-digest` | `canon.vault-identity-digest/v1` |
| `PIN_VAULT_HUB_MARKER` | `vault-hub-marker` | `canon.vault-hub-marker/v0` |
| `PIN_DRIFT_VERDICT` | `drift-verdict` | `canon.drift-verdict/v1` |
| `PIN_WRITING_GATE_REGISTER` | `writing-gate-register` | `canon.writing-gate-register/v0` |
| `PIN_PERSONA_THESIS_PAYLOAD` | `persona-thesis-payload` | `canon.persona-thesis-payload/v0` |
| `PIN_RECONCILE_GATE_POLICY` | `reconcile-gate-policy` | `canon.reconcile-gate-policy/v1` |
| `PIN_RUN_WITNESS` | `run-witness` | `canon.run-witness/v1` |
| `PIN_TRANSPORT_SEAM` | `transport-seam` | `canon.transport-seam/v0` |
| `PIN_VAULT_FRONTEND` | `vault-frontend` | `canon.vault-frontend/v0` |
| `PIN_TEXTUTIL` | `textutil` | `canon.textutil/v0` |

`SEAM_PINS: frozenset[str]` is the closed vocabulary of admissible
short-names. A module-level assertion enforces
`SEAM_PINS.isdisjoint(_WAVE_ONE_NAMES)` at import time; a future contributor
adding a Wave 1 short-name (`atom`, `capsule`, `omission`, `transform-receipt`,
`readiness-probe`, `bootstrap-witness`, `adapter`) without a corresponding
decision to widen `SEAM_PINS` fails loud on import.

`PIN_REGISTRY: Mapping[str, SchemaPin]` is a `types.MappingProxyType` over
the underlying dict. A caller trying to mutate the registry raises
`TypeError` at the point of write. Test-side overrides use
`pin_registry_scope` (below), never mutation.

## The reader interface

Six public callables and one immutable registry view:

| callable | contract |
|---|---|
| `pin_for(name) -> SchemaPin` | lookup by short-name; refuses `UnknownPin` on any name outside `SEAM_PINS` |
| `all_pins() -> tuple[SchemaPin, ...]` | every pin, sorted by short-name, stable across calls (D-90) |
| `is_compatible(a, b) -> bool` | three-field byte equality on `name`, `version`, `kind_tag`; `MalformedPin` if either argument is not a `SchemaPin` |
| `describe(pin, *, as_json=False) -> str` | byte-stable human line, or a sorted-key JSON object; used by tooling and diagnostics |
| `pin_from_schema_field(value) -> SchemaPin` | reverse-lookup from a `kind_tag` string; `MalformedPin` on a shape violation, `UnknownPin` on a well-shaped tag no pin matches |
| `pin_registry_scope() -> Iterator[dict[str, SchemaPin]]` | context manager; snapshots both the pin registry and the migrator registry into fresh scratch dicts, restores prior state on exit including on exception |

`describe(pin)` returns `"{name} {version} ({kind_tag}) [{adr_ref}]"`.
`describe(pin, as_json=True)` returns `json.dumps({...}, sort_keys=True)` for
byte-stable diffs.

## The refusal hierarchy

Two independent roots, so a caller catches version failures and migration
failures under different sleeves (D-93).

| root | subclass | condition |
|---|---|---|
| `VersionError` | `UnknownPin` | short-name outside `SEAM_PINS`, or a `kind_tag` reverse-lookup with no match |
| `VersionError` | `IncompatiblePin` | `migrate` cross-pin without a registered migrator |
| `VersionError` | `MalformedPin` | `is_compatible` on a non-`SchemaPin` argument, or `pin_from_schema_field` on a shape violation |
| `MigrationError` | `MigratorConflict` | duplicate `(from, to)` registration |
| `MigrationError` | `MigratorRaised` | a migrator itself raised; the original hangs off `cause` and `__cause__`; a `MigrationError` subclass re-raises as-is |

Constructor errors on `SchemaPin` raise `ValueError` (a wiring fault). Every
other refusal is a subclass of one of the two hierarchies above. Neither root
inherits from the other; the two live on separate axes.

## The migration seam

The seam ships in `versions_migrate.py` and stays small:

| callable | contract |
|---|---|
| `register_migrator(from_pin, to_pin, fn)` | installs `fn` under `(from, to)`; refuses `ValueError` on non-`SchemaPin`; refuses `ValueError` on identity (`from_pin == to_pin`); refuses `MigratorConflict` on duplicate |
| `unregister_migrator(from_pin, to_pin)` | idempotent; refuses `ValueError` on non-`SchemaPin` |
| `migrate(rec, from_pin, to_pin) -> Record` | identity fast-path when `from_pin == to_pin` (returns `rec` unchanged, no lookup); refuses `IncompatiblePin` cross-pin without a registered migrator; wraps any migrator exception as `MigratorRaised(cause=original)` unless the migrator itself raised a `MigrationError` subclass (which re-raises as-is per D-95) |

`_MIGRATORS: dict[tuple[SchemaPin, SchemaPin], MigrationFn]` is the
module-level registry, empty at M4.3 close. A test
(`test_no_migrators_registered_at_m4_close`) pins the empty state, so a
future contributor cannot slip a migrator in without also removing the pin.

`MigrationFn` is a `typing.Protocol` with one call signature: `(Record) ->
Record`. Any callable of that shape is admissible; canon carries no
inheritance requirement.

## The `SCHEMA` alias (D-94)

`schema.SCHEMA = "canon.record/v1"` shipped in F0 and is read by
`frontmatter.py`, `vault.py`, and every fixture on disk. Moving the literal
into `versions.PIN_RECORD.kind_tag` without an alias would break every
downstream module and rewrite every fixture; keeping two independent literals
would let one drift while the other stayed put. The alias closes that fork:

```python
# at the bottom of schema.py
from canon.versions import PIN_RECORD  # noqa: E402

SCHEMA = PIN_RECORD.kind_tag
assert SCHEMA == "canon.record/v1", (
    f"PIN_RECORD.kind_tag drifted from the canon.record/v1 wire literal; "
    f"got {SCHEMA!r}")
```

The bottom-of-module late import keeps `schema.py`'s top surface unchanged
and avoids a cycle: `versions.py` imports nothing from `canon.schema`, so the
edge `schema → versions` is one-way. `test_schema_module_pins_to_pin_record`
pins the alias so a rewrite that unwires the import fails the suite. Every
downstream reader of `SCHEMA` reads the same bytes as
`pin_for("record").kind_tag`.

## The `pin_registry_scope` (D-96)

`pin_registry_scope` is a `contextlib.contextmanager` built on
`contextvars.ContextVar`. Two vars back the two registries:
`_REGISTRY_OVERRIDE` for pins, and (via a late import from
`versions_migrate`) `_MIGRATORS_OVERRIDE` for migrators. Entry snapshots
both dicts into fresh scratch copies and installs them under the vars; exit
resets both tokens, including on exception.

The scope yields the pin scratch dict, so the common pattern reads:

```python
with pin_registry_scope() as scratch:
    scratch["record"] = fake_pin
    register_migrator(PIN_RECORD, future, fn)
    # ... test ...
# both registries restored, in both exception and normal paths
```

The late import is deliberate. `pin_registry_scope` lives in `versions.py`
and needs the migrator var, but a module-level import of `versions_migrate`
into `versions.py` would create a cycle (versions_migrate → schema →
versions). The late import inside the context manager body binds the migrator
var only at scope entry, when both modules are fully loaded.

`contextvars` gives per-context isolation, not thread-safety. Two tasks in
the same context racing `register_migrator` still race; canon does not
promise thread-safety on the registry (also D-96).

## The M4.1 and M4.2 seam pins

`PIN_TRANSPORT_SEAM` and `PIN_VAULT_FRONTEND` ship at M4.3 close (D-98). M4.1
and M4.2 already committed their prose contracts referencing the seam names
in plain text; the pins land here so a caller doing `pin_for("transport-seam")`
or `pin_for("vault-frontend")` at M4 close gets a real answer, and no seam
that lands anywhere in M4 is left unnamed for a release cycle.

The `vault-identity-digest` pin is separate from `vault-note` (D-99). R2's
D-29 named the on-disk file by digesting the record's `(scope, id)` key. The
digest domain (the exact input bytes, the hash function, the truncation
length) is a separate concern from the note codec (the frontmatter shape, the
body layout, the trailer). A future rewrite of the file-naming scheme bumps
the digest pin without touching the note pin; a rewrite of the note codec
bumps the note pin without touching the digest pin.

## Containment

`versions.py` imports from the standard library only:
`contextlib`, `contextvars`, `dataclasses`, `re`, `types`,
`typing`. `versions_migrate.py` imports `contextvars`, `typing`, and
`canon.schema` (for `Record`) and `canon.versions` (for `SchemaPin` and the
version-error subclasses). `schema.py` imports `canon.versions` at
bottom-of-module for the `SCHEMA` alias. `__init__.py` re-exports every
public name from both modules.

No third-party version library is added. `packaging`, `semver`, `pep440`, and
their kin stay out; canon's semver-lite regex covers everything the sixteen
pins need, and a widening decision lands its own regex under its own
approval.

`test_versions_module_imports_only_stdlib` walks the module's imports and
asserts every top-level name is either a stdlib module or a canon-internal
module. A future contributor adding a third-party import trips the gate.

## Totality

Every reader raises exactly one thing on the paths documented above. `pin_for`
and `pin_from_schema_field` raise a `VersionError` subclass, never `KeyError`
or `AttributeError`. `is_compatible` raises `MalformedPin` on a non-pin
argument rather than returning `False`, because a caller wiring `False` back
into a policy would silently drop the wiring fault. `describe` never raises;
a pin is validated at construction, so no field can be `None` or malformed at
describe time.

The migration seam is total the same way. `migrate(rec, p, p)` returns `rec`
unchanged with no lookup. `migrate(rec, a, b)` with `a != b` either runs the
registered migrator, wraps its exception as `MigratorRaised`, or refuses
`IncompatiblePin`; no other path exists. `register_migrator` and
`unregister_migrator` refuse `ValueError` on non-`SchemaPin` arguments before
they touch the registry, so a hostile call cannot corrupt state.

The two refusal roots are stable across the M4 close. A caller who catches
`VersionError` handles every runtime version fault at once; a caller who
catches `MigrationError` handles every migration fault at once. A caller who
catches the parent `Exception` catches both plus construction faults
(`ValueError`).

## What stays out

Range comparisons, pre-release qualifiers, build metadata: none. The
semver-lite regex is exact-match at `v0` and `v1`. Wider policy lands under
D-90 with a real caller.

Transitive migrator resolution, migrator chaining, auto-derived migrators
from schema diffs: none. Every cross-pin migration is an explicit registered
migrator, one hop, or a refusal (D-95).

A public API for enumerating installed migrators: none. `_MIGRATORS` is
underscored; a test reads it, a runtime caller does not. A future band that
needs a public enumerator lands one under its own decision.

Concurrent-mutation safety on the registries: none. `pin_registry_scope`
gives per-context isolation via `contextvars`, not a lock (D-96).

Version negotiation over the transport seam: none. M4.1's transport seam
carries wire pin information as ordinary payload; a caller who wants to
negotiate reads the pin from a frame header and calls `is_compatible` on the
result. The negotiation policy is the caller's, not canon's.

Backward-migration or downgrade paths: none. A migrator maps forward from an
older pin to a newer pin. A caller who wants a downgrade registers a separate
migrator in the opposite direction; the registry keys on the ordered pair
`(from, to)`, so both directions cohabit without conflict.

A per-pin capability manifest (what fields a pin at `v0` carries versus what
`v1` requires): none. The manifest is the wire module's job (the frontmatter
codec knows what a `v0` note carries; the record envelope knows what a `v1`
record requires). Canon ships the pin as a name for the shape; the shape
itself lives in its own module.

`pathlib`, `pickle`, `typing_extensions`: none. `pathlib` is unused; canon
carries no path work in versions. `pickle` is unused; every pin serializes
via `describe(pin, as_json=True)` or the constant's Python identity. Canon
does not need any `typing_extensions` backport.
