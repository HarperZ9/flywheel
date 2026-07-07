"""composition-gap falsifier — the chain re-witnesses verdicts, not just links.

The gap this closes: validate_chain proved link integrity but TRUSTED the stored
verdict string, so a chain of FORGED PASS receipts with intact links returned
MATCH. With a rewitness callable, MATCH requires every stored verdict to reproduce
— criterion-conservation along the whole chain. Anti-theatrical: the rewitness
path must CATCH a forged verdict a structural check waves through.
"""
from harness.chain import StageReceipt, append_stage, validate_chain, chain_to_dicts


def _clean_chain():
    chain = []
    append_stage(chain, "propose", "in0", "out0", "PASS")
    append_stage(chain, "verify", "out0", "hashX", "PASS")
    append_stage(chain, "accept", "hashX", "envY", "PASS")
    return chain


def test_structural_match_is_backward_compatible():
    v = validate_chain(chain_to_dicts(_clean_chain()))
    assert v.verdict == "MATCH" and "structural" in v.reason


def test_rewitness_agreeing_is_match():
    dicts = chain_to_dicts(_clean_chain())
    # a re-witness that reproduces every stored verdict
    v = validate_chain(dicts, rewitness=lambda sd: sd["verdict"])
    assert v.verdict == "MATCH" and "re-witnessed" in v.reason


def test_forged_verdict_with_intact_links_is_caught():
    # Build a chain whose LINKS are intact but the 'verify' verdict is FORGED:
    # stored PASS, but re-witnessing the real oracle would say FAIL.
    chain = []
    append_stage(chain, "propose", "in0", "out0", "PASS")
    append_stage(chain, "verify", "out0", "hashX", "PASS")   # <- forged
    append_stage(chain, "accept", "hashX", "envY", "PASS")
    dicts = chain_to_dicts(chain)

    # structural validation waves it through (the gap)
    assert validate_chain(dicts).verdict == "MATCH"

    # re-witness: the verify stage actually FAILs -> chain must DRIFT, not MATCH
    truth = {"propose": "PASS", "verify": "FAIL", "accept": "PASS"}
    v = validate_chain(dicts, rewitness=lambda sd: truth[sd["stage"]])
    assert v.verdict == "DRIFT", v
    assert v.broken_at == 1 and "drifted" in v.reason


def test_unwitnessable_stage_is_unverifiable():
    dicts = chain_to_dicts(_clean_chain())
    v = validate_chain(dicts, rewitness=lambda sd: None)   # can't re-witness
    assert v.verdict == "UNVERIFIABLE"


def test_broken_link_still_unverifiable_before_rewitness():
    dicts = chain_to_dicts(_clean_chain())
    dicts[2]["prev_hash"] = "tampered"                     # break the last link
    # even with a permissive rewitness, the structural break is caught first
    v = validate_chain(dicts, rewitness=lambda sd: sd["verdict"])
    assert v.verdict == "UNVERIFIABLE" and v.broken_at == 2
