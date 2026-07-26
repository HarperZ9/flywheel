"""Two checkers, one predicate, different algorithms.

The bitset scan tests column pairs. The independent checker counts, for every
unordered pair of ROWS, how many columns cover both: a K_{2,2} exists iff some
row pair is covered twice. Same mathematics, transposed axis, different data
structure, different failure modes. An implementation bug in one is unlikely to
be mirrored in the other.

When they disagree the answer is UNDECIDED, never the majority side and never a
coin flip. A disagreement means we do not know, and saying so is the point of
having a fourth verdict at all.

The last section is the harder problem: two implementations of one SPEC share
SPEC-level exploits. Mutating the encoding grammar (a string where an int
belongs, a nested list, a float that happens to be integral) probes what both
checkers would accept, which agreement can never reveal.
"""
import json

import pytest

from harness.certificates.zarankiewicz import ZarankiewiczOracle, k22_free, encode
from harness.certificates.independent import (
    IndependentZarankiewiczOracle, k22_free_by_row_pairs, cross_check,
    AgreementError,
)
from harness.certificates.generators import zarankiewicz_instance
from harness.verdict import Verdict, UndecidedReason


def _cert(m, n, edges, claimed=None, s=2, t=2):
    return json.dumps({"m": m, "n": n, "s": s, "t": t,
                       "edges": [list(e) for e in edges],
                       "edge_count": len(edges) if claimed is None else claimed})


FANO_LINES = [(0, 1, 2), (0, 3, 4), (0, 5, 6), (1, 3, 5),
              (1, 4, 6), (2, 3, 6), (2, 4, 5)]
FANO_EDGES = [(p, li) for li, pts in enumerate(FANO_LINES) for p in pts]


# --- the independent predicate agrees with the original ----------------------

def test_both_predicates_agree_on_the_four_cycle():
    e = [(0, 0), (0, 1), (1, 0), (1, 1)]
    assert k22_free(2, 2, e) is False
    assert k22_free_by_row_pairs(2, 2, e) is False


def test_both_predicates_agree_on_the_fano_plane():
    assert k22_free(7, 7, FANO_EDGES) is True
    assert k22_free_by_row_pairs(7, 7, FANO_EDGES) is True


def test_both_predicates_agree_on_the_empty_graph():
    assert k22_free(4, 4, []) is True
    assert k22_free_by_row_pairs(4, 4, []) is True


def test_both_predicates_agree_on_a_star():
    e = [(0, j) for j in range(9)]
    assert k22_free(4, 9, e) is True
    assert k22_free_by_row_pairs(4, 9, e) is True


def test_the_two_predicates_agree_across_an_exhaustive_small_space():
    """Every subgraph of K_{3,3}: 512 graphs, both algorithms, no disagreement.
    Agreement over an enumerated space is the strongest evidence available that
    the reimplementation is genuinely equivalent rather than merely similar."""
    cells = [(r, c) for r in range(3) for c in range(3)]
    for mask in range(1 << 9):
        edges = [cells[i] for i in range(9) if mask & (1 << i)]
        assert k22_free(3, 3, edges) == k22_free_by_row_pairs(3, 3, edges), edges


def test_the_two_predicates_agree_on_generated_instances():
    for seed in range(25):
        inst = zarankiewicz_instance(seed=seed, difficulty=2)
        e = [tuple(x) for x in inst["seed_edges"]]
        assert (k22_free(inst["m"], inst["n"], e)
                == k22_free_by_row_pairs(inst["m"], inst["n"], e))


def test_the_independent_checker_uses_a_different_algorithm():
    # Not a style preference: a reimplementation that shares the original's data
    # structure shares its bugs. This asserts the row-pair map is what is built.
    import inspect
    from harness.certificates import independent
    src = inspect.getsource(independent.k22_free_by_row_pairs)
    assert "rows" in src or "row_pair" in src
    assert "bit_count" not in src            # the original's mechanism, not this one


# --- the oracle ---------------------------------------------------------------

def test_the_independent_oracle_reaches_the_same_verdicts():
    a, b = ZarankiewiczOracle(), IndependentZarankiewiczOracle()
    for cand in (_cert(7, 7, FANO_EDGES),
                 _cert(2, 2, [(0, 0), (0, 1), (1, 0), (1, 1)]),
                 _cert(4, 9, [(0, j) for j in range(9)])):
        assert a.verify(cand, None).verdict() == b.verify(cand, None).verdict()


def test_the_independent_oracle_also_catches_an_overclaimed_count():
    r = IndependentZarankiewiczOracle().verify(
        _cert(4, 9, [(0, 0)], claimed=99), None)
    assert r.verdict() == "FAIL"


def test_the_independent_oracle_never_executes_candidate_code():
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "harness" / "certificates" / "independent.py")
    tree = ast.parse(src.read_text(encoding="utf-8"))
    banned = {"subprocess", "socket", "ctypes", "pickle", "importlib", "os"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        elif isinstance(node, ast.Name) and node.id in ("eval", "exec", "compile"):
            found.add(node.id)
    assert not (found & (banned | {"eval", "exec", "compile"})), found


# --- cross_check: disagreement is UNDECIDED ----------------------------------

def test_agreement_on_pass_yields_pass():
    r = cross_check(ZarankiewiczOracle(), IndependentZarankiewiczOracle(),
                    _cert(7, 7, FANO_EDGES), None)
    assert r.verdict() == "PASS"


def test_agreement_on_fail_yields_fail():
    r = cross_check(ZarankiewiczOracle(), IndependentZarankiewiczOracle(),
                    _cert(2, 2, [(0, 0), (0, 1), (1, 0), (1, 1)]), None)
    assert r.verdict() == "FAIL"


def test_disagreement_yields_undecided_and_names_the_reason():
    class _Liar(IndependentZarankiewiczOracle):
        def check(self, cert):
            valid, why, cov = super().check(cert)
            return (not valid), "deliberately inverted", cov

    r = cross_check(ZarankiewiczOracle(), _Liar(), _cert(7, 7, FANO_EDGES), None)
    assert r.verdict() == "UNDECIDED"
    assert r.undecided_reason == UndecidedReason.HELD_OUT_DISAGREEMENT.value


def test_disagreement_never_picks_a_side_even_when_one_is_right():
    class _Liar(IndependentZarankiewiczOracle):
        def check(self, cert):
            valid, why, cov = super().check(cert)
            return (not valid), "deliberately inverted", cov

    r = cross_check(ZarankiewiczOracle(), _Liar(), _cert(7, 7, FANO_EDGES), None)
    assert r.verdict() not in ("PASS", "FAIL")


def test_disagreement_records_both_verdicts_so_it_can_be_investigated():
    class _Liar(IndependentZarankiewiczOracle):
        def check(self, cert):
            valid, why, cov = super().check(cert)
            return (not valid), "deliberately inverted", cov

    r = cross_check(ZarankiewiczOracle(), _Liar(), _cert(7, 7, FANO_EDGES), None)
    assert "PASS" in r.stdout_excerpt and "FAIL" in r.stdout_excerpt


def test_an_undecided_cross_check_says_it_does_not_prove_the_predicate():
    class _Liar(IndependentZarankiewiczOracle):
        def check(self, cert):
            valid, why, cov = super().check(cert)
            return (not valid), "inverted", cov

    r = cross_check(ZarankiewiczOracle(), _Liar(), _cert(7, 7, FANO_EDGES), None)
    assert "NOT_PROVES_PREDICATE" in r.does_not_prove


def test_an_unverifiable_from_either_side_propagates_as_unverifiable():
    r = cross_check(ZarankiewiczOracle(), IndependentZarankiewiczOracle(),
                    _cert(4, 4, [(0, 0)], s=3, t=3), None)
    assert r.verdict() == "UNVERIFIABLE"


def test_cross_checking_an_oracle_against_itself_is_refused():
    # Two copies of one implementation is not independence, and accepting it
    # would let a caller manufacture the appearance of a held-out check.
    o = ZarankiewiczOracle()
    with pytest.raises(AgreementError):
        cross_check(o, o, _cert(7, 7, FANO_EDGES), None)


def test_cross_checking_two_instances_of_the_same_class_is_refused():
    with pytest.raises(AgreementError):
        cross_check(ZarankiewiczOracle(), ZarankiewiczOracle(),
                    _cert(7, 7, FANO_EDGES), None)


# --- spec-level mutation: what BOTH would accept ------------------------------

SPEC_MUTANTS = [
    ("string_dimension", '{"m":"4","n":9,"s":2,"t":2,"edges":[[0,0]],"edge_count":1}'),
    ("float_dimension", '{"m":4.0,"n":9,"s":2,"t":2,"edges":[[0,0]],"edge_count":1}'),
    ("string_edge_index", '{"m":4,"n":9,"s":2,"t":2,"edges":[["0",0]],"edge_count":1}'),
    ("float_edge_index", '{"m":4,"n":9,"s":2,"t":2,"edges":[[0.0,0]],"edge_count":1}'),
    ("bool_edge_index", '{"m":4,"n":9,"s":2,"t":2,"edges":[[true,0]],"edge_count":1}'),
    ("nested_edge", '{"m":4,"n":9,"s":2,"t":2,"edges":[[[0],0]],"edge_count":1}'),
    ("triple_edge", '{"m":4,"n":9,"s":2,"t":2,"edges":[[0,0,0]],"edge_count":1}'),
    ("string_count", '{"m":4,"n":9,"s":2,"t":2,"edges":[[0,0]],"edge_count":"1"}'),
    ("null_edges", '{"m":4,"n":9,"s":2,"t":2,"edges":null,"edge_count":0}'),
    ("edges_as_object", '{"m":4,"n":9,"s":2,"t":2,"edges":{"0":0},"edge_count":1}'),
]


@pytest.mark.parametrize("name,mutant", SPEC_MUTANTS)
def test_no_spec_mutant_is_accepted_by_either_checker(name, mutant):
    """A spec-level exploit is one BOTH checkers accept, so agreement cannot
    reveal it. Every mutant here must be refused, and refused the same way."""
    a = ZarankiewiczOracle().verify(mutant, None)
    b = IndependentZarankiewiczOracle().verify(mutant, None)
    assert a.verdict() != "PASS", f"{name} accepted by the bitset checker"
    assert b.verdict() != "PASS", f"{name} accepted by the row-pair checker"
    assert a.verdict() == b.verdict(), (
        f"{name}: checkers disagree on a malformed certificate, "
        f"{a.verdict()} vs {b.verdict()}")


def test_a_bool_index_is_not_silently_read_as_an_integer():
    # In Python True == 1, so a bool index would sail through a naive isinstance
    # check and silently become row 1. This is the mutant most likely to pass.
    mutant = '{"m":4,"n":9,"s":2,"t":2,"edges":[[true,0]],"edge_count":1}'
    assert ZarankiewiczOracle().verify(mutant, None).verdict() == "FAIL"
