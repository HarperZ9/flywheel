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
