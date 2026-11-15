from __future__ import annotations

import types as _types

from coherence_membrane.pngencode import encode_png
from coherence_membrane.retro import render_vintage
from coherence_membrane.render_critic import render_fidelity_deviation
from coherence_membrane.phash import hamming as _hamming


def _gradient_png(w=32, h=32) -> bytes:
    """A deterministic horizontal RGB gradient PNG (something to quantize)."""
    rows = bytearray()
    for y in range(h):
        for x in range(w):
            rows.extend((int(255 * x / (w - 1)), int(255 * y / (h - 1)), 128))
    return encode_png(w, h, bytes(rows), channels=3)


def test_fidelity_faithful_lower_than_aggressive():
    src = _gradient_png()
    faithful = render_vintage(src, target_width=32, palette_k=16, dither=True, scanlines=False)
    aggressive = render_vintage(src, target_width=4, palette_k=2, dither=False, scanlines=True)
    dev_faithful = render_fidelity_deviation((src, faithful.output_png))
    dev_aggressive = render_fidelity_deviation((src, aggressive.output_png))
    assert dev_faithful >= 0.0
    assert dev_faithful < dev_aggressive   # a faithful render is structurally closer to the source


def test_fidelity_identity_is_near_zero():
    # comparing a render to itself (as both source and output) is ~0 deviation
    src = _gradient_png()
    r = render_vintage(src, target_width=32, palette_k=16, scanlines=False)
    assert render_fidelity_deviation((r.output_png, r.output_png)) < 1e-9


from coherence_membrane.render_critic import render_signature, critique_render


def test_signature_is_stable_int():
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    s1 = render_signature(r.output_png)
    s2 = render_signature(r.output_png)
    assert isinstance(s1, int) and s1 == s2


def test_empty_corpus_is_unverifiable():
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    obs = critique_render(r, src, corpus=[], min_distance=5, tolerance=0.2)
    assert obs.data["verdict"] == "unverifiable"   # novelty UNVERIFIABLE -> composite UNVERIFIABLE


def test_derivative_render_is_refuted():
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    corpus = [render_signature(r.output_png)]          # the render is already in the corpus
    obs = critique_render(r, src, corpus=corpus, min_distance=5, tolerance=1.0)
    assert obs.data["verdict"] == "refuted"            # distance 0 < min_distance -> REFUTED, absorbing


def test_novel_and_fit_is_verified():
    src = _gradient_png()
    r = render_vintage(src, target_width=32, palette_k=16, scanlines=False)
    far_corpus = [0]                                   # a hash far from the render's signature
    obs = critique_render(r, src, corpus=far_corpus, min_distance=1, tolerance=10.0)
    assert obs.data["verdict"] == "verified"           # novel AND within a lax fidelity tolerance


def test_unfit_render_is_refuted():
    src = _gradient_png()
    r = render_vintage(src, target_width=4, palette_k=2, dither=False, scanlines=True)
    obs = critique_render(r, src, corpus=[0], min_distance=1, tolerance=0.001)
    assert obs.data["verdict"] == "refuted"            # novel but deviation > tiny tolerance


from coherence_membrane.memory import MemoryStore
from coherence_membrane.render_critic import remember_render, render_corpus


def test_remember_then_corpus_includes_signature():
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    store = MemoryStore()
    assert render_corpus(store) == []                       # empty to start
    obs = critique_render(r, src, corpus=[], min_distance=5, tolerance=1.0)
    remember_render(store, r, obs)
    corpus = render_corpus(store)
    assert render_signature(r.output_png) in corpus         # the remembered render is now in the corpus


def test_corpus_makes_a_repeat_derivative():
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    store = MemoryStore()
    remember_render(store, r, critique_render(r, src, corpus=[], min_distance=5, tolerance=1.0))
    # the SAME render, judged against the now-populated corpus, is derivative
    obs2 = critique_render(r, src, corpus=render_corpus(store), min_distance=5, tolerance=1.0)
    assert obs2.data["verdict"] == "refuted"


from coherence_membrane.render_critic import RenderStep, render_and_critique, run_render_critique


def test_stream_yields_four_steps_in_order():
    src = _gradient_png()
    store = MemoryStore()
    steps = list(render_and_critique(src, {"target_width": 16, "palette_k": 8, "scanlines": False},
                                     store, min_distance=5, tolerance=1.0))
    assert [s.name for s in steps] == ["render", "perceive", "critique", "remember"]
    assert all(isinstance(s, RenderStep) for s in steps)
    # each step carries a witnessed observation
    assert all(s.observation is not None for s in steps)
    # the critique step's verdict is present; remember grew the corpus
    critique = next(s for s in steps if s.name == "critique")
    assert critique.observation.data["verdict"] in ("verified", "refuted", "unverifiable")
    assert render_corpus(store)   # non-empty after remember


def test_run_returns_result_and_observation():
    src = _gradient_png()
    store = MemoryStore()
    result, obs = run_render_critique(src, {"target_width": 16, "palette_k": 8, "scanlines": False},
                                      store, min_distance=5, tolerance=1.0)
    assert result.output_png and obs.organ == "render-critic"


# M7 -- fail-closed + determinism

def test_undecodable_output_is_unverifiable_not_raised():
    src = _gradient_png()
    bad = _types.SimpleNamespace(output_png=b"not a png", output_sha256="deadbeef", palette_hex=())
    obs = critique_render(bad, src, corpus=[1, 2, 3], min_distance=5, tolerance=1.0)
    assert obs.data["verdict"] == "unverifiable"   # fail-closed; no PngDecodeError escapes


def test_deviation_is_deterministic():
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    assert render_fidelity_deviation((src, r.output_png)) == render_fidelity_deviation((src, r.output_png))


# M6 -- meaningful novelty bar + evidence names the dominating step

def test_novelty_bar_verified_just_below_real_distance():
    src = _gradient_png()
    r = render_vintage(src, target_width=32, palette_k=16, scanlines=False)
    sig = render_signature(r.output_png)
    far = sig ^ ((1 << 40) - 1)               # ~40 bits away
    d = _hamming(sig, far)
    # novelty_criterion uses >= so distance == min_distance IS novel (verified)
    obs = critique_render(r, src, corpus=[far], min_distance=d, tolerance=10.0)
    assert obs.data["verdict"] == "verified"  # distance d >= min_distance d -> novel, and fits


def test_novelty_bar_refuted_just_above_real_distance():
    src = _gradient_png()
    r = render_vintage(src, target_width=32, palette_k=16, scanlines=False)
    sig = render_signature(r.output_png)
    near = sig ^ 0b111                        # 3 bits away
    obs = critique_render(r, src, corpus=[near], min_distance=_hamming(sig, near) + 1, tolerance=10.0)
    assert obs.data["verdict"] == "refuted"   # distance < min_distance -> not novel


def test_evidence_identifies_dominating_step():
    # compose() produces evidence entries of the form [step_label, verdict_string]
    # e.g. ["step0:novelty-vs-corpus-v1", "verified"] and ["step1:structural-fitness-v1", "refuted"]
    # For a fitness-refuted case: step0 (novelty) is verified (novel), step1 (fitness) is refuted.
    # The evidence list must let us identify which step refuted the composition.
    src = _gradient_png()
    r = render_vintage(src, target_width=4, palette_k=2, dither=False, scanlines=True)
    # corpus=[0] + min_distance=1: sig far from 0, so novel (verified)
    # tolerance=0.001: tiny tolerance -> fitness refuted (aggressive render deviates a lot)
    obs = critique_render(r, src, corpus=[0], min_distance=1, tolerance=0.001)
    assert obs.data["verdict"] == "refuted"
    evidence = obs.data["evidence"]
    # evidence is list of 2-element lists: [step_label, verdict_string]
    # The fitness step label contains "structural-fitness" in its oracle name
    fitness_entries = [e for e in evidence if "structural-fitness" in e[0]]
    assert fitness_entries, "evidence must contain a structural-fitness entry"
    assert fitness_entries[0][1] == "refuted", "the structural-fitness step must be refuted"


# C1 regression -- the corpus is witnessed (survives save/load) and remember is idempotent

from coherence_membrane.provenance import VALID


def test_corpus_survives_save_load_round_trip(tmp_path):
    # C1: the novelty corpus lives INSIDE the witnessed MemoryRecord (a phash: tag),
    # so it must survive a save -> load cycle -- no side-channel state to lose.
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    store = MemoryStore()
    remember_render(store, r, critique_render(r, src, corpus=[], min_distance=5, tolerance=1.0))
    before = render_corpus(store)
    assert before == [render_signature(r.output_png)]
    p = tmp_path / "store.json"
    store.save(p)
    reloaded = MemoryStore.load(p)
    assert render_corpus(reloaded) == before              # corpus persisted across save/load
    assert reloaded.verify().verdict == VALID             # and the witnessed record verifies


def test_remember_same_render_twice_is_idempotent():
    # C1: re-remembering the same render (same output_sha256) must NOT raise a
    # duplicate-id ValueError, and must not double-count in the corpus.
    src = _gradient_png()
    r = render_vintage(src, target_width=16, palette_k=8, scanlines=False)
    store = MemoryStore()
    obs = critique_render(r, src, corpus=[], min_distance=5, tolerance=1.0)
    remember_render(store, r, obs)
    remember_render(store, r, obs)                         # second time: no crash
    assert render_corpus(store) == [render_signature(r.output_png)]   # exactly one entry
