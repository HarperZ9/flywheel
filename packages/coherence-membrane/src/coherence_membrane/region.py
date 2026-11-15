"""Region/element perception -- WHERE did it change, not just whether.

A whole-image perceptual hash answers "did the frame change". A region grid
answers "which part". The image is divided into a rows x cols grid; each tile gets
its own dHash, and a per-tile Hamming distance localises a change to the tiles
that actually moved -- so a model can ground "the button in the top-right redrew"
rather than only "the screen changed".

Same coarse-fingerprint honesty as the whole-image dHash: a tile distance is
advisory evidence that "this region changed", not an understanding of what
changed. The verdict is the same closed lattice (MATCH / DRIFT / UNVERIFIABLE),
fail-closed: a missing or mismatched grid is UNVERIFIABLE, never a silent MATCH.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .phash import DRIFT, MATCH, UNVERIFIABLE, _dhash_bits, _to_grayscale, hamming
from .pngview import DecodedImage


def tile_hashes(img: DecodedImage, rows: int, cols: int) -> list[int]:
    """dHash of each tile in a rows x cols grid, row-major (top-left first).

    Each tile is hashed independently with the same dHash used for the whole
    image, so a change confined to one tile moves only that tile's hash.
    """
    if rows <= 0 or cols <= 0:
        raise ValueError("rows and cols must be positive")
    w, h = img.width, img.height
    if w <= 0 or h <= 0:
        raise ValueError("non-positive image dimensions")
    gray = _to_grayscale(img)
    hashes: list[int] = []
    for r in range(rows):
        y0 = (r * h) // rows
        y1 = max(y0 + 1, ((r + 1) * h) // rows)
        for c in range(cols):
            x0 = (c * w) // cols
            x1 = max(x0 + 1, ((c + 1) * w) // cols)
            tile = [gray[y * w + x] for y in range(y0, y1) for x in range(x0, x1)]
            hashes.append(_dhash_bits(tile, x1 - x0, y1 - y0))
    return hashes


def _as_int(value: Any) -> int:
    return value if isinstance(value, int) else int(value, 16)


@dataclass(frozen=True)
class RegionDriftReport:
    """Where an artifact changed, region by region.

    verdict         -- MATCH / DRIFT / UNVERIFIABLE (the closed lattice).
    rows, cols      -- the grid the report is over.
    distances       -- per-region Hamming distance (row-major), [] if UNVERIFIABLE.
    changed_regions -- indices whose distance exceeds the threshold.
    max_distance    -- the largest per-region distance, or None if UNVERIFIABLE.
    reason          -- human-readable explanation.
    """

    verdict: str
    rows: int
    cols: int
    distances: list[int]
    changed_regions: list[int]
    max_distance: int | None
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "rows": self.rows,
            "cols": self.cols,
            "distances": list(self.distances),
            "changed_regions": list(self.changed_regions),
            "max_distance": self.max_distance,
            "reason": self.reason,
        }


def compare_region_drift(
    baseline_hashes: list | None,
    current_hashes: list | None,
    rows: int,
    cols: int,
    *,
    threshold: int = 0,
) -> RegionDriftReport:
    """Compare two region-hash grids, fail-closed.

    Each side is a row-major list of per-tile dHashes (ints or hex strings). A
    region counts as changed when its Hamming distance exceeds `threshold`
    (default 0 = any difference). A missing side or a grid whose length is not
    rows*cols is UNVERIFIABLE -- never a silent MATCH.
    """
    n = rows * cols
    if not baseline_hashes or not current_hashes:
        return RegionDriftReport(UNVERIFIABLE, rows, cols, [], [], None,
                                 "a region grid is missing")
    if len(baseline_hashes) != n or len(current_hashes) != n:
        return RegionDriftReport(
            UNVERIFIABLE, rows, cols, [], [], None,
            f"region grid size mismatch (expected {n}, got "
            f"{len(baseline_hashes)} vs {len(current_hashes)})",
        )
    try:
        distances = [hamming(_as_int(b), _as_int(c))
                     for b, c in zip(baseline_hashes, current_hashes)]
    except (TypeError, ValueError):
        return RegionDriftReport(UNVERIFIABLE, rows, cols, [], [], None,
                                 "a region hash is not a valid integer/hex")
    changed = [i for i, d in enumerate(distances) if d > threshold]
    max_d = max(distances)
    if not changed:
        return RegionDriftReport(MATCH, rows, cols, distances, [], max_d,
                                 "all regions match")
    return RegionDriftReport(
        DRIFT, rows, cols, distances, changed, max_d,
        f"{len(changed)}/{n} region(s) changed (max distance {max_d}/64)",
    )
