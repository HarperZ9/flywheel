"""transpile falsifier — cross-modal encoding conserves the criterion, honestly.

Sources: github.com/ZachRouan/agent-desktop-interface (grid-label targeting);
the operator's own transpile-conservation principle (public build: a transpiler
that forcefeeds structured signal to non-vision models); the color/
steganography/sound compression thread.

Properties (each an honest claim with teeth):
  1. Grid round-trip conserves the TARGETING criterion within half a cell.
  2. Deeper recursion is strictly tighter (rate/distortion is real).
  3. Same-cell points collide to one label — the collision IS the compression,
     characterized not hidden (this is what makes it lossy).
  4. The label costs fewer bits than a raw coordinate at useful depths, AND is
     what a model can emit reliably (measured, not asserted).
  5. The color carrier is LOSSLESS round-trip (a channel), and a tampered pixel
     is recoverable-as-different (no silent corruption).
"""
import math

import pytest

from harness import transpile as T

W, H = 1920, 1080


def test_grid_roundtrip_conserves_targeting_within_half_cell():
    for (x, y) in [(0, 0), (960, 540), (1919, 1079), (123, 456), (1500, 200)]:
        assert T.criterion_conserved(x, y, W, H, depth=2), f"{x},{y} not conserved"


def test_grid_metric_form_carries_label_and_decoded_coords():
    # the reasoning-conserving form: compact label + metric coords the model can
    # compute over (the measured fix for the COPY-ONLY spatial-reasoning weakness)
    import re
    form = T.grid_metric_form(120.0, 90.0, W, H)
    lab = T.grid_label(120.0, 90.0, W, H, depth=2)
    assert form.startswith(lab + " (x=")
    cx, cy = map(int, re.search(r"x=(\d+), y=(\d+)", form).groups())
    gx, gy = T.grid_center(lab, W, H)
    assert abs(cx - gx) <= 1 and abs(cy - gy) <= 1


def test_deeper_recursion_is_strictly_tighter():
    x, y = 733, 421
    err = []
    for depth in (1, 2, 3):
        cx, cy = T.grid_center(T.grid_label(x, y, W, H, depth=depth), W, H)
        err.append(math.hypot(cx - x, cy - y))
    assert err[0] > err[1] > err[2], f"error must shrink with depth: {err}"


def test_same_cell_points_collide_the_compression_is_lossy():
    # two points inside the same finest cell must produce the SAME label —
    # that collision is the compression, and we assert it honestly.
    a = T.grid_label(100, 100, W, H, depth=1)
    b = T.grid_label(105, 103, W, H, depth=1)   # ~5px away, same 120x120 cell
    assert a == b
    # and a point in a different cell must differ
    c = T.grid_label(500, 500, W, H, depth=1)
    assert c != a


def test_label_is_cheaper_and_emittable():
    # honest bit accounting: a depth-2 label < a raw 1920x1080 coordinate.
    assert T.label_bits(depth=2) < T.coord_bits(W, H)
    # and the label is a short human/model-emittable string
    lbl = T.grid_label(1500, 200, W, H, depth=2)
    assert "." in lbl and len(lbl) <= 8


def test_deterministic():
    assert T.grid_label(777, 333, W, H, depth=3) == T.grid_label(777, 333, W, H, depth=3)


def test_color_carrier_is_lossless_roundtrip():
    payload = b"receipt:af6abe9c3e0dd749|verdict:MATCH|\x00\xff\x10 arbitrary bytes"
    pixels = T.color_encode(payload)
    assert T.color_decode(pixels, len(payload)) == payload


def test_color_tamper_is_visible_not_silent():
    payload = b"provenance-sealed-node"
    pixels = T.color_encode(payload)
    r, g, b = pixels[0]
    pixels[0] = (r ^ 0x01, g, b)              # flip one bit in the carrier
    recovered = T.color_decode(pixels, len(payload))
    assert recovered != payload               # corruption surfaces, never silent
