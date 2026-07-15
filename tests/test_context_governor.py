"""The context governor: keep any model inside its reliable zone.

Nominal context is not reliable context; models degrade before their
stated limit (lost-in-the-middle, RULER). The governor curates the
window to a per-model reliable budget, and the load-bearing rule is the
governance-decay fix: a pinned constraint NEVER leaves the window, so
compaction cannot silently drop the thing holding the model correct.
Everything evicted is folded with a recall hash, so nothing is lost,
only moved. Model-agnostic: it operates on items and a token budget,
never on weights.
"""

import hashlib

from harness.context_governor import estimate_tokens, govern_context


def _item(cid, role, text, score=0.0):
    return {"id": cid, "role": role, "text": text, "score": score}


def test_pins_always_survive_even_under_a_tight_budget():
    items = [
        _item("c1", "pin", "MUST return cents as integers"),
        _item("e1", "evidence", "a " * 50, score=0.9),
        _item("e2", "evidence", "b " * 50, score=0.8),
    ]
    g = govern_context(items, budget=40, reliable_fraction=1.0)
    kept = {i["id"] for i in g["window"]}
    assert "c1" in kept, "a pinned constraint was evicted; that is the bug"
    assert g["schema"] == "flywheel.context-governor/v1"


def test_reliable_fraction_caps_fill_below_nominal():
    items = [_item(f"e{i}", "evidence", "word " * 100, score=1.0 - i * 0.01)
             for i in range(20)]
    full = govern_context(items, budget=1000, reliable_fraction=1.0)
    safe = govern_context(items, budget=1000, reliable_fraction=0.5)
    assert safe["used_tokens"] <= safe["reliable_budget"]
    assert safe["reliable_budget"] == 500
    assert len(safe["window"]) < len(full["window"])


def test_folded_overflow_is_actually_recoverable_not_just_hashed():
    """The governor claims verbatim recall of folded overflow. A one-way
    hash is not recoverable: the folded record must carry the text so a
    recall returns the exact span. Otherwise the claim outruns the receipt."""
    from harness.context_governor import recall_folded
    items = [_item("keep", "evidence", "x " * 5, score=0.99)] + \
            [_item(f"drop{i}", "evidence", f"payload-{i} unique text " * 20,
                   score=0.1) for i in range(4)]
    g = govern_context(items, budget=20, reliable_fraction=1.0)
    assert g["folded"], "expected some overflow to be folded"
    for f in g["folded"]:
        # recall by content hash returns the verbatim original text
        original = next(i for i in items if i["id"] == f["id"])["text"]
        assert recall_folded(g["folded"], f["sha256"]) == original


def test_evicted_items_are_folded_with_recoverable_hashes():
    items = [_item("keep", "evidence", "x " * 10, score=0.99)] + \
            [_item(f"drop{i}", "evidence", f"payload-{i} " * 40, score=0.1)
             for i in range(5)]
    g = govern_context(items, budget=30, reliable_fraction=1.0)
    kept = {i["id"] for i in g["window"]}
    folded = {f["id"] for f in g["folded"]}
    assert kept.isdisjoint(folded)
    assert kept | folded == {i["id"] for i in items}
    for f in g["folded"]:
        src = next(i for i in items if i["id"] == f["id"])
        assert f["sha256"] == hashlib.sha256(
            src["text"].encode()).hexdigest()


def test_higher_score_evidence_is_kept_over_lower():
    items = [_item("hi", "evidence", "w " * 20, score=0.9),
             _item("lo", "evidence", "w " * 20, score=0.1)]
    # each item estimates ~27 tokens; a budget of 30 admits exactly one
    g = govern_context(items, budget=30, reliable_fraction=1.0)
    kept = {i["id"] for i in g["window"]}
    assert "hi" in kept and "lo" not in kept


def test_over_pinning_is_named_not_silently_resolved():
    items = [_item(f"c{i}", "pin", "constraint " * 30) for i in range(5)]
    g = govern_context(items, budget=50, reliable_fraction=1.0)
    assert g["over_pinned"] is True
    # even over budget, no pin is dropped: the governor reports the
    # overflow honestly rather than eating a constraint
    assert len(g["window"]) == 5
    assert g["used_tokens"] > g["reliable_budget"]


def test_estimate_is_deterministic_and_monotonic():
    assert estimate_tokens("one two three") == estimate_tokens("one two three")
    assert estimate_tokens("a b c d e") > estimate_tokens("a b")


def test_a_clean_small_context_folds_nothing():
    items = [_item("c", "pin", "short"),
             _item("e", "evidence", "also short", score=0.5)]
    g = govern_context(items, budget=1000, reliable_fraction=1.0)
    assert g["folded"] == [] and g["over_pinned"] is False


def test_over_nominal_is_flagged_when_pins_exceed_the_hard_cap():
    from harness.context_governor import govern_context as gc
    items = [{"id": f"p{i}", "role": "pin", "text": "constraint " * 40}
             for i in range(4)]
    g = gc(items, budget=50, reliable_fraction=1.0)
    assert g["over_nominal"] is True and g["over_pinned"] is True


def test_within_nominal_is_not_over_nominal():
    from harness.context_governor import govern_context as gc
    g = gc([{"id": "p", "role": "pin", "text": "short pin"}],
           budget=1000, reliable_fraction=1.0)
    assert g["over_nominal"] is False
