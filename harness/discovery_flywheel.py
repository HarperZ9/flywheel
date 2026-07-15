"""discovery_flywheel.py -- sense the shifting field, gate what we adopt, flag
when to change course. The self-growth loop, kept honest.

The field moves fast; the operator wants the system to notice new discoveries and
adapt. This composes the pieces that already exist rather than inventing an
"oracle" that senses discoveries -- because there is no ground-truth oracle for
"is this a real discovery worth adopting"; that is a JUDGEMENT, and putting a
learned judge on the accept path is exactly the C2 violation the engine forbids.

The honest decomposition:
  - SENSE (the edge, ML on the PROPOSE side): a frontier sweep (LLM agents + live
    web) proposes discovery candidates. Off the accept path. Lives upstream; this
    module consumes its OUTPUT, it does not fetch.
  - GATE (native, C2-clean): a discovery enters the ADOPTABLE lane only if it
    carries a runnable FALSIFIER. No falsifier -> demoted to inspiration, full
    stop. That rule is enforced here at intake, before evolve.py's own gating
    (which further forces every code/capability change into the never-auto-apply
    lane). The falsifier -- a real oracle that fires or does not -- is the only
    thing that lets a change land. The matmul oracle shipped this way; J-lens
    stayed a wedge because its falsifier needs a GPU.
  - DRIFT (native, transition-fired): watch the stream of ACTIONABLE discoveries
    over time; when a domain outside the current course accumulates enough
    adoptable threads, RECOMMEND a course change -- once, on the transition, not
    every observation. It recommends; it never re-prioritizes the roadmap itself.

No learned model decides adoption; no code is auto-applied; no course auto-changes.
What compounds is the FLOOR: each turn that lands a falsifier-gated change raises
the baseline the next turn starts from (evolve.py's discipline), and the drift
signal keeps the loop pointed at where the field actually moved.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .evolve import meta_cycle

ACTIONABLE = "ACTIONABLE"
INSPIRATION = "INSPIRATION"
NOISE = "NOISE"


@dataclass
class Discovery:
    concept: str
    rank: str                       # ACTIONABLE | INSPIRATION | NOISE
    domain: str = ""                # which part of the system it threads into
    application: str = ""           # the concrete proposed change
    falsifier: str = ""             # the runnable test that would prove it worthless


def normalize_sweep(sweep: dict) -> list[Discovery]:
    """Accept a frontier-sweep report and return normalized discoveries. Tolerant
    of shape: reads a top-level `ranked` list of {concept, rank, where/domain,
    application, falsifier}. Unknown ranks are treated as NOISE (fail-closed)."""
    out: list[Discovery] = []
    for r in (sweep.get("ranked") or sweep.get("discoveries") or []):
        if not isinstance(r, dict):
            continue
        rank = str(r.get("rank", NOISE)).upper()
        if rank not in (ACTIONABLE, INSPIRATION, NOISE):
            rank = NOISE
        out.append(Discovery(
            concept=str(r.get("concept", "")),
            rank=rank,
            domain=str(r.get("domain") or r.get("where") or ""),
            application=str(r.get("application", "")),
            falsifier=str(r.get("falsifier", "")),
        ))
    return out


def frontier_feed(discoveries: list[Discovery]) -> tuple[dict, list[dict]]:
    """Bridge discoveries into evolve.py's research_feed shape, ENFORCING the
    falsifier gate at intake: an ACTIONABLE discovery with no falsifier is NOT
    adoptable and is demoted to inspiration. Returns (research_feed, demotions)
    where demotions records every gate action for the receipt."""
    actionable, inspiration, demotions = [], [], []
    for d in discoveries:
        if d.rank == ACTIONABLE and d.falsifier.strip():
            # the falsifier is model-authored text from the sweep: STATED,
            # not executed here. Naming that keeps the receipt from reading
            # a stated intention as a fired check; running it is the
            # downstream admission step.
            actionable.append({"title": d.concept,
                               "suggested_extension": d.application or d.concept,
                               "falsifier": d.falsifier,
                               "falsifier_status": "stated, not yet run",
                               "domain": d.domain})
        elif d.rank == ACTIONABLE:            # actionable but no falsifier -> demote
            inspiration.append({"title": d.concept})
            demotions.append({"concept": d.concept,
                              "reason": "ranked ACTIONABLE but carries no falsifier -- "
                                        "not adoptable; demoted to inspiration"})
        elif d.rank == INSPIRATION:
            inspiration.append({"title": d.concept})
        # NOISE is dropped (recorded in the cycle receipt's noise count)
    return {"actionable_threads": actionable,
            "inspiration_threads": inspiration}, demotions


@dataclass
class CourseDriftDetector:
    """Transition-fired course-drift signal. Holds the current course (priority
    domains) and fires a recommendation ONLY when it changes -- a domain outside
    the course crossing the adoptable-thread threshold. Steady state never
    re-fires (the knowledge_monitor discipline)."""
    course: set = field(default_factory=set)
    drift_threshold: int = 2         # adoptable threads in a new domain to flag it
    last_recommendation: str = ""
    observations: int = 0

    def observe(self, discoveries: list[Discovery]) -> dict:
        self.observations += 1
        # count ADOPTABLE (actionable + falsifier) threads per domain
        counts: dict[str, int] = {}
        for d in discoveries:
            if d.rank == ACTIONABLE and d.falsifier.strip() and d.domain:
                counts[d.domain] = counts.get(d.domain, 0) + 1
        emerging = sorted(dom for dom, c in counts.items()
                          if dom not in self.course and c >= self.drift_threshold)
        if emerging:
            recommendation = ("field shifting -- recommend adding to course: "
                              + ", ".join(emerging))
        else:
            recommendation = "course holds"
        # Fire only on a NEW active-drift recommendation: "course holds" is not an
        # alert, and an unchanged drift recommendation is steady state (no re-fire).
        fired = bool(emerging) and recommendation != self.last_recommendation
        self.last_recommendation = recommendation
        return {
            "observation": self.observations,
            "current_course": sorted(self.course),
            "domain_counts": counts,
            "emerging_domains": emerging,
            "recommendation": recommendation,
            "fired": fired,                    # transition only
            "note": "recommendation only, counted over STATED falsifiers "
                    "(none executed here) -- the operator/roadmap changes "
                    "course, not this",
        }

    def adopt_course_change(self, domains: list[str]) -> None:
        """Explicit, operator-invoked course update. Never called automatically."""
        self.course |= set(domains)


def discovery_cycle(sweep: dict, detector: CourseDriftDetector) -> dict:
    """One turn of the self-growth flywheel: normalize the sweep, gate discoveries
    into the evolve meta-loop (falsifier-enforced), and check for course drift.
    Emits a receipt binding what was sensed -> what is adoptable -> what needs
    gated admission -> whether the field drifted. Adopts nothing automatically."""
    discoveries = normalize_sweep(sweep)
    feed, demotions = frontier_feed(discoveries)
    cycle = meta_cycle(feed, efficiency_feed={})
    drift = detector.observe(discoveries)
    n_noise = sum(1 for d in discoveries if d.rank == NOISE)
    # A field DISCOVERY is a capability/technique to ADOPT, never a runtime config
    # knob -- so every falsifiable discovery needs ADMISSION (a human + a fired
    # falsifier), never auto-apply. evolve's auto-config lane is for INTERNAL
    # self-tuning from telemetry; a keyword match there ("escalation", "budget")
    # must not route an external discovery into it. So both evolve lanes fold into
    # one needs-admission list here. (Found by dogfooding this loop on real input.)
    needs_admission = cycle["auto_apply"] + cycle["gated"]
    return {
        "schema": "flywheel.discovery-cycle/v1",
        "sensed": len(discoveries),
        "needs_admission": needs_admission,        # every falsifiable discovery -> admission gate
        "inspiration": cycle["surface_only"],
        "demoted_no_falsifier": demotions,         # ACTIONABLE-but-unfalsifiable, blocked
        "noise_dropped": n_noise,
        "course_drift": drift,
        "invariant": "no learned judge on the accept path; NO external discovery "
                     "auto-applied (all need admission); no course auto-changed; a "
                     "fired falsifier is the only thing that lands a change",
    }
