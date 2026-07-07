"""asymmetry.py — the integration layer: every seam as one composable variable.

Across the project, every seam is an ASYMMETRY between a naive/authority regime and
an accountable/re-checkable one, and each is measurable as a dimensionless number.
They come in exactly two kinds, and the distinction is the whole point:

  AMPLIFIER (leverage >= 1): the accountable regime beats the naive one by a factor.
    - amortization: total/unique = 1/(1-r)   (authorization_cost)
    - verified lift: verified_pass / single_shot_pass   (eval)
    - escalation prune: total / expensive-tier-runs   (escalation)
    These COMPOUND MULTIPLICATIVELY over independent axes — the "vertical".

  GATE (fidelity in [0,1]): how faithfully a criterion is conserved / verified.
    - systematicity (structure_mapping), calibration soundness (calibration),
      adversarial soundness = 1 - false_accept_rate (adversarial_corpus),
      chain re-witness rate (chain), quorum agreement (quorum).
    These MULTIPLY THE AMPLITUDE DOWN.

Systematic amplitude = prod(amplifiers) * prod(gates). The amplifiers launch it up;
the gates keep it honest. The load-bearing, anti-overclaim property: ANY gate at 0
collapses the whole amplitude no matter how large the amplifiers — you cannot fake
your way up. That is the accountability thesis as a single composed variable.

HONEST BOUNDS (enforced in tests, not decoration):
  1. Amplifiers multiply ONLY when the axes are independent and co-act on one
     workload; the layer records the independence assumption per entry, it does not
     assume it silently.
  2. A gate < 1 is a real cost, not rounding — the amplitude it yields is the
     ACHIEVABLE leverage, not the theoretical amplifier product.
  3. This layer measures the seams we HAVE instrumented in this repo; it does not
     reach into operator-owned repos it must not touch. Coverage is explicit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Asymmetry:
    name: str
    domain: str
    kind: str                 # "amplifier" | "gate"
    surface: float            # naive/authority quantity (amplifier) or 1.0 (gate)
    core: float               # accountable/conserved quantity
    leverage: float           # amplifier: surface/core (>=1); gate: fidelity in [0,1]
    grounded_in: str          # the module/function this was computed from
    independent: bool = True  # amplifier: does it act on an independent axis?


def amplifier(name, domain, surface, core, grounded_in, *, independent=True) -> Asymmetry:
    lev = (surface / core) if core else math.inf
    return Asymmetry(name, domain, "amplifier", float(surface), float(core),
                     lev, grounded_in, independent)


def gate(name, domain, fidelity, grounded_in) -> Asymmetry:
    f = max(0.0, min(1.0, float(fidelity)))
    return Asymmetry(name, domain, "gate", 1.0, f, f, grounded_in, True)


def composed_amplitude(asyms: list[Asymmetry]) -> dict:
    """The systematic amplitude: prod(independent amplifiers) * prod(gates). Returns
    the amplitude, the raw amplifier product (ungated), and the binding gate — the
    smallest fidelity, the one most limiting the achievable leverage."""
    amps = [a for a in asyms if a.kind == "amplifier"]
    gates = [a for a in asyms if a.kind == "gate"]
    amp_product = 1.0
    for a in amps:
        if a.independent:
            amp_product *= a.leverage
    gate_product = 1.0
    for g in gates:
        gate_product *= g.leverage
    amplitude = amp_product * gate_product
    binding = min(gates, key=lambda g: g.leverage) if gates else None
    return {"amplitude": amplitude,
            "amplifier_product": amp_product,
            "gate_product": gate_product,
            "binding_gate": binding.name if binding else None,
            "binding_fidelity": binding.leverage if binding else 1.0,
            "n_amplifiers": len(amps), "n_gates": len(gates)}


def ledger(asyms: list[Asymmetry]) -> dict:
    comp = composed_amplitude(asyms)
    rows = [{"name": a.name, "domain": a.domain, "kind": a.kind,
             "leverage": round(a.leverage, 4), "grounded_in": a.grounded_in,
             "independent": a.independent} for a in asyms]
    return {"asymmetries": rows, **comp,
            "domains_covered": sorted({a.domain for a in asyms})}


def ledger_report(led: dict) -> str:
    return (f"systematic amplitude {led['amplitude']:.3g}x "
            f"= amplifiers {led['amplifier_product']:.3g}x * gates {led['gate_product']:.3f} "
            f"(binding gate: {led['binding_gate']} @ {led['binding_fidelity']:.3f}); "
            f"{led['n_amplifiers']} amplifiers, {led['n_gates']} gates over "
            f"{len(led['domains_covered'])} domains")


def measure_project() -> dict:
    """Measure the real, instrumented asymmetries of THIS repo, grounded in the
    actual modules (no invented numbers; representative workloads are labelled).
    The gates come out ~1.0 because the system is BUILT to hold them — which is the
    point: the green test suite IS the gate array, and a regression drops a gate
    and collapses the amplitude."""
    from .authorization_cost import regime_cost
    from .perception_probe import make_scene, conserving_encode
    from .structure_mapping import systematicity
    from .adversarial_corpus import run_corpus
    from .transitive_witness import transitive_verdicts

    asyms: list[Asymmetry] = []

    # AMPLIFIERS (grounded)
    r = regime_cost(["a", "b", "c", "d", "e"] * 4)     # representative flywheel, r=0.75
    asyms.append(amplifier("amortization", "compute-economy", r.permission_cost,
                           r.accountability_cost, "authorization_cost.regime_cost"))
    # verified lift, from the recorded M7 hard-set result (single_shot 0.80 -> verified 0.90)
    asyms.append(amplifier("verified_lift", "capability", 0.90, 0.80,
                           "m7_hard_scorecard_20260706 (verified/single_shot)"))

    # GATES (grounded)
    s = make_scene(7)
    asyms.append(gate("systematicity", "perception",
                      systematicity(s, conserving_encode(s)),
                      "structure_mapping.systematicity"))
    corpus = run_corpus(transitive_verdicts)
    asyms.append(gate("adversarial_soundness", "verification",
                      1.0 - corpus["false_accept_rate"],
                      "adversarial_corpus.run_corpus(transitive_verdicts)"))

    return ledger(asyms)
