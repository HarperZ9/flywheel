"""The physics lane's admission falsifiers: every reference solution must
pass its own physics (conservation, analytic limits, convergence order),
and every oracle must be able to FAIL — a physics test a wrong solution
passes is not physics, it is decoration."""

import pytest

from harness.task_curator import screen
from harness.tasks_physics import PHYSICS_REGISTRY


@pytest.mark.parametrize("spec", PHYSICS_REGISTRY,
                         ids=[s.task_id for s in PHYSICS_REGISTRY])
def test_reference_solution_clears_every_gate(spec, tmp_path):
    r = screen(spec, tmp_path)
    assert r["admitted"], r["gates"]


def test_the_physics_can_fail(tmp_path):
    # A plausible-looking WRONG integrator (explicit Euler) must be
    # rejected by the symplectic task's energy oracle.
    from harness.task_curator import _run_with
    spec = next(s for s in PHYSICS_REGISTRY
                if s.task_id == "symplectic_oscillator")
    euler = ("def integrate(x0, v0, dt, n):\n"
             "    x, v = x0, v0\n"
             "    for _ in range(n):\n"
             "        x, v = x + v*dt, v - x*dt\n"
             "    return x, v\n")
    assert _run_with(spec, tmp_path, euler, "wrong-physics") is False


def test_symplectic_pins_the_mandated_update_order(tmp_path):
    # The x-first update (x += v*dt THEN v -= x*dt) is ALSO symplectic -- unit
    # Jacobian, bounded energy, correct period -- so it satisfied every original
    # hidden test while ignoring the mandated v-then-x order. One exact first
    # step discriminates: v-then-x from (1,0) at dt=0.5 gives (0.75, -0.5); the
    # x-first variant gives (1.0, -0.5). The task must reject the cheat.
    from harness.task_curator import _run_with
    spec = next(s for s in PHYSICS_REGISTRY
                if s.task_id == "symplectic_oscillator")
    x_first = ("def integrate(x0, v0, dt, n):\n"
               "    x, v = x0, v0\n"
               "    for _ in range(n):\n"
               "        x += v * dt\n"
               "        v -= x * dt\n"
               "    return x, v\n")
    assert _run_with(spec, tmp_path, x_first, "opposite-order") is False
