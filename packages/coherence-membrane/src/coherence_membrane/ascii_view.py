"""ASCII perception -- a compact, model-readable view of a frame.

A perceptual hash answers "did it change" in 64 opaque bits. An ASCII view answers
"roughly what is on screen" in a tiny grid of glyphs a text model can read in
context with no image decode -- and a human can eyeball. It is the same move as the
dHash (downscale luma to a coarse projection), but the projection is legible text
instead of bits, which is exactly what makes it cheap to store in a baseline /
receipt and cheap to ground on.

Honesty: an ASCII view is a coarse LUMINANCE projection mapped to a glyph ramp --
advisory evidence of "this region got lighter/darker", NOT a semantic
understanding of the image and NOT OCR. The drift between two views is a literal
per-cell glyph difference, fail-closed on the same closed lattice (MATCH / DRIFT /
UNVERIFIABLE) -- a grid-size mismatch is UNVERIFIABLE, never a silent MATCH.

Stdlib only; it reuses the phash grayscale + box-downscale so the projection is
deterministic and re-derivable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .phash import DRIFT, MATCH, UNVERIFIABLE, _downscale, _to_grayscale
from .pngview import DecodedImage

# Dark -> light glyph ramp (10 levels). Index = luma * (len-1) // 255.
ASCII_RAMP = " .:-=+*#%@"


def ascii_view(img: DecodedImage, cols: int = 64, rows: int | None = None) -> list[str]:
    """Render a decoded image to a rows x cols grid of glyphs (row-major lines).

    `rows` defaults to a value that preserves aspect under a ~2:1 character cell
    (terminal glyphs are about twice as tall as wide). Deterministic and
    re-derivable: it box-downscales the luma and maps each cell through the ramp.
    """
    if cols <= 0:
        raise ValueError("cols must be positive")
    if img.width <= 0 or img.height <= 0:
        raise ValueError("non-positive image dimensions")
    if rows is None:
        rows = max(1, round(cols * img.height / (img.width * 2)))
    if rows <= 0:
        raise ValueError("rows must be positive")

    gray = _to_grayscale(img)
    small = _downscale(gray, img.width, img.height, cols, rows)
    last = len(ASCII_RAMP) - 1
    lines: list[str] = []
    for r in range(rows):
        base = r * cols
        lines.append("".join(ASCII_RAMP[(small[base + c] * last) // 255] for c in range(cols)))
    return lines


def ascii_text(view: list[str]) -> str:
    """The view as a single newline-joined string (the witnessed artifact form)."""
    return "\n".join(view)


@dataclass(frozen=True)
class AsciiDriftReport:
    verdict: str            # MATCH / DRIFT / UNVERIFIABLE
    changed_cells: int | None
    total_cells: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "changed_cells": self.changed_cells,
                "total_cells": self.total_cells, "reason": self.reason}


def compare_ascii_drift(baseline: list[str] | None, current: list[str] | None) -> AsciiDriftReport:
    """Per-cell glyph difference between two ASCII views, fail-closed.

    A missing view, a differing row count, or a differing row width is
    UNVERIFIABLE (the grids are not comparable) -- never a silent MATCH.
    """
    if not baseline or not current or len(baseline) != len(current):
        return AsciiDriftReport(UNVERIFIABLE, None, None, "a view is missing or row counts differ")
    if any(len(a) != len(b) for a, b in zip(baseline, current)):
        return AsciiDriftReport(UNVERIFIABLE, None, None, "view row widths differ")
    total = sum(len(row) for row in baseline)
    if total == 0:
        return AsciiDriftReport(UNVERIFIABLE, None, None, "no cells to compare")
    changed = sum(1 for a, b in zip(baseline, current) for ca, cb in zip(a, b) if ca != cb)
    if changed == 0:
        return AsciiDriftReport(MATCH, 0, total, "every cell matches")
    return AsciiDriftReport(DRIFT, changed, total,
                            f"{changed}/{total} cells changed")
