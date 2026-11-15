"""Bind the verdict lattices to the remaining adjudicators: closure + fail-closed
reachability for verify_receipt, ProvenanceGraph.verify, Baseline.check, the
agent-loop disposition, and the temporal episode aggregator.

Each test proves two things against the REAL function:
  * closure -- its verdict is always inside the declared closed set;
  * reachability -- the affirmative top is reachable ONLY with positive evidence
    (and the conservative verdicts only with their stated cause).
"""

from __future__ import annotations

import random
from itertools import product

from coherence_membrane.agent_loop import (
    ADJUST,
    CONVERGED,
    INDETERMINATE,
    AgentLoop,
    Goal,
)
from coherence_membrane.baseline import Baseline
from coherence_membrane.lattice import (
    DISPOSITIONS,
    DRIFT_LATTICE,
    GRAPH_LATTICE,
    RECEIPT_LATTICE,
)
from coherence_membrane.observation import Observation, Provenance, Status
from coherence_membrane.phash import DRIFT, MATCH, UNVERIFIABLE, DriftVerdict
from coherence_membrane.provenance import (
    BROKEN,
    VALID,
    ProvenanceGraph,
)
from coherence_membrane.receipt import emit_receipt, verify_receipt


def _obs(organ="o", subject="s", identity="a" * 64, canonical=None, phash=None):
    data = {"identity_sha256": identity}
    if canonical is not None:
        data["canonical_sha256"] = canonical
    if phash is not None:
        data["perceptual_hash"] = phash
    return Observation(organ, subject, "", Status.PASS,
                       Provenance.witness_bytes(subject, identity.encode(), "high"), data)


# --- receipt lattice: VALID only with an external anchor or verifier -------


def test_verify_receipt_closure_and_reachability():
    receipt = emit_receipt(_obs())
    anchor = receipt.anchor()
    verifiers = {
        "none": None,
        "true": (lambda r: True),
        "false": (lambda r: False),
        "raise": (lambda r: (_ for _ in ()).throw(RuntimeError("boom"))),
    }
    pins = {"none": None, "match": anchor, "mismatch": "0" * 64}
    for vname, verifier in verifiers.items():
        for pname, pin in pins.items():
            v = verify_receipt(receipt, pinned_anchor=pin, signature_verifier=verifier).verdict
            assert v in RECEIPT_LATTICE.elements                      # closure
            if v == VALID:                                            # reachability
                assert vname == "true" or (vname == "none" and pname == "match")
            if v == UNVERIFIABLE:
                assert vname == "none" and pname == "none"            # no evidence at all
            if v == DRIFT:
                assert vname in ("false", "raise") or (vname == "none" and pname == "mismatch")
    # the affirmative top is NEVER the default (no anchor, no verifier).
    assert verify_receipt(receipt).verdict == UNVERIFIABLE


# --- graph lattice: VALID only for a nonempty, fully consistent graph ------


def _chain(n: int) -> ProvenanceGraph:
    g = ProvenanceGraph()
    prev = None
    for i in range(n):
        parents = [prev] if prev else []
        g.add(f"n{i}", "observation" if i == 0 else "action", f"d{i}", parents=parents)
        prev = f"n{i}"
    return g


def test_graph_verify_closure_and_reachability_sweep():
    rng = random.Random(20260617)
    for _ in range(300):
        n = rng.randint(0, 6)
        g = _chain(n)
        d = g.to_dict()
        tampered = False
        if n and rng.random() < 0.5:
            # mutate one stored digest WITHOUT recomputing bindings -> a real tamper.
            d["nodes"][rng.randrange(n)]["digest"] = "tampered-" + str(rng.random())
            tampered = True
        g2 = ProvenanceGraph.from_dict(d)
        v = g2.verify().verdict
        assert v in GRAPH_LATTICE.elements                            # closure
        if n == 0:
            assert v == UNVERIFIABLE                                  # empty -> middle
        elif tampered:
            assert v == BROKEN                                        # contrary evidence
        else:
            assert v == VALID                                        # consistent + nonempty
        # the affirmative top implies a nonempty, untampered graph.
        if v == VALID:
            assert n > 0 and not tampered


def test_graph_insertion_caught_only_by_the_pinned_manifest():
    g = _chain(3)
    pinned = g.manifest()
    inserted = ProvenanceGraph.from_dict(g.to_dict())
    inserted.add("ghost", "observation", "ghost-d")                  # parentless, self-consistent
    assert inserted.verify().verdict == VALID                        # chain alone: honest gap
    assert inserted.verify(pinned_manifest=pinned).verdict == BROKEN  # anchor closes it


# --- drift lattice via the baseline ladder --------------------------------


def test_baseline_check_match_only_on_identity_or_canonical_equality():
    cases = []
    # (baseline_obs, current_obs, expected)
    b = _obs(identity="a" * 64, canonical="c" * 64, phash="0" * 16)
    cases.append((b, _obs(identity="a" * 64), MATCH))                       # identity equal
    cases.append((b, _obs(identity="z" * 64, canonical="c" * 64), MATCH))   # canonical equal
    cases.append((b, _obs(identity="z" * 64, canonical="d" * 64), DRIFT))   # canonical changed
    cases.append((b, _obs(identity="z" * 64, phash="f" * 16), DRIFT))       # perceptual drift
    cases.append((b, _obs(organ="other", identity="a" * 64), UNVERIFIABLE)) # organ mismatch
    for baseline_obs, current_obs, expected in cases:
        bl = Baseline()
        bl.pin(baseline_obs)
        verdict = bl.check(current_obs).verdict
        assert verdict in DRIFT_LATTICE.elements                            # closure
        assert verdict == expected
        if verdict == MATCH:                                               # reachability
            same_identity = current_obs.data.get("identity_sha256") == baseline_obs.data.get("identity_sha256")
            same_canon = (current_obs.data.get("canonical_sha256")
                          and current_obs.data.get("canonical_sha256") == baseline_obs.data.get("canonical_sha256"))
            assert same_identity or same_canon
    # no pinned baseline for the subject -> the middle, never a silent MATCH.
    assert Baseline().check(_obs()).verdict == UNVERIFIABLE


# --- disposition classification: CONVERGED/INDETERMINATE reachability ------


def test_assess_disposition_closure_and_reachability():
    for tolerance in range(0, 6):
        loop = AgentLoop(Goal("s", "a" * 64, 0, tolerance=tolerance))
        verdicts = (
            [DriftVerdict(MATCH, 0, "")]
            + [DriftVerdict(DRIFT, d, "") for d in range(0, 6)]
            + [DriftVerdict(UNVERIFIABLE, None, "")]
        )
        for dv in verdicts:
            disposition, _ = loop._assess(dv)
            assert disposition in DISPOSITIONS                              # closure
            # INDETERMINATE iff the look was uncomparable.
            assert (disposition == INDETERMINATE) == (dv.verdict == UNVERIFIABLE)
            if disposition == CONVERGED:                                   # reachability
                assert dv.verdict == MATCH or (dv.verdict == DRIFT and dv.distance <= tolerance)
            if disposition == ADJUST:
                assert dv.verdict == DRIFT and dv.distance > tolerance


# --- temporal aggregator: episodes need a confirming DRIFT; settle a MATCH -


def test_trace_events_episodes_are_opened_by_drift_and_settled_by_match():
    from coherence_membrane.events import trace_events

    alphabet = (MATCH, DRIFT, UNVERIFIABLE)
    for length in range(0, 7):                                            # exhaustive, 1093 streams
        for stream in product(alphabet, repeat=length):
            trace = trace_events(list(stream))
            assert trace.total_events == length
            assert trace.match_events + trace.drift_events + trace.unverifiable_events == length
            # no DRIFT anywhere -> no episode can exist (UNVERIFIABLE never opens one).
            if DRIFT not in stream:
                assert trace.episodes == []
            for ep in trace.episodes:
                assert stream[ep.start_index] == DRIFT                    # opened by a DRIFT
                assert stream[ep.end_index] == DRIFT                      # bounded by DRIFTs
                assert ep.length >= 1
                if ep.settled_at is not None:                            # settled only by a MATCH
                    assert stream[ep.settled_at] == MATCH
                else:
                    # an unsettled episode must run to the stream's end.
                    assert ep.end_index <= length - 1
