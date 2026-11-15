from __future__ import annotations

from coherence_membrane.certificate import Certificate, Verdict
from coherence_membrane.composition import compose, meet_verdicts, quorum


def _c(verdict, oracle="o"):
    return Certificate("step", verdict, oracle)


def test_meet_verdicts_semantics():
    V, R, U = Verdict.VERIFIED, Verdict.REFUTED, Verdict.UNVERIFIABLE
    assert meet_verdicts([V, V, V]) is V
    assert meet_verdicts([V, R, V]) is R          # REFUTED absorbs (lattice bottom)
    assert meet_verdicts([V, U, V]) is U          # UNVERIFIABLE attenuates
    assert meet_verdicts([R, U]) is R             # REFUTED dominates UNVERIFIABLE
    assert meet_verdicts([V]) is V
    assert meet_verdicts([]) is V                 # meet identity (top)


def test_compose_all_verified():
    c = compose([_c(Verdict.VERIFIED), _c(Verdict.VERIFIED)])
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "composed-v1"
    assert dict(c.evidence)["step0:o"] == "verified"


def test_compose_evidence_distinguishes_same_oracle_steps():
    # two steps from the same oracle must stay distinct in the evidence (indexed keys)
    c = compose([_c(Verdict.REFUTED, "z"), _c(Verdict.VERIFIED, "z")])
    ev = dict(c.evidence)
    assert ev["step0:z"] == "refuted" and ev["step1:z"] == "verified"


def test_compose_refuted_dominates():
    c = compose([_c(Verdict.VERIFIED), _c(Verdict.REFUTED, "bad"), _c(Verdict.UNVERIFIABLE)])
    assert c.verdict is Verdict.REFUTED


def test_compose_unverifiable_attenuates():
    c = compose([_c(Verdict.VERIFIED), _c(Verdict.UNVERIFIABLE, "dunno")])
    assert c.verdict is Verdict.UNVERIFIABLE


def test_compose_empty_is_unverifiable():
    # fail-closed: an empty argument verified nothing (NOT vacuous VERIFIED)
    c = compose([])
    assert c.verdict is Verdict.UNVERIFIABLE


def test_compose_matches_lattice_meet_exhaustively():
    # compose's verdict must equal the proven DRIFT_LATTICE meet for every pair
    from coherence_membrane.lattice import DRIFT_LATTICE
    from coherence_membrane.phash import DRIFT, MATCH, UNVERIFIABLE
    v2l = {Verdict.VERIFIED: MATCH, Verdict.REFUTED: DRIFT, Verdict.UNVERIFIABLE: UNVERIFIABLE}
    for a in Verdict:
        for b in Verdict:
            got = compose([_c(a), _c(b)]).verdict
            assert v2l[got] == DRIFT_LATTICE.meet(v2l[a], v2l[b])


# --- A1: quorum -- robust consensus over independent judges (the readout-gate) ----------

def test_quorum_supermajority_decides():
    V, R, U = Verdict.VERIFIED, Verdict.REFUTED, Verdict.UNVERIFIABLE
    assert quorum([_c(V), _c(V), _c(V)]).verdict is V
    assert quorum([_c(V), _c(V), _c(R)]).verdict is V       # 2/3 majority, one dissent can't flip
    assert quorum([_c(V), _c(R), _c(U)]).verdict is U       # no majority -> UNVERIFIABLE


def test_quorum_single_voice_cannot_flip_or_veto():
    V, R, U = Verdict.VERIFIED, Verdict.REFUTED, Verdict.UNVERIFIABLE
    assert quorum([_c(V)] * 4 + [_c(R)]).verdict is V        # one loud REFUTED can't veto truth
    assert quorum([_c(V)] + [_c(U)] * 4).verdict is U        # lone VERIFIED can't reach quorum
    assert quorum([_c(R)] + [_c(U)] * 4).verdict is U        # lone REFUTED can't impose REFUTED


def test_quorum_empty_is_unverifiable():
    assert quorum([]).verdict is Verdict.UNVERIFIABLE


def test_quorum_high_threshold_needs_unanimity():
    V, R, U = Verdict.VERIFIED, Verdict.REFUTED, Verdict.UNVERIFIABLE
    assert quorum([_c(V), _c(V), _c(V)], threshold=0.9).verdict is V
    assert quorum([_c(V), _c(V), _c(R)], threshold=0.9).verdict is U   # bare majority insufficient


def test_quorum_tally_evidence_is_auditable():
    cert = quorum([_c(Verdict.VERIFIED), _c(Verdict.VERIFIED), _c(Verdict.REFUTED)])
    ev = dict(cert.evidence)
    assert ev["verified"] == "2" and ev["refuted"] == "1" and ev["judges"] == "3"
    assert cert.oracle == "quorum-v1"
