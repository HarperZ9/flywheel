"""I2 completeness: a store this program adds carries its own export and
delete; a store that existed before either has them or names the gap, why it
is open, and the work package that closes it."""
import dataclasses
import re

import pytest

from harness import trace_inventory
from harness.trace_inventory import Gap

PACKAGE = re.compile(r"(FW-[0-9]{2}[a-z0-9]*|MN-0[1-3]|CA-0[1-3]|7\.[0-9]{1,2}|D[0-9]{1,2})\Z")


def test_every_registered_store_passes_the_completeness_rule():
    assert trace_inventory.completeness_errors(trace_inventory.stores()) == []


@pytest.mark.parametrize("op", ["inventory", "export", "delete"])
def test_every_operation_is_a_resolvable_callable_or_a_reasoned_gap(op):
    for store in trace_inventory.stores():
        value = getattr(store, op)
        if isinstance(value, Gap):
            assert value.reason.strip(), (store.id, op)
            assert PACKAGE.fullmatch(value.package), (store.id, op, value.package)
        else:
            assert callable(trace_inventory.resolve(value)), (store.id, op)


def test_program_added_stores_have_real_export_and_delete():
    added = [s for s in trace_inventory.stores() if s.added_by_program]
    assert added, "the custody ledger itself is a store this program adds"
    for store in added:
        assert not isinstance(store.export, Gap) and not isinstance(store.delete, Gap)


def test_the_rule_rejects_a_program_store_that_declares_a_gap():
    """False-success control: the checker must fail the entry it exists for."""
    base = next(s for s in trace_inventory.stores() if s.added_by_program)
    broken = dataclasses.replace(base, id="X1", delete=Gap("later", "FW-99"))
    unresolvable = dataclasses.replace(base, id="X2", export="harness.no_such.fn")
    no_package = dataclasses.replace(base, id="X3", added_by_program=False,
                                     delete=Gap("reason", ""))
    errors = trace_inventory.completeness_errors([broken, unresolvable, no_package])
    assert any("X1" in e for e in errors)
    assert any("X2" in e for e in errors)
    assert any("X3" in e for e in errors)


def test_every_declared_cap_names_its_behavior_and_the_test_that_covers_it():
    for store in trace_inventory.stores():
        for cap in store.caps:
            assert cap.what and cap.behavior and cap.test, store.id
