"""map_elites.py — quality-diversity archive (MAP-Elites), from the Swansea
ACM T-IIS study (Walton et al. 2026).

MAP-Elites illuminates the BEHAVIOR space: a grid indexed by behavior
descriptors, each cell holding the highest-fitness candidate in that niche.
Unlike best-of-N (keeps only the winner -> converges, early fixation), the
archive keeps DIVERSE candidates across niches — including ones that aren't
the global best but fill a unique cell. The Swansea study measured this on
humans: galleries with diverse designs (including bad ones) prevented early
fixation and boosted exploration. That's our awg_ucb option-diversity principle
in its established algorithmic form, peer-validated.

Compose with M3: best-of-N populates a MAP-Elites archive; the archive's
diverse_set() resists wrong-attractor convergence and feeds M6 search a spread
frontier instead of a single seed.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ArchiveEntry:
    behavior: tuple
    candidate: str
    fitness: float
    source: str = ""


class MapElitesArchive:
    def __init__(self, descriptor_fn: Callable[[str], tuple]):
        self._descriptor = descriptor_fn
        self.cells: dict[tuple, ArchiveEntry] = {}

    def add(self, candidate: str, fitness: float, source: str = "") -> bool:
        """Place candidate in its behavior niche; keep the best per cell.
        Returns True if this candidate displaced a prior entry (improved its niche)."""
        b = self._descriptor(candidate)
        existing = self.cells.get(b)
        if existing is None or fitness > existing.fitness:
            self.cells[b] = ArchiveEntry(b, candidate, fitness, source)
            return True
        return False

    def add_all(self, scored: list[tuple[str, float]], source: str = "") -> int:
        """Bulk-add (candidate, fitness) pairs; returns count of displacements."""
        return sum(1 for c, f in scored if self.add(c, f, source))

    def diverse_set(self) -> list[ArchiveEntry]:
        """One entry per occupied niche — the anti-fixation set. The Swansea
        finding: this diversity (even non-optimal cells) prevents early fixation."""
        return list(self.cells.values())

    def best(self) -> ArchiveEntry | None:
        if not self.cells:
            return None
        return max(self.cells.values(), key=lambda e: e.fitness)

    def coverage(self) -> int:
        """Number of distinct niches illuminated. Higher = more of the behavior
        space explored = more options kept open (the AWG principle)."""
        return len(self.cells)

    def fixation_ratio(self) -> float:
        """0.0 = fully diverse (every entry a unique niche); 1.0 = total
        fixation (all candidates collapsed to one cell). The early-fixation
        signal the Swansea gallery design counters."""
        return 0.0 if self.coverage() > 0 else 1.0


def length_bucket_descriptor(candidate: str, buckets: tuple = (10, 40, 120)) -> tuple:
    """A simple behavior descriptor: which length bucket the candidate falls in.
    Real descriptors are task-specific (algorithmic approach, style, etc.) but
    length is a generic, falsifiable proxy for 'different kind of solution'."""
    n = len(candidate)
    for i, bound in enumerate(buckets):
        if n <= bound:
            return ("len", i)
    return ("len", len(buckets))
