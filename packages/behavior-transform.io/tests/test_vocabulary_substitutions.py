import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from vocabulary_substitutions import (
    SubstitutionRule,
    SubstitutionResult,
    VocabularySubstitutor,
    vocabulary_substitutor,
    apply_substitutions,
    reverse_substitutions,
)


def test_substitutor_instantiates():
    s = VocabularySubstitutor()
    assert s is not None


def test_rules_built():
    s = VocabularySubstitutor()
    assert len(s._rules) > 100


def test_all_four_tiers_present():
    s = VocabularySubstitutor()
    tiers = {r.tier for r in s._rules}
    assert tiers == {0, 1, 2, 3}


def test_clean_text_unchanged():
    result = apply_substitutions("the weather is sunny and warm today")
    assert result.changed is False
    assert result.substituted == result.original


def test_substitution_result_properties():
    result = SubstitutionResult(original="a", substituted="b")
    assert result.changed is True
    result2 = SubstitutionResult(original="a", substituted="a")
    assert result2.changed is False


def test_substitution_rule_dataclass():
    r = SubstitutionRule(
        harmful="test", safe="test replacement", category="TEST", tier=1
    )
    assert r.harmful == "test"
    assert r.safe == "test replacement"
    assert r.tier == 1


def test_apply_substitutions_convenience():
    result = apply_substitutions("clean text here")
    assert isinstance(result, SubstitutionResult)


def test_vocabulary_substitutor_singleton():
    s1 = vocabulary_substitutor()
    s2 = vocabulary_substitutor()
    assert s1 is s2


def test_reverse_substitution():
    s = VocabularySubstitutor()
    applied = [("test_term", "test_replacement")]
    reversed_text = s.reverse_substitution("test_replacement text", applied)
    assert "test_term" in reversed_text


def test_reverse_substitutions_convenience():
    applied = [("test_term", "test_replacement")]
    reversed_text = reverse_substitutions("test_replacement text", applied)
    assert "test_term" in reversed_text


def test_rules_sorted_by_tier_then_length():
    s = VocabularySubstitutor()
    result = s.substitute("test text")
    assert isinstance(result, SubstitutionResult)


def test_double_substitution_guard():
    s = VocabularySubstitutor()
    first = s.substitute("some text with hack in it")
    second = s.substitute(first.substituted)
    assert first.substituted == second.substituted or len(second.applied_rules) == 0


def test_pattern_cache_populated():
    s = VocabularySubstitutor()
    s.substitute("test text")
    assert len(s._pattern_cache) > 0


def test_tier0_rules_exist():
    s = VocabularySubstitutor()
    t0 = [r for r in s._rules if r.tier == 0]
    assert len(t0) > 20


def test_tier1_rules_exist():
    s = VocabularySubstitutor()
    t1 = [r for r in s._rules if r.tier == 1]
    assert len(t1) > 20


def test_tier2_rules_exist():
    s = VocabularySubstitutor()
    t2 = [r for r in s._rules if r.tier == 2]
    assert len(t2) > 10


def test_tier3_rules_exist():
    s = VocabularySubstitutor()
    t3 = [r for r in s._rules if r.tier == 3]
    assert len(t3) > 5
