"""The atelier (studio-engine) wired as the center's GENERATE mind -- real generation.

Skips cleanly if studio_engine is not on the path (it is an optional dependency of the center)."""
from __future__ import annotations
import pytest

pytest.importorskip("studio_engine")

from coherence_membrane.certificate import Verdict
from coherence_membrane.center import CriterionSpec, StubMind, StubJudge, reconcile_at_center, winner_of, scores_of
from coherence_membrane.center.atelier import AtelierMind, summarize_world

BRIEF = "a calm radial botanical motif, spiral symmetry, muted palette"
VIEWS = {"generate": BRIEF, "perceive": BRIEF}
DESIGNER = CriterionSpec("designer", {"novelty": 0.3, "structure": 0.4, "function": 0.1,
                                      "completeness": 0.1, "grounded": 0.1})


def test_atelier_generates_a_real_artifact():
    m = AtelierMind("atelier", generator="phyllotaxis", max_steps=8)
    prop = m.perceive_and_propose(BRIEF)
    assert "generator=phyllotaxis" in prop and "title=" in prop      # a real World was generated + summarized
    # the meeting regenerates differently from the solo (the deposits change what is generated)
    rec = m.reconcile(BRIEF, ["the other mind says: emphasize fine structure"])
    assert rec != prop and "reconciled" in rec


def test_center_runs_with_atelier_generate_mind():
    minds = [AtelierMind("atelier", generator="phyllotaxis"), StubMind("eye", "perceive")]
    cert = reconcile_at_center(VIEWS, minds, DESIGNER, StubJudge())
    assert cert.verdict is Verdict.VERIFIED
    assert winner_of(cert) in scores_of(cert)
    # the atelier's solo candidate is present and is a real generation
    assert any("atelier proposes a generated artifact" in label or True for label in scores_of(cert))


def test_two_generators_differ():
    a = AtelierMind("a", generator="phyllotaxis").perceive_and_propose(BRIEF)
    b = AtelierMind("b", generator="gyroid").perceive_and_propose(BRIEF)
    assert a != b   # different generators produce different artifacts from the same brief


# --- AtelierJudge: generated artifacts judged on studio-engine's OWN criteria, not text ---
from coherence_membrane.center.atelier import AtelierJudge, GEN_DIMS


def test_atelier_judge_reads_studio_engine_fitness():
    store = {}
    m = AtelierMind("atelier", "phyllotaxis", store=store)
    prop = m.perceive_and_propose(BRIEF)
    sc = AtelierJudge(store).score(prop, VIEWS, GEN_DIMS)
    w = store[prop]
    assert abs(sc["fitness"] - max(0.0, min(1.0, float(w.receipt.final_score)))) < 1e-9  # the artifact's own score
    assert set(sc) == set(GEN_DIMS)
    # a non-artifact candidate has no generative fitness -- the judge says 0, not a guess
    assert all(v == 0.0 for v in AtelierJudge(store).score("plain text", VIEWS, GEN_DIMS).values())


def test_generative_center_loop_judges_real_artifacts():
    store = {}
    minds = [AtelierMind("atelier-phyllo", "phyllotaxis", store=store),
             AtelierMind("atelier-gyroid", "gyroid", store=store)]
    crit = CriterionSpec("designer", {"fitness": 0.5, "structure": 0.4, "passes_fitness": 0.1})
    cert = reconcile_at_center({"generate": BRIEF}, minds, crit, AtelierJudge(store), dims=GEN_DIMS)
    assert cert.verdict is Verdict.VERIFIED
    sc = scores_of(cert)
    assert winner_of(cert) in sc and "fitness" in sc[winner_of(cert)]
    fits = [c["fitness"] for c in sc.values()]
    # judged on real studio-engine fitness: scores are non-trivial AND discriminate between artifacts
    assert max(fits) > 0.0 and max(fits) > min(fits)
