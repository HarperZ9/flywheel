"""asymmetry integration-layer falsifier — amplifiers compound, gates bound honestly.

The load-bearing properties: amplifiers multiply UP; gates multiply the amplitude
DOWN; a gate at 0 collapses the whole amplitude regardless of amplifier size (the
anti-overclaim property); and the project ledger is grounded in the real modules.
"""
from harness.asymmetry import (
    Asymmetry, amplifier, gate, composed_amplitude, ledger, ledger_report,
    measure_project)


def test_amplifiers_compound_multiplicatively():
    a = [amplifier("x", "d", 6, 3, "src"), amplifier("y", "d", 10, 2, "src")]  # 2x, 5x
    c = composed_amplitude(a)
    assert c["amplifier_product"] == 10.0 and c["amplitude"] == 10.0   # no gates -> full


def test_gate_bounds_the_amplitude():
    a = [amplifier("x", "d", 10, 1, "src"),      # 10x
         gate("fidelity", "d", 0.5, "src")]       # half
    c = composed_amplitude(a)
    assert c["amplitude"] == 5.0 and c["binding_gate"] == "fidelity"


def test_failed_gate_collapses_amplitude_regardless_of_amplifiers():
    # the anti-overclaim property: a broken gate zeroes it no matter how big the amps
    a = [amplifier("x", "d", 1e6, 1, "src"), gate("broken", "d", 0.0, "src")]
    c = composed_amplitude(a)
    assert c["amplitude"] == 0.0, "a failed fidelity gate must collapse the amplitude"


def test_non_independent_amplifier_does_not_multiply_in():
    ind = amplifier("x", "d", 4, 1, "src")                       # 4x, independent
    dep = amplifier("y", "d", 4, 1, "src", independent=False)    # 4x, NOT independent
    c = composed_amplitude([ind, dep])
    assert c["amplifier_product"] == 4.0                          # only the independent one


def test_binding_gate_is_the_smallest_fidelity():
    a = [gate("g1", "d", 0.9, "s"), gate("g2", "d", 0.6, "s"), gate("g3", "d", 0.95, "s")]
    c = composed_amplitude(a)
    assert c["binding_gate"] == "g2" and abs(c["binding_fidelity"] - 0.6) < 1e-9


def test_project_ledger_is_grounded_and_reports():
    led = measure_project()
    names = {r["name"] for r in led["asymmetries"]}
    assert {"amortization", "verified_lift", "systematicity", "adversarial_soundness"} <= names
    # the system is built to hold its gates -> gate product ~1 -> amplitude ~ amplifier product
    assert led["gate_product"] >= 0.99 and led["amplitude"] > 1.0
    assert led["binding_fidelity"] >= 0.99          # all gates held (green system)
    assert "systematic amplitude" in ledger_report(led)
    # grounded in real modules, not invented
    assert all(r["grounded_in"] for r in led["asymmetries"])
    assert len(led["domains_covered"]) >= 3
