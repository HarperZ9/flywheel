"""render_refine -- the refine primitive's first instance: grounded creative search.

Refine a vintage render until it is CORRECT (not good-enough): coordinate an OBJECTIVE axis
(fidelity to the source) with a SUBJECTIVE composite (palette harmony to a chosen ideal +
consistency with the taste of your kept corpus), balance them by cohesion, guard with novelty,
reflect on the weakest axis and re-iterate. Built on the general `refine` + the shipped
`render_critic`. Stdlib only.
"""
from __future__ import annotations

import statistics

from .color import srgb_to_oklab
from .phash import hamming
from .refine import GradedCriterion, refine
from .render_critic import render_fidelity_deviation, render_signature, render_corpus
from .retro import render_vintage

_HARMONY_L_TARGET = 0.6        # a healthy OKLab lightness spread
_START = {"target_width": 48, "palette_k": 8, "dither": True, "scanlines": False}


def _palette_oklab(palette_hex):
    out = []
    for h in palette_hex:
        s = h.lstrip("#")
        r, g, b = int(s[0:2], 16) / 255, int(s[2:4], 16) / 255, int(s[4:6], 16) / 255
        out.append(srgb_to_oklab((r, g, b)))
    return out


def palette_harmony_deviation(palette_hex) -> float:
    """0 = the chosen ideal: a healthy OKLab lightness contrast AND even spacing. inf if < 2
    colours (the harmony of a single swatch is undefined -> fail-closed)."""
    lab = _palette_oklab(palette_hex)
    if len(lab) < 2:
        return float("inf")
    ls = sorted(L for (L, _a, _b) in lab)
    contrast_deficit = max(0.0, _HARMONY_L_TARGET - (ls[-1] - ls[0]))
    gaps = [ls[i + 1] - ls[i] for i in range(len(ls) - 1)]
    unevenness = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
    return contrast_deficit + unevenness


def corpus_taste_deviation(signature: int, corpus: list) -> float:
    """0 = the render fits the FAMILY of your kept corpus (as related to it as its members are
    to each other); rises as it becomes an outlier. inf if < 2 kept renders (no taste-family
    yet) -> render_refine OMITS the axis rather than failing it."""
    if len(corpus) < 2:
        return float("inf")
    render_mean = statistics.mean(hamming(signature, c) for c in corpus)
    internal = statistics.mean(hamming(corpus[i], corpus[j])
                               for i in range(len(corpus)) for j in range(i + 1, len(corpus)))
    return max(0.0, render_mean - internal) / 64.0


def _novelty_guard(corpus, min_distance):
    def guard(result):
        if not corpus:
            return True                                   # nothing to be derivative of
        sig = render_signature(result.output_png)
        return min(hamming(sig, c) for c in corpus) >= min_distance
    return guard


def render_refine(source_png, store, *, target_margin=0.15, cohesion_bar=0.4, max_iter=8,
                  min_distance=5, fidelity_tol=20.0, harmony_tol=0.5, taste_tol=0.3, start=None):
    """Refine a render of `source_png` until CORRECT (or an honest budget). Coordinates fidelity
    (objective) + harmony + corpus-taste (subjective), cohesion-balanced, novelty-guarded.
    Does NOT remember; the caller keeps the winner (so every candidate is judged vs one corpus)."""
    corpus = render_corpus(store)
    start_params = dict(start) if start else dict(_START)

    def generate(state):
        return render_vintage(source_png, **(state if state else start_params))

    def adjust(reflection, state):
        s = dict(state) if state else dict(start_params)
        w = reflection.weakest
        if w == "fidelity":
            s["palette_k"] = min(s.get("palette_k", 8) + 4, 32)
            s["target_width"] = min(s.get("target_width", 48) + 8, 96)
        elif w == "harmony":
            s["palette_k"] = min(s.get("palette_k", 8) + 2, 32)
        elif w == "corpus_taste":
            s["scanlines"] = not s.get("scanlines", False)
            s["dither"] = not s.get("dither", True)
        else:
            s["palette_k"] = min(s.get("palette_k", 8) + 2, 32)
        return s

    graders = [
        GradedCriterion("fidelity", "objective",
                        lambda r: render_fidelity_deviation((source_png, r.output_png)), fidelity_tol),
        GradedCriterion("harmony", "subjective",
                        lambda r: palette_harmony_deviation(r.palette_hex), harmony_tol),
    ]
    if len(corpus) >= 2:
        graders.append(GradedCriterion(
            "corpus_taste", "subjective",
            lambda r: corpus_taste_deviation(render_signature(r.output_png), corpus), taste_tol))

    return refine(generate, graders, adjust, guard=_novelty_guard(corpus, min_distance),
                  target_margin=target_margin, cohesion_bar=cohesion_bar, max_iter=max_iter)
