"""Live-state continuity -- always-on perception that costs ~nothing at rest.

The loop pulls frames from any CaptureSource and emits a stream of witnessed
events.  It is built to be native and continuous WITHOUT being over-consumptive:

  * Change-proportional work.  A cheap identity hash (sha256 of the frame bytes)
    runs every tick.  An unchanged frame is MATCH and stops there -- no decode, no
    perceptual hash.  Only a real change escalates to the full witnessed
    observation.  Cost tracks actual change, not wall-clock.
  * Self-throttling.  A ResourceBudget caps how much expensive work the loop may
    do; once spent, a changed frame is reported UNVERIFIABLE("throttled") -- the
    identity changed but the pixels were not perceived -- never silently dropped.
  * Inert and un-gated.  The loop only PERCEIVES.  It never gates an action and
    never grants authority; acting on what it perceives goes out through the
    write-gate separately (see membrane.py / scope.py).  Creative flow is
    untouched because nothing here blocks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Iterator

from .capture import CaptureSource, Frame
from .observation import Observation, sha256_hex
from .organ import Organ
from .organs.raw import RawFrameOrgan
from .organs.visual import VisualArtifactOrgan
from .phash import DRIFT, MATCH, UNVERIFIABLE, hamming, raw_channels


@dataclass(frozen=True)
class ResourceBudget:
    """Bounds that keep continuity from being over-consumptive.

    max_full_observations -- cap on expensive (decode+perceptual-hash) escalations
                            over the run; None = unbounded.
    min_interval_s        -- minimum seconds between processed frames (cadence
                            back-off); 0 = as fast as frames arrive.
    """

    max_full_observations: int | None = None
    min_interval_s: float = 0.0


@dataclass(frozen=True)
class ContinuityEvent:
    """One tick of perception."""

    frame_index: int
    source_id: str
    verdict: str  # MATCH / DRIFT / UNVERIFIABLE
    distance: int | None  # perceptual distance on a perceivable change, else None
    observation: Observation | None  # full witnessed obs only when escalated
    throttled: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_index": self.frame_index,
            "source_id": self.source_id,
            "verdict": self.verdict,
            "distance": self.distance,
            "observation": self.observation.to_dict() if self.observation else None,
            "throttled": self.throttled,
            "note": self.note,
        }


def run_continuity(
    source: CaptureSource,
    *,
    budget: ResourceBudget | None = None,
    organ: Organ | None = None,
    max_frames: int | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> Iterator[ContinuityEvent]:
    """Process frames from `source`, yielding a ContinuityEvent per frame.

    Default-deny on perception cost: identical frames cost one hash; only changed
    frames pay decode+perceptual-hash, and only until the budget is spent.
    """
    budget = budget or ResourceBudget()
    forced_organ = organ  # if set, used for every frame; else chosen per frame
    default_visual: VisualArtifactOrgan | None = None
    default_raw: RawFrameOrgan | None = None

    prev_sha: str | None = None
    prev_phash: int | None = None
    full_count = 0
    last_tick: float | None = None

    for n, frame in enumerate(source.frames()):
        if max_frames is not None and n >= max_frames:
            return

        # Cadence back-off: never busier than the budget allows.
        if budget.min_interval_s > 0 and last_tick is not None:
            elapsed = clock() - last_tick
            if elapsed < budget.min_interval_s:
                sleeper(budget.min_interval_s - elapsed)
        last_tick = clock()

        payload = frame.read()
        cur_sha = sha256_hex(payload)
        sid = frame.descriptor.source_id

        # --- cheap step: identity unchanged -> MATCH, no further work ----------
        if cur_sha == prev_sha:
            yield ContinuityEvent(n, sid, MATCH, 0, None, False, "unchanged (identity hash only)")
            continue

        # --- changed: escalate to a full observation, unless throttled --------
        if budget.max_full_observations is not None and full_count >= budget.max_full_observations:
            prev_sha = cur_sha
            prev_phash = None  # we did not perceive the pixels, so distance is unknown
            yield ContinuityEvent(
                n, sid, UNVERIFIABLE, None, None, True,
                "throttled: full-observation budget spent; identity changed but pixels not perceived",
            )
            continue

        # Choose the perceiver: an explicit organ wins; otherwise a raw-pixel
        # frame goes to RawFrameOrgan (no encode/decode) and everything else to
        # the PNG eye.
        if forced_organ is not None:
            perceiver: Organ = forced_organ
        elif raw_channels(frame.descriptor.pixel_format) is not None:
            default_raw = default_raw or RawFrameOrgan()
            perceiver = default_raw
        else:
            default_visual = default_visual or VisualArtifactOrgan()
            perceiver = default_visual
        # Hand the organ the bytes we ALREADY read (with the descriptor, so raw
        # geometry travels too).  Re-reading would be a second disk hit for
        # path-backed frames and could witness different bytes than cur_sha --
        # one canonical read keeps identity and perception consistent.
        observed = Frame(descriptor=frame.descriptor, payload=payload)
        obs = perceiver.observe(observed)[0]
        full_count += 1
        ph_hex = obs.data.get("perceptual_hash")
        cur_phash = int(ph_hex, 16) if ph_hex else None

        if prev_sha is None:
            note = "first frame; baseline established"
            distance = None
        elif prev_phash is None or cur_phash is None:
            note = "changed; pixels not perceptually hashable (identity drift only)"
            distance = None
        else:
            distance = hamming(prev_phash, cur_phash)
            note = f"changed; perceptual distance {distance}/64"

        yield ContinuityEvent(n, sid, DRIFT, distance, obs, False, note)
        prev_sha = cur_sha
        prev_phash = cur_phash
