"""The agent loop -- make -> look -> compare -> adjust, grounded and gated.

A state-blind model reasons about whether its action worked; it does not check.
This closes that loop: the agent MAKES (produces an artifact, takes an action),
the membrane LOOKS (perceives the result) and COMPARES it to what was intended,
and recommends ADJUST or CONVERGED. The membrane never makes and never actuates --
it is inert; the agent iterates and the operator/runtime commits.

Two comparisons, deliberately separate, so nothing is laundered:

  * ITERATION (look / iterate): "is the result close enough to my intended goal?"
    Compared to a `Goal` (a reference + an operator-set tolerance). This is purely
    advisory iteration control -- it is NEVER gated, and the tolerance NEVER
    touches the write-gate.
  * COMMIT (commit): "may I now take the consequential action on this result?"
    Drift is measured against the operator-AUTHORIZED baseline via the baseline
    ladder (byte identity -> canonical -> perceptual), and routed through
    proof-surface's write-gate. So the gate allows publishing only an artifact
    that matches what was authorized -- identical bytes, or for structured data a
    canonically-equivalent form; a result that drifted is denied, and committing
    with no look or no authorized baseline is needs-human -- never a silent allow.

  goal      = the intended target (a reference observation + a tolerance)
  look()    = perceive the current artifact, compare to the goal -> AdjustmentProposal
  iterate() = drive make->look until converged (the agent's make(), our look)
  authorize() = the operator pins the converged result as the commit baseline
  commit()  = propose the consequential action on the result, through the write-gate

Inert and advisory: looking is free and never gated; only commit() touches the
write-gate, and only for consequential actions (consequence-scope). The loop adds
no authority and removes no check -- every guarantee still lives in the parts it
composes (inert organs, fail-closed gate, honest drift).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterator

from .live import LiveDecision, LiveMembrane
from .observation import Observation
from .organ import Organ
from .organs.visual import VisualArtifactOrgan
from .phash import DRIFT, MATCH, UNVERIFIABLE, DriftVerdict, compare_drift

# Disposition lattice -- the loop's judgement about progress toward the goal.
# Distinct from the drift lattice (MATCH/DRIFT/UNVERIFIABLE): this is "should the
# agent keep adjusting?", not "did the bytes change?".
CONVERGED = "converged"
ADJUST = "adjust"
INDETERMINATE = "indeterminate"  # cannot compare to the goal -> cannot judge
DISPOSITIONS = frozenset({CONVERGED, ADJUST, INDETERMINATE})


def _fingerprint_int(obs: Observation) -> int | None:
    """The perceptual fingerprint of an observation as an int (visual or audio),
    or None if it carries none."""
    for key in ("perceptual_hash", "perceptual_audio_hash"):
        value = obs.data.get(key)
        if value:
            try:
                return int(value, 16)
            except (TypeError, ValueError):
                return None
    return None


@dataclass(frozen=True)
class Goal:
    """The intended target the agent iterates toward: a reference identity + a
    perceptual fingerprint, plus how close still counts as converged.

    tolerance is the operator's "close enough to stop adjusting" threshold (max
    perceptual Hamming distance). It governs ITERATION ONLY; it never reaches the
    write-gate. tolerance=0 converges an exact perceptual match -- a byte-identical
    result (MATCH), or a byte-different one whose perceptual hash is identical
    (distance 0, e.g. a re-encode); larger tolerances admit proportionally more
    perceptual drift.
    """

    subject: str
    identity_sha256: str | None
    fingerprint: int | None
    tolerance: int = 0

    @classmethod
    def from_observation(cls, observation: Observation, *, tolerance: int = 0) -> "Goal":
        return cls(
            subject=observation.subject,
            identity_sha256=observation.data.get("identity_sha256"),
            fingerprint=_fingerprint_int(observation),
            tolerance=tolerance,
        )


@dataclass(frozen=True)
class AdjustmentProposal:
    """The outcome of one look: where the result stands relative to the goal, and
    whether the agent should keep adjusting. Advisory -- the loop recommends; the
    agent acts."""

    iteration: int
    subject: str
    disposition: str  # converged / adjust / indeterminate
    drift: DriftVerdict  # distance from the goal
    reasons: list[str] = field(default_factory=list)
    converged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "subject": self.subject,
            "disposition": self.disposition,
            "converged": self.converged,
            "drift": {
                "verdict": self.drift.verdict,
                "distance": self.drift.distance,
                "reason": self.drift.reason,
            },
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class BasinReport:
    """A2 (aperture-sim) -- witness whether independent starts reconcile to ONE basin.

    The agent loop converges a single trajectory from wherever make() begins; the sims
    proved convergence is START-governed (a near-midpoint basin separatrix), so a single
    'converged' is NOT evidence the result is path-independent. This reports how many
    distinct basins the converged runs fell into: agree (one basin) => path-independent
    FOR THIS GOAL, witnessed not assumed; otherwise the result rode on the start."""

    runs: int           # converged runs compared
    basins: int         # distinct basins they fell into
    agree: bool         # True iff exactly one basin (path-independent, witnessed)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"runs": self.runs, "basins": self.basins, "agree": self.agree,
                "reasons": list(self.reasons)}


def basin_agreement(observations, *, tolerance: int = 0) -> BasinReport:
    """Cluster the converged Observations of independent-start runs into basins.

    Two runs share a basin iff their perceived results MATCH (identity equal) or sit within
    `tolerance` perceptual distance of each other (the same comparison the loop uses against
    the goal). One basin => path-independent (witnessed); >1 => PATH-DEPENDENT, surfaced as a
    reason so a caller never launders a start-dependent result as ownerless. Pure + fail-safe:
    an empty set is agree=False (nothing was witnessed), never a vacuous agreement."""
    obs = [o for o in observations if o is not None]
    n = len(obs)
    if n == 0:
        return BasinReport(0, 0, False, ["no converged runs to compare (nothing witnessed)"])
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            d = compare_drift(obs[i].data.get("identity_sha256"), obs[j].data.get("identity_sha256"),
                              _fingerprint_int(obs[i]), _fingerprint_int(obs[j]))
            same = d.verdict == MATCH or (
                d.verdict == DRIFT and d.distance is not None and d.distance <= tolerance)
            if same:
                parent[find(i)] = find(j)
    basins = len({find(i) for i in range(n)})
    reasons = [f"{n} converged run(s) reconcile to {basins} basin(s)"]
    if basins != 1:
        reasons.append("PATH-DEPENDENT: independent starts reached different basins -- the result "
                       "rode on the start, not the criterion (aperture-sim A2); not ownerless")
    return BasinReport(n, basins, basins == 1, reasons)


class AgentLoop:
    """make -> look -> compare -> adjust around an agent's own production, with the
    one consequential step routed through the write-gate."""

    def __init__(
        self,
        goal: Goal,
        *,
        membrane: LiveMembrane | None = None,
        organ: Organ | None = None,
    ):
        self.goal = goal
        self.membrane = membrane or LiveMembrane(organ=organ)
        self.organ = organ or VisualArtifactOrgan()
        self._iteration = 0
        self._last_obs: Observation | None = None
        self.history: list[AdjustmentProposal] = []

    # --- look / compare / adjust (free, inert, never gated) ----------------

    def look(self, subject) -> AdjustmentProposal:
        """Perceive the current result and compare it to the goal.

        `subject` is a path, bytes, or an already-perceived Observation. Returns an
        AdjustmentProposal recommending converged / adjust / indeterminate. This is
        perception only -- it performs no action and touches no gate.
        """
        obs = self._observe(subject)
        if obs is None:
            return self._record(
                AdjustmentProposal(
                    self._iteration, self.goal.subject, INDETERMINATE,
                    DriftVerdict(UNVERIFIABLE, None, "nothing perceivable in the subject"),
                    ["the organ perceived nothing in the subject"], False,
                ),
                None,
            )
        drift = compare_drift(
            self.goal.identity_sha256, obs.data.get("identity_sha256"),
            self.goal.fingerprint, _fingerprint_int(obs),
        )
        disposition, reasons = self._assess(drift)
        return self._record(
            AdjustmentProposal(self._iteration, self.goal.subject, disposition, drift,
                               reasons, disposition == CONVERGED),
            obs,
        )

    def iterate(self, make: Callable[[], Any], *, max_iterations: int = 10) -> Iterator[AdjustmentProposal]:
        """Drive make -> look -> compare -> adjust until converged or budget spent.

        `make()` is the AGENT's producer (it returns the next artifact subject --
        path, bytes, or Observation). The loop only looks and compares; it never
        actuates a consequential action (use commit() for that, through the gate).
        Yields each AdjustmentProposal and stops at the first converged one.
        """
        for _ in range(max_iterations):
            proposal = self.look(make())
            yield proposal
            if proposal.converged:
                return

    def converge_multistart(
        self, makes, *, max_iterations: int = 10
    ) -> tuple[list[Observation | None], BasinReport]:
        """A2 -- drive iterate() from several INDEPENDENT starts and witness basin agreement.

        `makes` is an iterable of independent producers (diversified starts). Each is run
        through iterate(); the converged Observation per start is collected (None if a start
        never converged within budget). Returns (results, BasinReport). The report says
        whether the starts reconciled to ONE basin (path-independent, witnessed) or DIVERGED
        (path-dependent -- the convergence rode on the start, surfaced not hidden). This
        replaces the implicit single-trajectory assumption with an explicit witness; it adds
        no authority and gates nothing (looking is free)."""
        results: list[Observation | None] = []
        for make in makes:
            converged_obs = None
            for proposal in self.iterate(make, max_iterations=max_iterations):
                if proposal.converged:
                    converged_obs = self._last_obs
                    break
            results.append(converged_obs)
        report = basin_agreement([r for r in results if r is not None], tolerance=self.goal.tolerance)
        return results, report

    # --- the operator authorizes the result as the commit baseline ---------

    def authorize(self, observation: Observation | None = None) -> None:
        """Pin a state as the baseline a commit is checked against (the baseline
        ladder: byte identity, then canonical form for structured data, then
        perceptual distance).

        Defaults to the most recently looked-at result, so the natural flow is
        iterate -> (operator approves) authorize() -> commit().
        """
        obs = observation if observation is not None else self._last_obs
        if obs is None:
            raise ValueError("nothing to authorize: look at a result first or pass an observation")
        self.membrane.authorize(obs)

    # --- commit: the one consequential, gated step -------------------------

    def commit(
        self,
        action_kind: str,
        target: str,
        *,
        observation: Observation | None = None,
        authorization: dict[str, Any] | None = None,
    ) -> LiveDecision:
        """Propose a consequential action on the result, through the write-gate.

        Drift is measured against the authorized baseline via the baseline ladder
        (byte identity, then canonical for structured data, then perceptual
        distance), so the gate confirms the artifact matches what was approved and
        denies one that drifted. Reversible actions flow free; a consequential
        commit with no looked-at result is needs-human (fail-closed), never a
        silent allow.
        """
        obs = observation if observation is not None else self._last_obs
        if self.membrane.scope.requires_gate(action_kind) and obs is None:
            return LiveDecision(
                action_kind, target, gated=True, decision="needs-human",
                reasons=["consequential commit with no witnessed look -- look at the "
                         "result first (fail-closed)"],
            )
        # Only consequential actions consult the baseline/gate; for a reversible
        # action propose() short-circuits to a free allow and never reads drift.
        drift = (
            self.membrane.baseline_check(obs)
            if obs is not None and self.membrane.scope.requires_gate(action_kind)
            else None
        )
        return self.membrane.propose(
            action_kind, target, authorization=authorization, observation=obs, drift=drift,
        )

    # --- internals --------------------------------------------------------

    def _observe(self, subject) -> Observation | None:
        if isinstance(subject, Observation):
            return subject
        observed = self.organ.observe(subject)
        return observed[0] if observed else None

    def _assess(self, drift: DriftVerdict) -> tuple[str, list[str]]:
        if drift.verdict == MATCH:
            return CONVERGED, ["identical to the goal (identity equal)"]
        if drift.verdict == DRIFT:
            if drift.distance is not None and drift.distance <= self.goal.tolerance:
                return CONVERGED, [
                    f"within tolerance: perceptual distance {drift.distance} <= {self.goal.tolerance}"
                ]
            return ADJUST, [
                f"perceptual distance {drift.distance} > tolerance {self.goal.tolerance}; keep adjusting"
            ]
        return INDETERMINATE, ["cannot compare to the goal (a fingerprint is missing)"]

    def _record(self, proposal: AdjustmentProposal, obs: Observation | None) -> AdjustmentProposal:
        # The latest look is authoritative: an UNPERCEIVABLE look (obs is None)
        # clears the default, so a subsequent defaulted commit()/authorize() fails
        # closed rather than silently reusing a stale earlier observation.
        self._last_obs = obs
        self._iteration += 1
        self.history.append(proposal)
        return proposal
