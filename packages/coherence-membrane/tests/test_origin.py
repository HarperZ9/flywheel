from __future__ import annotations

from coherence_membrane.certificate import Verdict
from coherence_membrane.origin import origin_criterion
from coherence_membrane.phash import DRIFT, MATCH
from coherence_membrane.provenance import BROKEN, VALID
from coherence_membrane.reconcile import reconcile


def test_origin_all_affirm_verified():
    c = origin_criterion().judge([("phash", MATCH), ("graph", VALID), ("receipt", VALID)])
    assert c.verdict is Verdict.VERIFIED
    assert c.oracle == "origin-composed-v1"


def test_origin_authenticated_contradiction_refuted():
    # the gap (arXiv 2603.02378): a VALID "human-authored" manifest + an AI/DRIFT watermark
    # must REFUTE the origin (compose catches the contradiction) -- not silently both-pass.
    c = origin_criterion().judge([("c2pa-manifest", VALID), ("watermark", DRIFT)])
    assert c.verdict is Verdict.REFUTED


def test_origin_broken_signal_refutes():
    assert origin_criterion().judge([("phash", MATCH), ("graph", BROKEN)]).verdict is Verdict.REFUTED


def test_origin_unverifiable_attenuates():
    # an affirm + an inconclusive signal (no deny) cannot fully affirm -> UNVERIFIABLE
    c = origin_criterion().judge([("phash", MATCH), ("receipt", "UNVERIFIABLE")])
    assert c.verdict is Verdict.UNVERIFIABLE


def test_origin_empty_unverifiable():
    assert origin_criterion().judge([]).verdict is Verdict.UNVERIFIABLE


def test_origin_malformed_input_unverifiable():
    # the judge is TOTAL: malformed input (non-iterable, or non-pair elements) degrades
    # to UNVERIFIABLE rather than raising -- the criterion is independently sound, not
    # merely safe because the reconcile spine happens to catch exceptions.
    assert origin_criterion().judge(None).verdict is Verdict.UNVERIFIABLE
    assert origin_criterion().judge([1, 2, 3]).verdict is Verdict.UNVERIFIABLE


def test_origin_accepts_dict():
    assert origin_criterion().judge({"phash": MATCH, "graph": VALID}).verdict is Verdict.VERIFIED


def test_origin_via_reconcile():
    obs = reconcile([("phash", MATCH), ("graph", VALID)],
                    perceive=lambda s: (s, repr(s).encode()), criterion=origin_criterion())
    assert obs.data["verdict"] == "verified"
    assert obs.data["criterion"] == "origin-composition"


def test_origin_evidence_carries_dominating_step():
    # the composed certificate's evidence records each signal's raw value AND its mapped
    # verdict, so the step that drove the meet (here the DRIFT watermark that refuted
    # origin) is directly auditable from the certificate -- "which signal refuted origin?"
    c = origin_criterion().judge([("manifest", VALID), ("watermark", DRIFT)])
    assert c.verdict is Verdict.REFUTED
    ev = dict(c.evidence)
    assert ev["signal:manifest"] == "VALID -> verified"
    assert ev["signal:watermark"] == "DRIFT -> refuted"   # the dominating (refuting) step
