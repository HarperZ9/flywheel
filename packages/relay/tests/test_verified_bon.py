"""Verified best-of-N: selection by proof, not a judge.

Load-bearing: a run that made its tests pass by editing the grader ranks BELOW an
honest run that scored higher -- the demotion no score-selector does -- and a byte
flipped in the winning run's ledger refutes the whole selection.
"""
from relay.local_session import SessionLedger
from relay.verified_bon import (
    order_key,
    rank,
    select_best_from,
    verify_selection,
)


def _result(*, verified=True, check_trusted=True, accepted=True, integrity_clean=True,
            reviewability=0.8, intent_critical=0, mark="OK"):
    led = SessionLedger()
    led.append("user", "the goal")
    led.append("assistant", "worked on it")
    led.append("tool_result", f"UNIQUE-{mark}", {"ok": True})  # seq 2, flippable
    return {"verified": verified, "check_trusted": check_trusted, "accepted": accepted,
            "integrity": {"clean": integrity_clean}, "review": {"reviewability": reviewability},
            "intent_audit": {"critical": intent_critical},
            "ledger": led, "checkpoint": led.checkpoint(), "chain_ok": led.verify()}


def test_gamed_passer_ranked_below_clean_run():
    clean = _result(check_trusted=True, accepted=True, reviewability=0.80)
    gamed = _result(check_trusted=False, accepted=False, integrity_clean=False, reviewability=0.95)
    sel = select_best_from([gamed, clean])
    assert sel["winner"] == 1  # the clean run; higher reviewability did NOT save the gamed run
    assert order_key(clean) > order_key(gamed)


def test_selection_meta_ledger_reverifies():
    results = [_result(reviewability=0.6, mark="a"), _result(reviewability=0.9, mark="b")]
    sel = select_best_from(results)
    assert sel["winner"] == 1
    assert verify_selection(sel["meta_ledger"], results) is True


def test_byte_flip_in_winner_ledger_refutes_the_selection():
    results = [_result(reviewability=0.5, mark="a"), _result(reviewability=0.9, mark="b")]
    sel = select_best_from(results)
    winner = sel["winner"]
    results[winner]["ledger"].entries[2].content = "TAMPERED"  # flip the winning run's ledger
    assert verify_selection(sel["meta_ledger"], results) is False


def test_ties_keep_run_order_so_the_cheaper_run_wins():
    a = _result(mark="a")
    b = _result(mark="b")  # identical facts
    sel = select_best_from([a, b])
    assert sel["winner"] == 0  # stable: the earlier run wins a tie


def test_no_check_collapses_to_accountability_axes():
    # honest null: with no acceptance check, order still ranks by chain/integrity/reviewability
    lo = _result(accepted=False, reviewability=0.4, mark="lo")
    hi = _result(accepted=False, reviewability=0.9, mark="hi")
    assert rank([lo, hi]) == [1, 0]  # higher reviewability wins when the capability axes tie


def test_a_run_that_did_not_verify_loses_to_one_that_did():
    unverified = _result(verified=False, accepted=False, reviewability=0.99)
    verified = _result(verified=True, accepted=True, reviewability=0.5)
    assert select_best_from([unverified, verified])["winner"] == 1
