import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from check_file_gate import (  # noqa: E402
    BURNDOWNS, LIMIT, TREES, load_all, load_grandfathered, over_gate)

ROOT = Path(__file__).resolve().parent.parent


def test_over_gate_finds_a_long_file(tmp_path):
    (tmp_path / "long.py").write_text("x = 1\n" * 400, encoding="utf-8")
    (tmp_path / "short.py").write_text("x = 1\n", encoding="utf-8")
    found = dict(over_gate(tmp_path, limit=300))
    assert "long.py" in found
    assert found["long.py"] == 400
    assert "short.py" not in found


def test_over_gate_ignores_bytecode_caches(tmp_path):
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "junk.py").write_text("x = 1\n" * 500, encoding="utf-8")
    assert over_gate(tmp_path, limit=300) == []


def test_grandfather_list_parses(tmp_path):
    p = tmp_path / "burndown.md"
    p.write_text(
        "# burn-down\n\n"
        "| file | lines |\n"
        "|---|---|\n"
        "| harness/gateway.py | 2391 |\n"
        "| harness/serve.py | 420 |\n",
        encoding="utf-8")
    g = load_grandfathered(p)
    assert g["harness/gateway.py"] == 2391
    assert g["harness/serve.py"] == 420


def test_missing_burndown_is_an_empty_list_not_a_crash(tmp_path):
    assert load_grandfathered(tmp_path / "nope.md") == {}


# The two invariants, over EVERY gated tree rather than harness alone. The gate
# only ever scanned harness/, so scripts/ and tests/ had accumulated 46
# violations with the standard unenforced. Parametrizing over TREES is what keeps
# a third tree from being silently exempt the way those two were.


@pytest.mark.parametrize("tree", TREES)
def test_the_real_repo_has_a_burndown_covering_every_current_violation(tree):
    listed = load_all(ROOT / b for b in BURNDOWNS)
    actual = dict(over_gate(ROOT / tree, limit=LIMIT))
    unlisted = [f for f in actual if f"{tree}/{f}" not in listed]
    assert unlisted == [], f"unlisted {tree}/ violations: {unlisted}"


@pytest.mark.parametrize("tree", TREES)
def test_no_grandfathered_file_has_grown_past_its_frozen_size(tree):
    listed = load_all(ROOT / b for b in BURNDOWNS)
    actual = dict(over_gate(ROOT / tree, limit=LIMIT))
    grown = {f: (n, listed[f"{tree}/{f}"]) for f, n in actual.items()
             if f"{tree}/{f}" in listed and n > listed[f"{tree}/{f}"]}
    assert grown == {}, f"grew past frozen size in {tree}/: {grown}"


def test_load_all_merges_records_and_lower_ceiling_wins():
    """Two records must merge into one dict. If they ever named the same file,
    the gate must take the LOWER frozen size, never silently raise a ceiling."""
    a = ROOT / "scripts" / "_ga.md"
    b = ROOT / "scripts" / "_gb.md"
    try:
        a.write_text("| f | l |\n|---|---|\n| harness/x.py | 500 |\n",
                     encoding="utf-8")
        b.write_text("| f | l |\n|---|---|\n| harness/x.py | 400 |\n"
                     "| tests/y.py | 320 |\n", encoding="utf-8")
        merged = load_all([a, b])
        assert merged["harness/x.py"] == 400, "the higher ceiling must not win"
        assert merged["tests/y.py"] == 320
    finally:
        a.unlink(missing_ok=True)
        b.unlink(missing_ok=True)


@pytest.mark.parametrize("tree", ["scripts", "tests"])
def test_the_gate_bites_on_a_new_oversized_file_end_to_end(tree):
    """Run the REAL main() against a real oversized file dropped into a gated
    tree. A dict-membership check would prove nothing; this exercises the actual
    classification path and must return failure (1)."""
    import check_file_gate

    victim = ROOT / tree / f"_gate_bite_probe_{tree}.py"
    victim.write_text("x = 1\n" * (LIMIT + 50), encoding="utf-8")
    try:
        rc = check_file_gate.main()
    finally:
        victim.unlink(missing_ok=True)
    assert rc == 1, f"the gate did not fail on a new oversized {tree}/ file"
    # And with the probe removed, the real repo is clean again.
    assert check_file_gate.main() == 0


def test_the_scripts_tests_record_exists_and_is_populated():
    """Deleting the record would silently un-gate 46 files while the gate still
    reported clean. The record's existence is itself part of the invariant."""
    rec = ROOT / "project-docs" / "records" / \
        "2026-07-26-file-gate-burndown-scripts-tests.md"
    assert rec.is_file(), "the scripts/tests burn-down record is missing"
    listed = load_grandfathered(rec)
    assert any(k.startswith("scripts/") for k in listed)
    assert any(k.startswith("tests/") for k in listed)


def test_the_gate_scans_scripts_and_tests_not_only_harness():
    """The regression this whole change fixes: TREES must include the two trees
    that were unenforced, or the extension is cosmetic."""
    assert "scripts" in TREES and "tests" in TREES and "harness" in TREES


def test_every_file_created_in_phase_0_is_under_the_gate():
    # The new modules must not need grandfathering. If one does, split it.
    root = Path(__file__).resolve().parent.parent
    new = ["verdict.py", "advantages.py", "gateway_auth.py", "gate.py"]
    over = dict(over_gate(root / "harness", limit=300))
    assert [f for f in new if f in over] == []
