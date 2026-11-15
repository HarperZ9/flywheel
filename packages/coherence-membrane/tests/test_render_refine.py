from coherence_membrane.render_refine import (
    palette_harmony_deviation, corpus_taste_deviation, render_refine,
)
from coherence_membrane.memory import MemoryStore
from coherence_membrane.pngencode import encode_png


def _gradient(w=24, h=24):
    rows = bytearray()
    for y in range(h):
        for x in range(w):
            rows.extend((int(255 * x / (w - 1)), int(255 * y / (h - 1)), 128))
    return encode_png(w, h, bytes(rows), channels=3)


def test_palette_harmony_single_colour_is_inf():
    assert palette_harmony_deviation(["#808080"]) == float("inf")


def test_palette_harmony_even_contrast_beats_low_contrast():
    even = palette_harmony_deviation(["#000000", "#555555", "#aaaaaa", "#ffffff"])
    low = palette_harmony_deviation(["#707070", "#808080"])    # tiny lightness range
    assert even >= 0.0
    assert even < low                                          # wide + even beats flat


def test_corpus_taste_needs_a_family():
    assert corpus_taste_deviation(123, []) == float("inf")
    assert corpus_taste_deviation(123, [5]) == float("inf")
    assert corpus_taste_deviation(5, [5, 7]) >= 0.0            # finite with a family of >= 2


def test_render_refine_reaches_correct_lenient():
    out = render_refine(_gradient(), MemoryStore(), target_margin=0.001, cohesion_bar=0.001,
                        max_iter=3, fidelity_tol=1000.0, harmony_tol=1000.0)
    assert out.status == "correct"
    assert out.candidate.output_png                            # a real render result
    assert len(out.trajectory) >= 1


def test_render_refine_honest_short_strict():
    out = render_refine(_gradient(), MemoryStore(), target_margin=0.999, cohesion_bar=0.999,
                        max_iter=3, fidelity_tol=0.01, harmony_tol=0.01)
    assert out.status == "short"                               # impossible bars -> honest short
    assert out.short_axis in ("fidelity", "harmony")
    assert all(s.correct is False for s in out.trajectory)     # never a false 'correct'
    assert len(out.trajectory) == 3                            # spent the whole budget
