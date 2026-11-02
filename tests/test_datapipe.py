"""Datapipe regressions: each test holds a failure the first study runs actually hit."""
import dataclasses

from harness.datapipe import clean
from harness.datapipe.access import SourceRecord
from harness.datapipe.diffuse import decide
from harness.datapipe.schema import Column as C, Table


def _table(cols, rows):
    return Table("t", "s", cols, rows, "f", "0", "unknown", "unknown")


def test_copy_keeps_declared_identities():
    t = _table([C("A", "num"), C("B", "num")], [["1", "2"]])
    t.identities = [("A = B", lambda g: g("A") - g("B"), 0.5)]
    assert len(clean.check_identity(t.copy())) == 1


def test_identity_flags_only_rows_that_break_it():
    rows = [[str(i), str(i)] for i in range(5)] + [["9", "3"]]
    t = _table([C("A", "num"), C("B", "num")], rows)
    t.identities = [("A = B", lambda g: g("A") - g("B"), 0.5)]
    assert [f.row for f in clean.check_identity(t)] == [5]


def test_sorted_integer_column_is_not_stuck():
    rows = [[str(z), f"{i}.5"] for i, z in enumerate(sorted(list(range(30)) * 6))]
    t = _table([C("Z", "num"), C("x", "num")], rows)
    assert clean.check_runs(t) == []


def test_stuck_decimal_value_is_flagged():
    rows = [[f"{i}.25"] for i in range(40)]
    rows[10:16] = [["7.75"]] * 6
    flags = clean.check_runs(_table([C("x", "num")], rows))
    assert sorted({f.row for f in flags}) == list(range(10, 16))


def test_offset_rule_needs_a_temperature_column():
    vals = [str(20 + (i % 5) * 0.2) for i in range(60)] + ["293.15"]
    rows = [[v] for v in vals]
    offset = lambda dim: [f for f in clean.check_unit_factor(_table([C("x", "num", "1", "q", dim)], rows)) if "273.15" in str(f)]
    assert offset("temperature")
    assert not offset("energy")


def test_unread_terms_block_export(tmp_path):
    rec = SourceRecord("x", "t", "https://example.org", "direct", "2026-10-31")
    ok, why = decide(rec, tmp_path)
    assert not ok and why
    assert dataclasses.asdict(rec)["source_id"] == "x"
