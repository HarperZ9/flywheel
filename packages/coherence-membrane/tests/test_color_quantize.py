from __future__ import annotations

import pytest

from coherence_membrane.color import srgb_to_oklab
from coherence_membrane.color_field import ColorField
from coherence_membrane.color_quantize import (
    palette_to_hex,
    quantization_error,
    quantize,
)


def _cf(triples, unknown=None):
    n = len(triples)
    return ColorField(n, 1, tuple(triples), tuple(unknown or [False] * n))


def test_quantize_two_clusters():
    black = srgb_to_oklab((0.0, 0.0, 0.0))
    white = srgb_to_oklab((1.0, 1.0, 1.0))
    cf = _cf([black, black, white, white])
    indices, palette = quantize(cf, 2)
    assert len(palette) == 2
    # each cell maps to a palette entry; the two blacks share one, whites the other
    assert indices[0] == indices[1] and indices[2] == indices[3]
    assert indices[0] != indices[2]
    err = quantization_error(cf, indices, palette)
    assert err["max"] < 1e-9                      # exact: 2 clusters, 2 colors


def test_quantize_unknown_and_validation():
    black = srgb_to_oklab((0.0, 0.0, 0.0))
    cf = _cf([black, black], unknown=[False, True])
    indices, palette = quantize(cf, 2)
    assert indices[0] >= 0                          # known cell gets a real palette index
    assert indices[1] == -1                        # UNVERIFIABLE cell not assigned
    with pytest.raises(ValueError):
        quantize(cf, 0)


def test_quantize_k_exceeds_unique_colors():
    # k larger than the number of distinct colors -> palette is "up to k" (here 2)
    black = srgb_to_oklab((0.0, 0.0, 0.0))
    white = srgb_to_oklab((1.0, 1.0, 1.0))
    cf = _cf([black, white])
    indices, palette = quantize(cf, 5)
    assert len(palette) == 2                        # early-exit: no box left to split
    assert quantization_error(cf, indices, palette)["max"] < 1e-9


def test_palette_to_hex():
    white = srgb_to_oklab((1.0, 1.0, 1.0))
    assert palette_to_hex((white,))[0] == "#ffffff"
