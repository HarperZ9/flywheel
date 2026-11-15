"""Temporal perception -- drift episodes over the continuity stream.

The continuity loop emits a flat sequence of per-tick verdicts (MATCH / DRIFT /
UNVERIFIABLE). That tells you what happened at each instant, not the *shape* of
change over time. EventTrace reads the stream and structures it: it finds drift
EPISODES (a change began, ran, and settled), how far each drifted (peak
distance), when each settled, and the longest DWELL (run of unchanged ticks).

So a model can ground "the canvas changed at t=3, peaked at distance 18, and
settled by t=7" rather than only "tick 5 was DRIFT". This is inert analysis over
already-witnessed verdicts -- it perceives nothing new and grants no authority;
it only re-shapes the witnessed stream into episodes, fail-closed on the same
closed lattice.

Episode model (stated, not implied): an episode is a maximal run that contains at
least one DRIFT, opened by the first DRIFT and closed (SETTLED) by the next MATCH.
UNVERIFIABLE ticks inside an open episode keep it open (the state is uncertain,
not confirmed-settled); a run of only UNVERIFIABLE is NOT an episode (no confirmed
change). A dwell is a run of consecutive MATCH ticks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .phash import DRIFT, MATCH, UNVERIFIABLE


def _verdict_distance(item: Any) -> tuple[str, int | None]:
    """Extract (verdict, distance) from a ContinuityEvent, a dict, or a bare
    verdict string -- so the trace works over any of the stream's forms."""
    if isinstance(item, str):
        return item, None
    verdict = getattr(item, "verdict", None)
    if verdict is not None:
        return verdict, getattr(item, "distance", None)
    if isinstance(item, dict):
        return item.get("verdict"), item.get("distance")
    raise TypeError(f"cannot read a verdict from {type(item).__name__}")


@dataclass(frozen=True)
class DriftEpisode:
    """One contiguous drift episode in the stream."""

    start_index: int       # index of the first DRIFT tick
    end_index: int         # index of the last DRIFT tick
    length: int            # span from first to last DRIFT, inclusive
    peak_distance: int | None  # largest perceptual distance seen, or None if unquantified
    settled_at: int | None     # index of the MATCH that closed it, or None if still open at stream end

    @property
    def settled(self) -> bool:
        return self.settled_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_index": self.start_index,
            "end_index": self.end_index,
            "length": self.length,
            "peak_distance": self.peak_distance,
            "settled_at": self.settled_at,
            "settled": self.settled,
        }


@dataclass(frozen=True)
class EventTrace:
    """Structured temporal view of a continuity stream."""

    episodes: list[DriftEpisode] = field(default_factory=list)
    total_events: int = 0
    match_events: int = 0
    drift_events: int = 0
    unverifiable_events: int = 0
    longest_dwell: int = 0

    @property
    def unsettled_episodes(self) -> list[DriftEpisode]:
        return [e for e in self.episodes if not e.settled]

    def to_dict(self) -> dict[str, Any]:
        return {
            "episodes": [e.to_dict() for e in self.episodes],
            "total_events": self.total_events,
            "match_events": self.match_events,
            "drift_events": self.drift_events,
            "unverifiable_events": self.unverifiable_events,
            "longest_dwell": self.longest_dwell,
        }


def trace_events(events: Iterable[Any]) -> EventTrace:
    """Structure a continuity stream into drift episodes + dwell statistics.

    `events` is any iterable of ContinuityEvents, dicts with verdict/distance, or
    bare verdict strings. Inert: it reads verdicts and reports; it changes nothing.
    """
    episodes: list[DriftEpisode] = []
    total = match = drift = unv = 0
    longest_dwell = cur_dwell = 0

    open_start: int | None = None      # first DRIFT index of the open episode
    last_drift: int | None = None      # most recent DRIFT index in the open episode
    peak: int | None = None            # peak distance in the open episode

    def close(settled_at: int | None) -> None:
        nonlocal open_start, last_drift, peak
        episodes.append(DriftEpisode(
            start_index=open_start, end_index=last_drift,
            length=last_drift - open_start + 1, peak_distance=peak, settled_at=settled_at,
        ))
        open_start = last_drift = peak = None

    for i, item in enumerate(events):
        verdict, distance = _verdict_distance(item)
        total += 1
        if verdict == MATCH:
            match += 1
            cur_dwell += 1
            longest_dwell = max(longest_dwell, cur_dwell)
            if open_start is not None:
                close(settled_at=i)
        elif verdict == DRIFT:
            drift += 1
            cur_dwell = 0
            if open_start is None:
                open_start = i
            last_drift = i
            if distance is not None:
                peak = distance if peak is None else max(peak, distance)
        elif verdict == UNVERIFIABLE:
            unv += 1
            cur_dwell = 0
            # keeps an open episode open (uncertain), never opens one alone
        else:
            raise ValueError(f"unknown verdict {verdict!r} (expected MATCH/DRIFT/UNVERIFIABLE)")

    if open_start is not None:
        close(settled_at=None)  # stream ended mid-episode

    return EventTrace(
        episodes=episodes, total_events=total, match_events=match,
        drift_events=drift, unverifiable_events=unv, longest_dwell=longest_dwell,
    )
