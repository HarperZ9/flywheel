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
    # verified lift: the +10% M7 hard-set lift did NOT reproduce under the ablation
    # (2026-07-06: single 80% / ext 80% / self 80%, +0%). The earlier 80->90 was one
    # task of ten, no CI, inside noise. Relabeled to leverage 1.0 (NO measured lift)
    # rather than carry an unearned result. Needs a harder set (single_shot < 80%),
    # larger N, and a confidence interval before this can be an amplifier again.
    asyms.append(amplifier("verified_lift", "capability", 0.80, 0.80,
                           "run_ablation 20260706: +10% M7 did NOT reproduce (within noise, N=10)"))

    # GATES (grounded)
    s = make_scene(7)
    asyms.append(gate("systematicity", "perception",
                      systematicity(s, conserving_encode(s)),
                      "structure_mapping.systematicity"))
    corpus = run_corpus(transitive_verdicts)
    asyms.append(gate("adversarial_soundness", "verification",
                      1.0 - corpus["false_accept_rate"],
                      "adversarial_corpus.run_corpus(transitive_verdicts)"))

    # --- the cross-domain mechanisms (grounded, real calls) ------------------
    from .cross_domain import run_all as cross_run
    from .inversion_flywheel import run_acceleration
    from .fluid_router import Grid, springload, conservation, springload_amortization
    from .valve_flywheel import run_stream
    from .backflow import run_levels
    from .turbulence import regime as turb_regime

    # AMPLIFIERS
    acc = run_acceleration()                            # active vs passive shadow ordering
    asyms.append(amplifier("inversion_acceleration", "active-inference",
                           acc["passive_to_floor"], acc["active_to_floor"],
                           "inversion_flywheel.run_acceleration"))
    _wall = frozenset({(3, 0), (3, 1), (3, 2), (3, 3)})
    _g = Grid(6, 5, sink=(5, 2), blocked=_wall)
    _src = [(0, 0), (0, 2), (0, 4), (1, 1), (2, 3)]
    fa = springload_amortization(_g, _src)
    asyms.append(amplifier("fluid_springload", "flow",
                           fa["passive_cost"], fa["springloaded_cost"],
                           "fluid_router.springload_amortization"))

    # GATES (each ~1.0 because the suite holds it; a regression drops it)
    asyms.append(gate("cross_domain_coverage", "cross-domain",
                      cross_run()["coverage"], "cross_domain.run_all"))
    asyms.append(gate("fluid_conservation", "flow",
                      1.0 if conservation(_g, springload(_g), _src)["conserved"] else 0.0,
                      "fluid_router.conservation(relaxed)"))
    asyms.append(gate("valve_ratchet", "control",
                      1.0 if run_stream(1.0, [5, 0.1, -3, 4, -8, 7])["monotone_no_regression"] else 0.0,
                      "valve_flywheel.run_stream"))
    asyms.append(gate("backflow_no_regression", "control",
                      1.0 if run_levels([3, 5, 4, 6, 2, 9])["monotone"] else 0.0,
                      "backflow.run_levels"))
    asyms.append(gate("turbulence_invariant", "chaos",
                      1.0 if turb_regime(3.9)["invariant_rechecks"] else 0.0,
                      "turbulence.regime(3.9).invariant_rechecks"))

    led = ledger(asyms)
    led["disclaimer"] = ("this is a CATALOG of independently-grounded asymmetries, each "
                         "with its own module and number. The composed 'amplitude' is a "
                         "scoring composition we DEFINED (prod amplifiers * prod gates), "
                         "NOT a discovered capacity or a launch variable — the adversarial "
                         "audit retired that reading. The gates sit at ~1.0 because the "
                         "green suite holds them; a regression drops a gate and collapses "
                         "the amplitude. The amplifiers are the only real leverage.")
    return led
