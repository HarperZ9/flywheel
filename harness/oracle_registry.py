"""oracle_registry.py -- route work to its domain's oracle, one loop for all.

oracle.py's contract is "a new domain = a new Oracle subclass, same loop." That
gives the boundary. This gives the routing: a registry from domain to the oracle
that disposes it, and one entrypoint (`run_verified`) that resolves the oracle by
domain and drives the existing loop. Nothing here reinvents the loop; it composes
run_loop and the Oracle Protocol.

The property that makes "spans every domain" honest rather than a boast: a domain
with no registered oracle returns UNVERIFIABLE with reason ORACLE_UNAVAILABLE, and
no proposal is spent. The engine never fabricates a verdict for a domain it cannot
check. "No receipt, no accept" extended to "no oracle, no verdict."

Registered today: the code/execution domain (pytest). The math (Lean), ML
(measurement gate), and other domain oracles are separate components; when they
exist they register here, and until they do their domains answer UNVERIFIABLE
truthfully rather than silently passing.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .oracle import Oracle, OracleResult, PytestOracle
from .verdict import UnverifiableReason, Verdict


# Canonical domain names and the aliases callers actually pass. A domain is the
# kind of claim, not the tool: "code" is verified by execution, "math" by a proof
# checker, "ml" by a measurement gate with an interval.
_ALIASES = {
    "python": "code", "pytest": "code", "execution": "code", "test": "code",
    "software": "code", "unit-test": "code",
    "mathematics": "math", "proof": "math", "lean": "math", "theorem": "math",
    "measurement": "ml", "model": "ml", "eval": "ml",
}


def canonical_domain(domain: str) -> str:
    d = (domain or "").strip().lower()
    return _ALIASES.get(d, d)


@dataclass
class DomainOracle:
    """An oracle bound to a domain, with the scope of what it checks.

    `scope` travels with the oracle so a verdict from it reads as exactly what
    the oracle checked (the render.py discipline, at the registry level)."""
    domain: str
    oracle: Oracle
    scope: tuple[str, ...] = ()


class OracleRegistry:
    """Domain -> oracle. Deny by default: an unregistered domain resolves to None
    and the engine answers UNVERIFIABLE, never a fabricated pass."""

    def __init__(self) -> None:
        self._by_domain: dict[str, DomainOracle] = {}

    def register(self, domain: str, oracle: Oracle, *,
                 scope: tuple[str, ...] = ()) -> None:
        d = canonical_domain(domain)
        if not d:
            raise ValueError("a domain name is required")
        self._by_domain[d] = DomainOracle(d, oracle, scope)

    def resolve(self, domain: str) -> Oracle | None:
        entry = self._by_domain.get(canonical_domain(domain))
        return entry.oracle if entry is not None else None

    def entry(self, domain: str) -> DomainOracle | None:
        return self._by_domain.get(canonical_domain(domain))

    def domains(self) -> list[str]:
        return sorted(self._by_domain)

    def __contains__(self, domain: str) -> bool:
        return canonical_domain(domain) in self._by_domain


def default_registry() -> OracleRegistry:
    """The registry with the oracles that exist today. Extend by registering new
    DomainOracles; do not special-case them in the loop.

    `math` is registered whether or not the Lean toolchain is installed: the
    domain is in scope, and a claim answers UNVERIFIABLE (toolchain missing)
    rather than ORACLE_UNAVAILABLE (no oracle) when Lean is absent. That
    distinction is the difference between "the engine cannot check this kind of
    claim" and "the engine can, but this environment lacks the checker"."""
    from .lean_oracle import LeanOracle
    from .measurement_oracle import MeasurementOracle
    reg = OracleRegistry()
    reg.register("code", PytestOracle(),
                 scope=("the candidate ran against the tests the task ships",))
    reg.register("math", LeanOracle(),
                 scope=("Lean checked the proof term against the stated "
                        "theorem",))
    reg.register("ml", MeasurementOracle(),
                 scope=("a measurement gate bounds a tested effect against a "
                        "control",))
    return reg


def unverifiable_result(domain: str, task) -> OracleResult:
    """The honest-null oracle answer for a domain with no verifier. A direct
    OracleResult so a caller that wants the loop-shaped object still gets one,
    without a fabricated PASS/FAIL."""
    d = canonical_domain(domain)
    return OracleResult(
        cmd=getattr(task, "oracle_cmd", ""), output_hash="", stdout_excerpt="",
        rc=0, verdict_=Verdict.UNVERIFIABLE,
        unverifiable_reason=UnverifiableReason.ORACLE_UNAVAILABLE.value,
        scope=[f"no oracle is registered for the {d!r} domain; the claim "
               "stands unchecked"])


@dataclass
class EngineVerdict:
    """One reconcile result: which domain, what verdict, whether it was accepted,
    and why. `loop` is the full LoopResult when an oracle ran, None when the
    domain had no verifier."""
    domain: str
    verdict: str
    accepted: bool
    reason: str
    loop: "object | None" = None
    scope: tuple[str, ...] = field(default_factory=tuple)

    def to_trace(self) -> dict:
        return {"domain": self.domain, "verdict": self.verdict,
                "accepted": self.accepted, "reason": self.reason,
                "scope": list(self.scope)}


def run_verified(task, proposer, *, domain: str,
                 registry: OracleRegistry | None = None,
                 **loop_kwargs) -> EngineVerdict:
    """The one all-domain entrypoint. Resolve the oracle for `domain`, then drive
    the existing loop. A domain with no oracle returns UNVERIFIABLE without
    spending a proposal, because a claim that cannot be verified must not be
    accepted, and proposing first would waste the call and tempt a fabricated
    accept."""
    reg = registry if registry is not None else default_registry()
    entry = reg.entry(domain)
    if entry is None:
        avail = ", ".join(reg.domains()) or "none"
        return EngineVerdict(
            canonical_domain(domain), Verdict.UNVERIFIABLE.value, False,
            f"no oracle for domain {canonical_domain(domain)!r} "
            f"({UnverifiableReason.ORACLE_UNAVAILABLE.value}); "
            f"registered domains: {avail}",
            loop=None,
            scope=(f"the {canonical_domain(domain)!r} claim stands unchecked",))
    from .loop import run_loop
    lr = run_loop(task, proposer, entry.oracle, **loop_kwargs)
    return EngineVerdict(
        entry.domain, lr.envelope.verdict, lr.accepted,
        f"disposed by the {entry.oracle.oracle_type} oracle for the "
        f"{entry.domain!r} domain", loop=lr,
        scope=entry.scope)
