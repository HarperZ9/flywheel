"""The benchmark defect gate: 398 certified-defective statements were
found across five published Lean benchmarks (lean-invention dossier,
2026-07-14). This gate catches the two mechanical defect classes before
a statement enters any lane here: `sorry` (an admitted hole wearing a
theorem's name) and nonstandard axioms (acceptance smuggled in through
an assumed falsehood). Clean statements pass; every flag names its
statement and its reason."""

from harness.benchmark_hygiene import screen_statements

CLEAN = "theorem t1 (n m : Nat) : n + m = m + n := by omega"
SORRY = "theorem t2 (n : Nat) : n + 0 = n := by sorry"
AXIOM = "axiom bad : 1 = 2\ntheorem t3 : 1 = 2 := bad"


def test_clean_statements_pass():
    r = screen_statements([CLEAN])
    assert r["schema"] == "flywheel.benchmark-hygiene/v1"
    assert r["flagged"] == [] and r["clean"] == 1


def test_sorry_is_flagged_with_its_statement():
    r = screen_statements([CLEAN, SORRY])
    assert r["clean"] == 1
    f = r["flagged"][0]
    assert f["index"] == 1 and f["defect"] == "sorry"
    assert "t2" in f["statement"]


def test_nonstandard_axiom_is_flagged():
    r = screen_statements([AXIOM])
    assert r["flagged"][0]["defect"] == "axiom"


def test_sorry_inside_a_name_or_comment_is_not_a_hole():
    named = "theorem sorry_free (n : Nat) : n = n := rfl"
    commented = "-- this used to say sorry\ntheorem t (n : Nat) : n = n := rfl"
    r = screen_statements([named, commented])
    assert r["flagged"] == [], r["flagged"]


def test_summary_counts_are_consistent():
    r = screen_statements([CLEAN, SORRY, AXIOM])
    assert r["total"] == 3
    assert r["clean"] + len(r["flagged"]) == r["total"]
