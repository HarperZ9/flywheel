import pytest
from solution import fold_events


def test_applied_in_timestamp_order_not_input_order():
    assert fold_events([("set", 5, "a", 2), ("set", 1, "a", 1)]) == {"a": 2}
    assert fold_events([("set", 3, "a", "x"), ("set", 2, "a", "y")]) == {"a": "x"}


def test_del_removes_key():
    assert fold_events([("set", 1, "a", 1), ("del", 2, "a")]) == {}


def test_del_beats_set_at_same_timestamp_regardless_of_input_order():
    assert fold_events([("del", 5, "a"), ("set", 5, "a", 9)]) == {}
    assert fold_events([("set", 5, "a", 9), ("del", 5, "a")]) == {}


def test_same_ts_same_key_sets_later_input_wins():
    evs = [("set", 3, "a", "first"), ("set", 3, "a", "second")]
    assert fold_events(evs) == {"a": "second"}


def test_del_absent_ok_and_set_after_del():
    evs = [("del", 1, "ghost"), ("set", 2, "a", 1), ("del", 2, "a"),
           ("set", 3, "a", 7)]
    assert fold_events(evs) == {"a": 7}


def test_malformed_events_raise():
    with pytest.raises(ValueError):
        fold_events([["set", 1, "a", 1]])  # not a tuple
    with pytest.raises(ValueError):
        fold_events([("put", 1, "a", 1)])  # unknown op
    with pytest.raises(ValueError):
        fold_events([("set", 1, "a")])  # bad arity for set
    with pytest.raises(ValueError):
        fold_events([("del", 1, "a", 1)])  # bad arity for del
    with pytest.raises(ValueError):
        fold_events([("set", -1, "a", 1)])  # negative ts
    with pytest.raises(ValueError):
        fold_events([("set", True, "a", 1)])  # bool ts rejected
    with pytest.raises(ValueError):
        fold_events([("set", 1.0, "a", 1)])  # non-int ts
    with pytest.raises(ValueError):
        fold_events([("set", 1, 7, 1)])  # non-str key
    with pytest.raises(ValueError):
        fold_events([()])  # empty tuple


def test_no_mutation():
    evs = [("set", 5, "a", 2), ("del", 5, "a"), ("set", 1, "b", 0)]
    snap = list(evs)
    fold_events(evs)
    assert evs == snap


def test_empty_input():
    assert fold_events([]) == {}
