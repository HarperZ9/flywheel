"""transpile.py — cross-modal transpilation: encode a signal into a compact
carrier a text model can read, conserving the CRITERION (not the bytes).

The thread (gui-tool grid labels; color/steganography/sound; the operator's own
public build of a vision transpiler that forcefeeds structured signal to
NON-vision models): a text-only model cannot consume raw pixels/audio, but it CAN
consume a transpiled representation. This module operationalizes the operator's
transpile-conservation principle: a lossy transform is faithful when it conserves
the task-relevant invariant, witnessed externally — not when it preserves bytes.

Two honest mechanisms here (labeled for what they are — no overclaim):

1. `grid_*` — QUANTIZATION / COMPRESSION with a conserved targeting criterion.
   A continuous coordinate -> a short recursive cell label ("B2.C1") -> the cell
   center. Genuinely fewer bits AND far more robust for a model to emit (a label
   it can name vs a 4-digit coordinate it hallucinates). Lossy: points in one
   finest cell collide — that collision IS the compression, characterized not
   hidden. Criterion conserved: the decoded point targets the true point within
   half a cell. This is the gui-tool technique, generalized + measured.

2. `color_*` — a lossless byte<->RGB CARRIER (a channel, NOT compression).
   Packs bytes into pixel channels for round-trip transport / covert provenance
   (steganography = capacity in a carrier, not size reduction). Honest framing:
   this re-represents data, it does not shrink it; pair with entropy coding for
   real compression. Included so the color/stego channel has a falsifier.
"""
from __future__ import annotations

import math
import string

_COLS_ALPHA = string.ascii_uppercase  # A..Z column codes


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else (hi if v > hi else v)


def grid_label(x: float, y: float, w: int, h: int, *,
               cols: int = 16, rows: int = 9, depth: int = 1) -> str:
    """Encode a pixel coordinate as a recursive grid label (e.g. 'B2' or
    'B2.C1'). `depth` levels of refinement; each level subdivides the chosen
    cell into cols x rows again. Lossy, criterion (targeting) conserving."""
    if cols < 1 or rows < 1 or cols > 26:
        raise ValueError("cols in 1..26, rows >= 1")
    x = _clamp(x, 0, w - 1e-9); y = _clamp(y, 0, h - 1e-9)
    x0, y0, cw, ch = 0.0, 0.0, float(w), float(h)
    parts: list[str] = []
    for _ in range(depth):
        col = min(cols - 1, int((x - x0) / (cw / cols)))
        row = min(rows - 1, int((y - y0) / (ch / rows)))
        parts.append(f"{_COLS_ALPHA[col]}{row + 1}")
        x0 = x0 + col * (cw / cols); y0 = y0 + row * (ch / rows)
        cw = cw / cols; ch = ch / rows
    return ".".join(parts)


def grid_center(label: str, w: int, h: int, *,
                cols: int = 16, rows: int = 9) -> tuple[float, float]:
    """Decode a grid label back to the pixel center of its (finest) cell."""
    x0, y0, cw, ch = 0.0, 0.0, float(w), float(h)
    for part in label.split("."):
        part = part.strip()
        col = _COLS_ALPHA.index(part[0].upper())
        row = int(part[1:]) - 1
        x0 = x0 + col * (cw / cols); y0 = y0 + row * (ch / rows)
        cw = cw / cols; ch = ch / rows
    return (x0 + cw / 2, y0 + ch / 2)


def grid_cell_size(w: int, h: int, *, cols: int = 16, rows: int = 9,
                   depth: int = 1) -> tuple[float, float]:
    return (w / cols ** depth, h / rows ** depth)


def label_bits(cols: int = 16, rows: int = 9, depth: int = 1) -> float:
    """Information cost of a label: depth * log2(cols*rows)."""
    return depth * math.log2(cols * rows)


def coord_bits(w: int, h: int) -> float:
    """Information cost of a raw integer pixel coordinate."""
    return math.log2(w) + math.log2(h)


def grid_metric_form(x: float, y: float, w: int, h: int, *,
                     cols: int = 16, rows: int = 9, depth: int = 2) -> str:
    """The reasoning-conserving form: the compact label PLUS its decoded metric
    coordinates, e.g. 'B2.D5 (x=108, y=105)'.

    MEASURED (2026-07-06, trained 14B, n=20): a bare grid_label conserves the
    LOCATE criterion (a reader can find the cell) but NOT the METRIC criterion —
    a model cannot compute distances/counts/regions over opaque labels. Opaque
    labels scored 0.20 mean on spatial-reasoning tasks vs 0.467 for raw coords;
    this pair form is the honest fix. The principle refines: conserve the
    criterion the DOWNSTREAM TASK needs — lookup wants the label, reasoning wants
    the metric. (Model ceiling ~0.47 even with coords: format is a major factor,
    not the whole story.)"""
    lab = grid_label(x, y, w, h, cols=cols, rows=rows, depth=depth)
    cx, cy = grid_center(lab, w, h, cols=cols, rows=rows)
    return f"{lab} (x={int(cx)}, y={int(cy)})"


def criterion_conserved(x: float, y: float, w: int, h: int, *,
                        cols: int = 16, rows: int = 9, depth: int = 1,
                        tol_frac: float = 0.5) -> bool:
    """The transpile-conservation check: does the round-trip land within
    `tol_frac` of a cell of the true point? Half a cell is the tightest a
    center-of-cell decode can guarantee."""
    cx, cy = grid_center(grid_label(x, y, w, h, cols=cols, rows=rows, depth=depth),
                         w, h, cols=cols, rows=rows)
    cw, ch = grid_cell_size(w, h, cols=cols, rows=rows, depth=depth)
    return abs(cx - x) <= tol_frac * cw + 1e-9 and abs(cy - y) <= tol_frac * ch + 1e-9


# -- color carrier (lossless channel, NOT compression) -----------------------

def color_encode(payload: bytes) -> list[tuple[int, int, int]]:
    """Pack bytes into RGB pixels (3 bytes/pixel), zero-padded. A carrier for
    round-trip transport / covert provenance — re-representation, not shrinkage."""
    pad = (-len(payload)) % 3
    b = payload + b"\x00" * pad
    return [(b[i], b[i + 1], b[i + 2]) for i in range(0, len(b), 3)]


def color_decode(pixels: list[tuple[int, int, int]], length: int) -> bytes:
    """Recover the original bytes (exact) given the true length."""
    out = bytearray()
    for px in pixels:
        out.extend(px)
    return bytes(out[:length])
