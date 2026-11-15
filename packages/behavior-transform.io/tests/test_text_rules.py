import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import re
import pytest
from collections import Counter

from text_rules import (
    TextRule,
    collect_text_rules,
    apply_text_rules,
    scan_text_rules,
    is_rule_source_path,
    load_rule_source,
)


def test_text_rule_frozen():
    rule = TextRule(
        pattern=re.compile(r"\bfoo\b"),
        replacement="bar",
        tier="T1",
    )
    with pytest.raises(AttributeError):
        rule.tier = "T2"


def test_text_rule_fields():
    rule = TextRule(
        pattern=re.compile(r"\bfoo\b"),
        replacement="bar",
        tier="T1",
    )
    assert rule.replacement == "bar"
    assert rule.tier == "T1"


def test_collect_text_rules_no_source():
    rules = collect_text_rules(source=None)
    assert isinstance(rules, list)


def test_apply_text_rules_empty():
    text, counter = apply_text_rules("hello world", [])
    assert text == "hello world"
    assert dict(counter) == {}


def test_apply_text_rules_single_match():
    rule = TextRule(
        pattern=re.compile(r"\bhello\b", re.IGNORECASE),
        replacement="greeting",
        tier="T1",
    )
    text, counter = apply_text_rules("hello world", [rule])
    assert text == "greeting world"
    assert counter["T1"] == 1


def test_apply_text_rules_multiple():
    rule = TextRule(
        pattern=re.compile(r"\bfoo\b"),
        replacement="bar",
        tier="T2",
    )
    text, counter = apply_text_rules("foo and foo", [rule])
    assert text == "bar and bar"
    assert counter["T2"] == 2


def test_scan_text_rules_returns_matches():
    rule = TextRule(
        pattern=re.compile(r"\bhello\b", re.IGNORECASE),
        replacement="greeting",
        tier="T1",
    )
    counter, matches = scan_text_rules("Hello world hello", [rule])
    assert counter["T1"] == 2
    assert len(matches) == 1
    assert matches[0][2] == "T1"


def test_scan_text_rules_no_matches():
    rule = TextRule(
        pattern=re.compile(r"\bxyz\b"),
        replacement="abc",
        tier="T1",
    )
    counter, matches = scan_text_rules("nothing here", [rule])
    assert dict(counter) == {}
    assert matches == []


def test_is_rule_source_path_true():
    assert is_rule_source_path(Path("/some/dir/vocabulary_map.py")) is True
    assert is_rule_source_path(Path("/some/dir/prose_vocabulary_map.py")) is True


def test_is_rule_source_path_false():
    assert is_rule_source_path(Path("/some/dir/other.py")) is False
