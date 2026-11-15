"""Tests for the criterion-independence witness -- the BEFORE/AFTER closure of the seam.

BEFORE: without witnessing, a self-authored reconcile is BYTE-IDENTICAL to an independent
one (the seam). AFTER: with independence witnessed, the self-authored case is marked
`self-authored` and (strict mode) its decided verdict downgrades to UNVERIFIABLE, while
the independent case stays decided. Also pins the additive/default-preserving contract.
"""
from __future__ import annotations

import json

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.observation import Status
from coherence_membrane.propositional import And, Implies, Var, check_validity
from coherence_membrane.reconcile import (
    Criterion,
    reconcile,
    witness_independence,
)
from experiments.criterion_independence import after, before


def _mp():
    A, B = Var("A"), Var("B")
    return Implies(And(A, Implies(A, B)), B)


def _decided_criterion(author=None):
    return Criterion("wellformed", lambda f: Certificate("c", Verdict.VERIFIED, "v1"),
                     author=author)


# ---------------------------------------------------------------------------------------
# BEFORE -- the seam: self-grading is byte-indistinguishable from independent grading.
# ---------------------------------------------------------------------------------------

def test_before_self_and_independent_are_byte_identical():
    # WITHOUT independence witnessing (no `producer`), a self-authored criterion and an
    # independent one produce BYTE-IDENTICAL Observations -- the seam the system can't see.
    b_self, b_indep = before()
    assert b_self == b_indep
    # both are honestly marked "unwitnessed" and the differing author is NOT leaked.
    d = json.loads(b_self.decode())
    assert d["data"]["independence"] == "unwitnessed"
    assert "criterion_author" not in d["data"]
    assert "artifact_producer" not in d["data"]


def test_before_holds_for_arbitrary_authors_without_producer():
    # Generalised: two criteria differing ONLY in their author id, with no producer
    # witnessed, are indistinguishable in the emitted Observation content.
    def canon(obs):
        x = obs.to_dict()
        x["provenance"] = dict(x["provenance"])
        x["provenance"]["timestamp"] = "<t>"
        return json.dumps(x, sort_keys=True)

    a = reconcile(_mp(), criterion=_decided_criterion(author="org:A"))
    b = reconcile(_mp(), criterion=_decided_criterion(author="org:Z"))
    assert canon(a) == canon(b)


# ---------------------------------------------------------------------------------------
# AFTER -- the closure: witnessing distinguishes the two and downgrades the self-graded one.
# ---------------------------------------------------------------------------------------

def test_after_self_authored_is_marked_and_downgraded():
    self_obs, indep_obs = after()
    # self-authored: marked, decided verdict downgraded to UNVERIFIABLE, status unverified.
    assert self_obs.data["independence"] == "self-authored"
    assert self_obs.data["verdict"] == "unverifiable"
    assert self_obs.status is Status.UNVERIFIED
    assert self_obs.data["downgrade_reason"] == \
        "verdict from a self-authored criterion (independence not witnessed)"
    # independent: marked witnessed-independent, verdict stays decided.
    assert indep_obs.data["independence"] == "witnessed-independent"
    assert indep_obs.data["verdict"] == "verified"
    assert indep_obs.status is Status.PASS


def test_after_observations_are_distinguishable():
    self_obs, indep_obs = after()
    assert self_obs.to_dict() != indep_obs.to_dict()
    # the witnessed ids are now recorded (only because independence is witnessed).
    assert self_obs.data["criterion_author"] == self_obs.data["artifact_producer"]
    assert indep_obs.data["criterion_author"] != indep_obs.data["artifact_producer"]


# ---------------------------------------------------------------------------------------
# witness_independence -- the pure tri-state resolver.
# ---------------------------------------------------------------------------------------

def test_witness_independence_tristate():
    assert witness_independence("a", "b") == "witnessed-independent"
    assert witness_independence("a", "a") == "self-authored"
    assert witness_independence(None, "a") == "unwitnessed"
    assert witness_independence("a", None) == "unwitnessed"
    assert witness_independence(None, None) == "unwitnessed"


# ---------------------------------------------------------------------------------------
# Default-preserving / additive contract.
# ---------------------------------------------------------------------------------------

def test_default_mode_does_not_alter_verdict_even_when_self_authored():
    # strict OFF (default): a self-authored decided verdict is annotated but NOT changed.
    obs = reconcile(_mp(), criterion=_decided_criterion(author="org:A"), producer="org:A")
    assert obs.data["independence"] == "self-authored"
    assert obs.data["verdict"] == "verified"     # verdict UNCHANGED in default mode
    assert obs.status is Status.PASS
    assert "downgrade_reason" not in obs.data


def test_strict_does_not_touch_witnessed_independent_or_unverifiable():
    # strict mode only downgrades the self-authored DECIDED case; an independent decided
    # verdict and a self-authored UNDECIDED verdict are passed through unchanged.
    indep = reconcile(_mp(), criterion=_decided_criterion(author="org:B"),
                      producer="org:A", strict=True)
    assert indep.data["verdict"] == "verified"

    def unver(_f):
        return Certificate("c", Verdict.UNVERIFIABLE, "v1")

    self_unver = reconcile(_mp(), criterion=Criterion("u", unver, author="org:A"),
                           producer="org:A", strict=True)
    assert self_unver.data["verdict"] == "unverifiable"
    assert "downgrade_reason" not in self_unver.data   # already undecided, not a downgrade


def test_legacy_call_is_unchanged_apart_from_unwitnessed_annotation():
    # An existing-style call (no author, no producer) keeps EXACTLY its old verdict/status
    # and oracle/claim, gaining only the honest independence="unwitnessed" annotation.
    obs = reconcile(_mp(), criterion=Criterion("propositional-dpll", check_validity))
    assert obs.status is Status.PASS
    assert obs.data["verdict"] == "verified"
    assert obs.data["oracle"] == "propositional-dpll-v1"
    assert obs.data["independence"] == "unwitnessed"
    assert "criterion_author" not in obs.data and "artifact_producer" not in obs.data


def test_strict_downgrade_also_witnessed_in_failclosed_path_keeps_independence():
    # even when the judge itself fails (fail-closed exception path), the independence
    # annotation is still recorded (producer is known regardless of the judge outcome).
    def boom(_f):
        raise RuntimeError("judge boom")

    obs = reconcile(_mp(), criterion=Criterion("c", boom, author="org:A"),
                    producer="org:A", strict=True)
    assert obs.data["verdict"] == "unverifiable"      # fail-closed, as before
    assert obs.data["independence"] == "self-authored"
