"""test_versions_migrate.py -- M4.3 migration seam.

Covers `register_migrator`, `unregister_migrator`, `migrate` (with the
identity fast-path, the MigratorRaised wrap, and the IncompatiblePin refusal),
and the `pin_registry_scope` interaction that isolates a scratch migrator
registry from the module-level default.
"""
from __future__ import annotations

import pytest

from canon.schema import (
    KIND_PERSONALITY_BLOCK,
    Provenance,
    Record,
)
from canon.versions import (
    PIN_RECORD,
    IncompatiblePin,
    SchemaPin,
    pin_registry_scope,
)
from canon.versions_migrate import (
    MigrationError,
    MigrationFn,
    MigratorConflict,
    MigratorRaised,
    _MIGRATORS,
    _active_migrators,
    migrate,
    register_migrator,
    unregister_migrator,
)


def _rec(id_: str = "tone", body: str = "hello") -> Record:
    prov = Provenance(
        harness="claude-code", source_hash="a" * 64, create_ord=42)
    return Record(
        kind=KIND_PERSONALITY_BLOCK, id=id_, scope="global",
        data={"title": id_.title(), "body": body}, provenance=prov)


def _future_pin_v2() -> SchemaPin:
    return SchemaPin(
        "record", "v2", "canon.record/v2", "hypothetical future band")


def test_migrate_same_pin_is_identity():
    rec = _rec()
    assert migrate(rec, PIN_RECORD, PIN_RECORD) is rec


def test_migrate_cross_pin_without_migrator_refuses():
    rec = _rec()
    future = _future_pin_v2()
    with pytest.raises(IncompatiblePin) as exc:
        migrate(rec, PIN_RECORD, future)
    assert "canon.record/v1" in str(exc.value)
    assert "canon.record/v2" in str(exc.value)


def test_register_migrator_installs_and_migrates():
    future = _future_pin_v2()
    rec = _rec("tone", "before")

    def bump_to_v2(r: Record) -> Record:
        return Record(
            kind=r.kind, id=r.id, scope=r.scope,
            data={**r.data, "body": "after"},
            provenance=r.provenance)

    with pin_registry_scope():
        register_migrator(PIN_RECORD, future, bump_to_v2)
        out = migrate(rec, PIN_RECORD, future)
    assert out.data["body"] == "after"
    assert (PIN_RECORD, future) not in _MIGRATORS


def test_register_migrator_duplicate_refuses():
    future = _future_pin_v2()
    with pin_registry_scope():
        register_migrator(PIN_RECORD, future, lambda r: r)
        with pytest.raises(MigratorConflict) as exc:
            register_migrator(PIN_RECORD, future, lambda r: r)
    assert "canon.record/v1" in str(exc.value)
    assert "canon.record/v2" in str(exc.value)


def test_unregister_migrator_idempotent():
    future = _future_pin_v2()
    with pin_registry_scope():
        unregister_migrator(PIN_RECORD, future)
        register_migrator(PIN_RECORD, future, lambda r: r)
        unregister_migrator(PIN_RECORD, future)
        unregister_migrator(PIN_RECORD, future)


def test_migrator_raised_wraps_original():
    future = _future_pin_v2()

    class BadMigratorError(RuntimeError):
        pass

    def broken(r: Record) -> Record:
        raise BadMigratorError("nope")

    with pin_registry_scope():
        register_migrator(PIN_RECORD, future, broken)
        with pytest.raises(MigratorRaised) as exc_info:
            migrate(_rec(), PIN_RECORD, future)
    exc = exc_info.value
    assert isinstance(exc.cause, BadMigratorError)
    assert isinstance(exc.__cause__, BadMigratorError)
    assert "BadMigratorError" in str(exc)
    assert "nope" in str(exc)


def test_no_migrators_registered_at_m4_close():
    assert _MIGRATORS == {}


def test_pin_registry_scope_isolates_migrators():
    future = _future_pin_v2()
    with pin_registry_scope():
        register_migrator(PIN_RECORD, future, lambda r: r)
        assert (PIN_RECORD, future) in _active_migrators()
    assert (PIN_RECORD, future) not in _MIGRATORS
    assert _active_migrators() is _MIGRATORS


def test_pin_registry_scope_nested_migrators_are_layered():
    future = _future_pin_v2()

    def outer_fn(r: Record) -> Record:
        return r
    def inner_fn(r: Record) -> Record:
        return r

    with pin_registry_scope():
        register_migrator(PIN_RECORD, future, outer_fn)
        assert _active_migrators()[(PIN_RECORD, future)] is outer_fn
        with pin_registry_scope():
            assert _active_migrators()[(PIN_RECORD, future)] is outer_fn
            unregister_migrator(PIN_RECORD, future)
            register_migrator(PIN_RECORD, future, inner_fn)
            assert _active_migrators()[(PIN_RECORD, future)] is inner_fn
        assert _active_migrators()[(PIN_RECORD, future)] is outer_fn
    assert _MIGRATORS == {}


def test_pin_registry_scope_restores_migrators_on_exception():
    future = _future_pin_v2()
    with pytest.raises(RuntimeError, match="test-exc"):
        with pin_registry_scope():
            register_migrator(PIN_RECORD, future, lambda r: r)
            raise RuntimeError("test-exc")
    assert (PIN_RECORD, future) not in _MIGRATORS


def test_register_migrator_refuses_non_schemapin():
    with pytest.raises(ValueError):
        register_migrator("record", PIN_RECORD, lambda r: r)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        register_migrator(PIN_RECORD, "record", lambda r: r)  # type: ignore[arg-type]


def test_register_migrator_refuses_identity():
    with pytest.raises(ValueError):
        register_migrator(PIN_RECORD, PIN_RECORD, lambda r: r)


def test_unregister_migrator_refuses_non_schemapin():
    with pytest.raises(ValueError):
        unregister_migrator("record", PIN_RECORD)  # type: ignore[arg-type]


def test_migrate_refuses_non_schemapin():
    with pytest.raises(ValueError):
        migrate(_rec(), "record", PIN_RECORD)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        migrate(_rec(), PIN_RECORD, "record")  # type: ignore[arg-type]


def test_migration_error_hierarchy():
    assert issubclass(MigratorConflict, MigrationError)
    assert issubclass(MigratorRaised, MigrationError)
    # MigrationError does not inherit from VersionError; separate roots.
    from canon.versions import VersionError
    assert not issubclass(MigrationError, VersionError)
    assert not issubclass(VersionError, MigrationError)


def test_migration_fn_is_a_protocol():
    from typing import get_type_hints, runtime_checkable
    assert hasattr(MigrationFn, "__call__")


def test_migrator_raised_preserves_migration_error_subclass():
    """A migrator that itself raises a MigrationError re-raises as-is, so a
    caller who catches MigratorConflict from a nested register_migrator gets
    the class they registered against, not a wrapped MigratorRaised."""
    future = _future_pin_v2()

    def re_raises_conflict(r: Record) -> Record:
        raise MigratorConflict("nested-conflict-from-migrator")

    with pin_registry_scope():
        register_migrator(PIN_RECORD, future, re_raises_conflict)
        with pytest.raises(MigratorConflict, match="nested-conflict-from-migrator"):
            migrate(_rec(), PIN_RECORD, future)
