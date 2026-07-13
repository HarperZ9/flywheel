"""map_elites falsifier — quality-diversity prevents early fixation.

The Swansea finding operationalized: a MAP-Elites archive keeps DIVERSE
candidates (one per niche) rather than collapsing to the single global best.
Diverse candidates fill multiple niches (high coverage); the archive keeps the
best PER CELL, so a strong candidate in niche A doesn't evict a weaker but
unique candidate in niche B. This is the anti-fixation mechanism.
"""
import pytest

from harness.map_elites import (MapElitesArchive, ArchiveEntry,
                                length_bucket_descriptor)


def test_diverse_candidates_fill_multiple_niches():
    arch = MapElitesArchive(length_bucket_descriptor)
    arch.add_all([("short", 0.5), ("a medium-length solution here", 0.7),
                  ("x" * 200, 0.4)])
    assert arch.coverage() == 3, "each distinct-length candidate fills its own niche"


def test_best_per_niche_not_global_best():
    """A strong candidate in niche A must not evict a weaker candidate in niche B."""
    arch = MapElitesArchive(length_bucket_descriptor)
    arch.add("short", 0.9)            # niche 0, strong
    arch.add("a medium-length one", 0.6)  # niche 1, weaker
    assert arch.coverage() == 2
    entries = {e.behavior: e for e in arch.diverse_set()}
    assert entries[("len", 0)].fitness == 0.9
    assert entries[("len", 1)].fitness == 0.6


def test_same_niche_keeps_highest_fitness():
    arch = MapElitesArchive(length_bucket_descriptor)
    arch.add("short", 0.3)
    displaced = arch.add("tiny", 0.5)  # same niche (both <=10)
    assert displaced
    assert arch.coverage() == 1
    assert arch.best().fitness == 0.5


def test_low_fitness_unique_niche_is_kept():
    """The anti-fixation core: a low-fitness candidate in a UNIQUE niche is kept,
    not evicted by a high-fitness candidate elsewhere. Swansea: diversity
    including 'bad' candidates prevents fixation."""
    arch = MapElitesArchive(length_bucket_descriptor)
    arch.add("x" * 200, 0.1)  # unique long niche, low fitness
    arch.add("short", 0.95)   # different niche, high fitness
    assert arch.coverage() == 2
    diverse = arch.diverse_set()
    assert any(e.fitness == 0.1 for e in diverse), "low-fitness unique niche must survive"


def test_best_returns_global_max():
    arch = MapElitesArchive(length_bucket_descriptor)
    arch.add_all([("short", 0.5), ("a medium one", 0.8), ("x" * 200, 0.6)])
    assert arch.best().fitness == 0.8


def test_empty_archive_safe():
    arch = MapElitesArchive(length_bucket_descriptor)
    assert arch.best() is None
    assert arch.coverage() == 0
    assert arch.diverse_set() == []
