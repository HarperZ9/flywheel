"""The effort dial: one knob, named parameters, and the part Amp's Dial
lacks — the chosen effort is stamped into the receipt so two results at
different settings are comparable and re-checkable."""

from harness.effort import EFFORTS, resolve_effort


def test_the_dial_names_its_parameters():
    for name in ("low", "standard", "high", "ultra"):
        e = resolve_effort(name)
        assert e["name"] == name
        assert e["max_steps"] >= 2
        assert e["n_candidates"] >= 1
    assert resolve_effort("ultra")["max_steps"] > \
           resolve_effort("low")["max_steps"]
    assert resolve_effort("ultra")["n_candidates"] > \
           resolve_effort("low")["n_candidates"]


def test_unknown_effort_falls_back_named_not_silent():
    e = resolve_effort("turbo-plaid")
    assert e["name"] == "standard"
    assert "unknown effort" in e["note"]


def test_the_table_ships_so_the_receipt_is_re_derivable():
    assert set(EFFORTS) == {"low", "standard", "high", "ultra"}


def test_stamp_applied_tells_the_truth_about_the_enforced_budget():
    from harness.effort import resolve_effort, stamp_applied
    low = resolve_effort("low")            # nominal max_steps 4
    # caller overrode to 12 steps: the receipt must say so, not assert 4
    applied = stamp_applied(low, max_steps_applied=12)
    assert applied["max_steps_applied"] == 12
    assert applied["max_steps_overridden"] is True
    assert applied["n_candidates_applied"] is False   # this route does not fan out
    # no override: flagged false
    same = stamp_applied(low, max_steps_applied=4)
    assert same["max_steps_overridden"] is False
