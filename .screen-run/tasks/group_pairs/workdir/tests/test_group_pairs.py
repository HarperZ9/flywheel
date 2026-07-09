import pytest
from solution import group_pairs


def test_groups_in_first_seen_key_order():
    out = group_pairs([("b", 1), ("a", 2), ("b", 3), ("c", 4), ("a", 5)])
    assert out == {"b": [1, 3], "a": [2, 5], "c": [4]}
    assert list(out) == ["b", "a", "c"]


def test_duplicate_pairs_kept():
    assert group_pairs([("k", 1), ("k", 1)]) == {"k": [1, 1]}


def test_value_identity_preserved():
    v1, v2 = [1, 2], {"x": 1}
    out = group_pairs([("a", v1), ("a", v2)])
    assert out["a"][0] is v1
    assert out["a"][1] is v2


def test_rejects_list_entry():
    with pytest.raises(ValueError):
        group_pairs([("a", 1), ["b", 2]])


def test_rejects_wrong_length_tuple():
    with pytest.raises(ValueError):
        group_pairs([("a", 1, 2)])
    with pytest.raises(ValueError):
        group_pairs([("a",)])


def test_rejects_tuple_subclass():
    class T(tuple):
        pass

    with pytest.raises(ValueError):
        group_pairs([T(("a", 1))])


def test_input_not_mutated():
    pairs = [("a", 1), ("b", 2)]
    snapshot = list(pairs)
    group_pairs(pairs)
    assert pairs == snapshot


def test_empty():
    assert group_pairs([]) == {}
