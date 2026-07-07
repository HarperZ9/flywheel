"""quorum falsifier — no single verifier is an authority; dissent is heard.

Properties that make it accountability-to-peers, not authority:
  - unanimity: one honest dissenter VETOES acceptance, even against a majority;
  - majority: the crowd decides, a lone dissenter cannot block;
  - no lone authority: a single PASS among failures cannot force acceptance;
  - the receipt records EVERY vote and names dissenters (answerability).
"""
import pytest

from harness.oracle import OracleResult
from harness.quorum import QuorumOracle, QuorumResult


class FixedOracle:
    def __init__(self, name, passes):
        self.oracle_type = name
        self._p = passes
    def verify(self, candidate, task):
        return OracleResult(passed=self._p, cmd=self.oracle_type, output_hash="h",
                            stdout_excerpt="", rc=0 if self._p else 1)


P = lambda n: FixedOracle(n, True)
F = lambda n: FixedOracle(n, False)


def test_unanimous_pass_accepts_and_records_votes():
    q = QuorumOracle([P("a"), P("b"), P("c")], unanimous=True)
    r = q.verify("x", None)
    assert r.passed and r.n_pass == 3 and r.quorum_needed == 3
    assert len(r.votes) == 3 and all(v["passed"] for v in r.votes)
    assert "ACCEPT" in r.accountability_receipt()


def test_one_dissenter_vetoes_under_unanimity():
    # 2 of 3 pass, but unanimity is required -> a single peer's objection blocks.
    q = QuorumOracle([P("a"), P("b"), F("skeptic")], unanimous=True)
    r = q.verify("x", None)
    assert r.passed is False, "one honest dissenter must veto under unanimity"
    assert "skeptic" in r.dissenters


def test_majority_lets_the_crowd_decide():
    # same 2-of-3, but simple majority -> accepted; the lone dissenter is recorded
    q = QuorumOracle([P("a"), P("b"), F("skeptic")], threshold=0.5)
    r = q.verify("x", None)
    assert r.passed is True and r.n_pass == 2 and r.quorum_needed == 2
    assert r.dissenters == ["skeptic"]


def test_no_lone_authority_can_force_acceptance():
    # a single PASS among failures never reaches quorum -> not accepted
    q = QuorumOracle([P("lone"), F("b"), F("c")], threshold=0.5)
    r = q.verify("x", None)
    assert r.passed is False and r.n_pass == 1
    assert "lone" in r.dissenters       # the lone yes-vote dissents from the reject


def test_tie_does_not_reach_majority():
    q = QuorumOracle([P("a"), F("b")], threshold=0.5)
    r = q.verify("x", None)
    assert r.quorum_needed == 2 and r.passed is False   # 1/2 is not a majority


def test_is_an_oracle_result():
    q = QuorumOracle([P("a")])
    r = q.verify("x", None)
    assert isinstance(r, QuorumResult) and r.verdict() in {"PASS", "FAIL"}


def test_empty_quorum_rejected_at_construction():
    with pytest.raises(ValueError):
        QuorumOracle([])
