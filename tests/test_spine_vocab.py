"""The spine's one verdict vocabulary, and the four older sets mapped onto it.

The map is lossy on purpose, so each test pins a direction a reader would get
wrong if the table drifted: an abstain must never read as a pass, a refusal
must never read as an inability to check.
"""
import pytest

from harness.spine.vocab import (FLYWHEEL, GATE, INTEGRITY, ORGAN_BUNDLE,
                                 VOCABULARIES, VocabularyError, fold,
                                 mapping_rows, to_spine)
from harness.verdict import Verdict


def test_the_spine_reuses_flywheels_enum_rather_than_adding_a_fifth():
    assert set(VOCABULARIES[FLYWHEEL].values()) == set(Verdict)
    for term, verdict in VOCABULARIES[FLYWHEEL].items():
        assert verdict is Verdict(term)


@pytest.mark.parametrize("vocabulary,term,expected", [
    (INTEGRITY, "MATCH", Verdict.PASS),
    (INTEGRITY, "DRIFT", Verdict.FAIL),
    (INTEGRITY, "UNVERIFIABLE", Verdict.UNVERIFIABLE),
    (INTEGRITY, "RECEIPT_TAMPERED", Verdict.FAIL),
    (ORGAN_BUNDLE, "warn", Verdict.UNDECIDED),
    (ORGAN_BUNDLE, "needs-human", Verdict.UNDECIDED),
    (ORGAN_BUNDLE, "not-applicable", Verdict.UNVERIFIABLE),
    (ORGAN_BUNDLE, "unknown", Verdict.UNVERIFIABLE),
    (GATE, "allow", Verdict.PASS),
    (GATE, "deny", Verdict.FAIL),
    (GATE, "needs-human", Verdict.UNDECIDED),
])
def test_each_source_term_maps_to_one_spine_verdict(vocabulary, term, expected):
    assert to_spine(vocabulary, term) is expected


def test_only_a_decided_favourable_term_maps_to_pass():
    passing = {(v, t) for v, t, s in mapping_rows() if s == "PASS"}
    assert passing == {(FLYWHEEL, "PASS"), (INTEGRITY, "MATCH"),
                       (INTEGRITY, "RECEIPT_VALID"), (ORGAN_BUNDLE, "pass"),
                       (GATE, "allow")}


def test_every_organ_bundle_status_in_use_has_a_mapping():
    # The set lesson_interop.py and crucible/gather interop.py validate against.
    from harness.lesson_interop import STATUSES
    assert STATUSES == set(VOCABULARIES[ORGAN_BUNDLE])


@pytest.mark.parametrize("vocabulary,term", [
    ("integrity", "TRUSTED"), ("gate", "maybe"), ("organ-bundle", "PASS"),
    ("nonexistent", "PASS")])
def test_an_unknown_term_or_vocabulary_raises_instead_of_guessing(vocabulary, term):
    with pytest.raises(VocabularyError):
        to_spine(vocabulary, term)


def test_fold_lets_a_confirmed_failure_outrank_an_inability_to_check():
    assert fold([Verdict.PASS, Verdict.UNVERIFIABLE, Verdict.FAIL]) is Verdict.FAIL
    assert fold([Verdict.PASS, Verdict.UNDECIDED, Verdict.UNVERIFIABLE]) is Verdict.UNVERIFIABLE
    assert fold([Verdict.PASS, Verdict.UNDECIDED]) is Verdict.UNDECIDED
    assert fold([Verdict.PASS, Verdict.PASS]) is Verdict.PASS


def test_an_empty_fold_is_unverifiable_and_never_a_pass():
    assert fold([]) is Verdict.UNVERIFIABLE
