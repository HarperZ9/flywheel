"""Falsifiers for the answer as a Lean file, and for the relations it states.

The property that makes this artifact worth anything is the division: what the
kernel settles is a theorem, what an outside source decided is an axiom, and
`#print axioms confirmed` lists the second set by name. Anything that quietly
moved a fact across that line would produce a file that looks proved and is
not, so the tests here are mostly about the line.

The other half is arithmetic. A relation is parsed, never evaluated, and a
relation this module will not read is refused rather than approximated.
"""
import pytest

from harness.contract_terms import CITED, RECOMPUTE, TABLE
from harness.proof_lean import SUFFIXES, identifier, lean_source, scale_of
from harness.proof_relations import (MAX_SCALE, RelationError, claims,
                                     fixed_point, places)
from harness.verdict import Verdict

ANSWER = {"taxable_income": {"value": 36700, "source": "the return"},
          "tax": {"value": 4169, "source": "irs-2025-tax-table-single",
                  "method": "table"}}
ROWS = [
    {"field": "taxable_income", "authority": CITED, "source": "the return",
     "verdict": Verdict.PASS.value, "code": "AGREES", "reason": "",
     "criticality": "standard"},
    {"field": "tax", "authority": TABLE, "source": "irs-2025-tax-table-single",
     "verdict": Verdict.PASS.value, "code": "AGREES", "reason": "",
     "criticality": "critical"},
]
REPORT = {"verdict": Verdict.PASS.value, "release": "RELEASE", "blocking": [],
          "checked": 2, "passed": 2, "fields": ROWS}
CONTRACT = [{"name": "tax", "authority": TABLE, "method": "table",
             "source": "irs-2025-tax-table-single"}]


def source(**kwargs) -> str:
    return lean_source(REPORT, kwargs.pop("answer", ANSWER),
                       kwargs.pop("contract", None), **kwargs)


# --- the line between what is proved and what is assumed --------------------

def test_a_value_an_outside_source_decided_is_an_axiom_not_a_theorem():
    """The check ran in a subprocess. Calling that a theorem would put a
    kernel's name on a subprocess's word."""
    body = source()
    assert "axiom tax_decided : Decided" in body
    assert "theorem tax_decided" not in body


def test_a_cited_field_produces_no_axiom_because_nothing_decided_it():
    assert "taxable_income_decided" not in source()


def test_a_field_the_check_did_not_confirm_produces_no_axiom():
    rows = [dict(ROWS[1], verdict=Verdict.FAIL.value)]
    body = lean_source(dict(REPORT, fields=rows), ANSWER)
    assert "tax_decided" not in body
    assert "unconfirmed : List String := [" + chr(34) + "tax" in body


def test_a_recompute_authority_is_assumed_the_same_way_a_table_is():
    rows = [dict(ROWS[1], authority=RECOMPUTE)]
    assert "axiom tax_decided" in lean_source(dict(REPORT, fields=rows), ANSWER)


def test_the_file_prints_its_own_axioms():
    assert "#print axioms confirmed" in source()


def test_every_obligation_is_conjoined_into_one_name():
    """One `#print axioms` has to cover the whole surface. An obligation left
    out of `confirmed` would rest on an axiom nothing reports."""
    body = source(contract=CONTRACT, relations=["0 <= tax"])
    tail = body.split("theorem confirmed :")[1]
    for name in ("tax_decided", "tax_method_as_required", "relation_1"):
        assert name in tail


def test_an_answer_with_nothing_to_prove_says_so_rather_than_proving_nothing():
    empty = lean_source({"verdict": Verdict.PASS.value, "release": "RELEASE",
                         "blocking": [], "checked": 0, "passed": 0,
                         "fields": []}, {})
    assert "theorem confirmed : True := trivial" in empty
    assert "axiom Decided" not in empty


# --- the contract's mandates ------------------------------------------------

def test_a_required_method_becomes_an_obligation_the_kernel_settles():
    body = source(contract=CONTRACT)
    assert "theorem tax_method_as_required" in body
    assert "by decide" in body


def test_a_contract_field_absent_from_the_answer_states_no_obligation():
    contract = [{"name": "missing", "authority": CITED, "source": "nowhere"}]
    assert "missing" not in source(contract=contract)


# --- names ------------------------------------------------------------------

def test_a_field_named_like_a_derived_name_does_not_collide_with_it():
    """A contract holding both `tax` and `tax_source` would otherwise emit two
    declarations called `tax_source` and the file would not parse."""
    taken = set()
    first = identifier("tax_source", taken)
    second = identifier("tax", taken)
    assert first == "tax_source"
    assert second != first
    assert first not in {second + suffix for suffix in SUFFIXES}


def test_a_lean_keyword_is_not_used_as_a_declaration_name():
    assert identifier("end", set()) != "end"


def test_a_field_named_after_a_generated_name_is_moved_aside():
    for name in ("Decided", "confirmed", "unconfirmed", "relation_1"):
        assert identifier(name, set()) != name


def test_a_field_name_that_is_not_an_identifier_is_still_declarable():
    assert identifier("2nd payment", set()) == "f_2nd_payment"


def test_a_quote_in_a_source_name_is_escaped_not_dropped():
    answer = {"tax": {"value": 1, "source": 'a "quoted" source'}}
    body = lean_source(REPORT, answer)
    assert chr(92) + chr(34) + "quoted" in body


# --- the fixed-point scale --------------------------------------------------

def test_one_scale_covers_the_whole_file_so_no_sum_mixes_units():
    assert scale_of({"a": {"value": 1}, "b": {"value": 2.25}}) == 2


def test_a_value_too_wide_for_the_scale_does_not_drag_every_other_value_into_it():
    """A float's rounding tail would otherwise set the scale for the file, and
    a plain 12 would be carried as 12000000000 to make room for a value that
    gets dropped anyway."""
    assert scale_of({"a": {"value": 12}, "b": {"value": 0.1 + 0.2}}) == 0


def test_a_value_the_scale_cannot_hold_is_dropped_and_named_not_rounded():
    """A rounded number in a proof is a proof about a number nobody stated."""
    answer = {"tax": {"value": 4169}, "odd": {"value": 0.1 + 0.2}}
    body = lean_source(REPORT, answer)
    assert "unrepresentable : List String := [" + chr(34) + "odd" in body
    assert "def odd :" not in body


def test_fixed_point_refuses_rather_than_rounding():
    assert fixed_point(0.1 + 0.2, MAX_SCALE) is None
    assert fixed_point(4165.50, 2) == "416550"
    assert fixed_point(-4165.50, 2) == "(-416550)"


def test_a_value_that_is_not_a_finite_decimal_never_reaches_a_scale():
    assert places(float("nan")) > MAX_SCALE
    assert places(float("inf")) > MAX_SCALE


# --- relations --------------------------------------------------------------

def test_the_spelling_a_person_writes_is_the_one_that_parses():
    """`total = subtotal + tax` is what a contract author writes. Python reads
    a single `=` as an assignment, which would refuse the documented syntax."""
    assert claims("total = a + b", {"total": "total", "a": "a", "b": "b"}, 0) == \
        ["total = (a + b)"]


def test_a_chain_becomes_one_claim_per_link_so_a_failure_names_the_link():
    assert claims("0 <= tax <= income", {"tax": "tax", "income": "income"}, 0) == \
        ["0 ≤ tax", "tax ≤ income"]


def test_a_bare_literal_is_scaled_with_everything_else():
    assert claims("tax <= 5", {"tax": "tax"}, 2) == ["tax ≤ 500"]


def test_a_factor_is_not_scaled_because_doubling_does_not_double_the_units():
    assert claims("fee <= 2 * base", {"fee": "fee", "base": "base"}, 2) == \
        ["fee ≤ (2 * base)"]


@pytest.mark.parametrize("relation, why", [
    ("nowhere > 0", "names a field the answer does not have"),
    ("tax * tax > 0", "would square the scale"),
    ("tax ** 2 > 0", "is an operator this module does not read"),
    ("tax", "states no comparison"),
    ("open('x') > 0", "is a call"),
])
def test_a_relation_this_module_will_not_read_is_refused(relation, why):
    with pytest.raises(RelationError):
        claims(relation, {"tax": "tax"}, 0)


def test_a_relation_naming_a_dropped_field_is_refused_not_silently_skipped():
    """The field is reachable by every other part of the check. A relation
    about it cannot be proved here, and saying nothing would read as proved."""
    answer = {"tax": {"value": 1}, "odd": {"value": 0.1 + 0.2}}
    with pytest.raises(RelationError):
        lean_source(REPORT, answer, relations=["odd >= 0"])


# --- the artifact -----------------------------------------------------------

def test_the_same_answer_emits_the_same_bytes():
    """A proof file that differs run to run cannot be hashed into a receipt."""
    assert source(contract=CONTRACT, relations=["0 <= tax"]) == \
        source(contract=CONTRACT, relations=["0 <= tax"])


def test_the_answer_digest_is_in_the_header():
    assert "sha256:" in source()


def test_the_file_never_carries_an_authoritative_value():
    """Every `def` is what the answer states. The table's own number is not in
    the report and must not arrive here either."""
    assert "4165" not in source()
