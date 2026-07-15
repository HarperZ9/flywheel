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


def test_one_objector_vetoes_under_unanimity():
    # 2 of 3 pass, but unanimity is required -> a single peer's objection blocks.
    # The skeptic's FAIL is recorded in the votes (the objection is answerable);
    # the dissenters-from-the-outcome are the two who wanted to accept.
    q = QuorumOracle([P("a"), P("b"), F("skeptic")], unanimous=True)
    r = q.verify("x", None)
    assert r.passed is False, "one honest objection must veto under unanimity"
    objection = next(v for v in r.votes if v["type"] == "skeptic")
    assert objection["passed"] is False        # the veto is on the record
    assert set(r.dissenters) == {"a", "b"}     # against the REJECT outcome


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


class IdOracle:
    """A verifier with an explicit identity: its own output_hash and model_ref."""
    def __init__(self, name, passes, ref, ohash):
        self.oracle_type = name
        self.model_ref = ref
        self._p, self._h = passes, ohash
    def verify(self, candidate, task):
        return OracleResult(passed=self._p, cmd=self.oracle_type,
                            output_hash=self._h, stdout_excerpt="", rc=0)


def test_stacked_ballot_is_visible_in_the_receipt():
    # One verifier counted twice must NOT look identical to two independent
    # peers: the receipt carries each member's identity so a stranger can
    # see the stacked ballot.
    same = IdOracle("judge", True, "endpoint-A", "same-hash")
    stacked = QuorumOracle([same, same], threshold=0.5)
    two_independent = QuorumOracle(
        [IdOracle("judge", True, "endpoint-A", "hash-1"),
         IdOracle("peer", True, "endpoint-B", "hash-2")], threshold=0.5)
    rs = stacked.verify("x", None)
    ri = two_independent.verify("x", None)
    # each vote carries identity
    assert all("output_hash" in v and "ref" in v for v in rs.votes)
    # the stacked pair shares one identity; the receipt says so
    assert rs.distinct_members == 1
    assert ri.distinct_members == 2
    # and the two receipts are not byte-identical
    assert rs.output_hash != ri.output_hash


def test_same_endpoint_under_two_names_is_flagged():
    # Two oracle_type names hitting the SAME endpoint (same model_ref) are one
    # voice, not two: the receipt flags the collision.
    q = QuorumOracle([IdOracle("a", True, "endpoint-X", "h1"),
                      IdOracle("b", True, "endpoint-X", "h2")], threshold=0.5)
    r = q.verify("x", None)
    assert r.distinct_members == 1     # one endpoint, one voice


def test_learned_member_is_refused_at_construction():
    class LearnedJudge:
        oracle_type = "llm-judge"
        learned = True
        def verify(self, c, t):
            return OracleResult(passed=True, cmd="", output_hash="h",
                                stdout_excerpt="", rc=0)
    with pytest.raises(ValueError) as e:
        QuorumOracle([P("code"), LearnedJudge()])
    assert "learned" in str(e.value).lower()


def test_dissenters_are_against_the_outcome_not_the_bare_majority():
    # threshold 0.6, n=5, 3 pass: needed = floor(3)+1 = 4, so the OUTCOME is
    # REJECT even though 3/5 is a bare majority. The dissenters (voices against
    # the outcome) are the PASS voters, not the FAIL voters.
    q = QuorumOracle([P("a"), P("b"), P("c"), F("d"), F("e")], threshold=0.6)
    r = q.verify("x", None)
    assert r.passed is False           # supermajority not reached
    assert set(r.dissenters) == {"a", "b", "c"}  # the outvoted PASS minority
