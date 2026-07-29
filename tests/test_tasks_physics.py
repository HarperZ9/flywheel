"""The physics lane's admission falsifiers: every reference solution must
pass its own physics (conservation, analytic limits, convergence order),
and every oracle must be able to FAIL -- a physics test a wrong solution
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


def test_branch_entanglement_oracle_rejects_determinant_without_norm2(tmp_path):
    """A scaled Bell state exposes determinant-only "concurrence".

    The unnormalized state (3|00> + 3|11>) has norm2=18, so its normalized
    determinant magnitude remains 1/2 and concurrence remains 1.  Returning
    the raw determinant instead reports 9 and 18, respectively.
    """
    from harness.task_curator import _run_with

    spec = next(s for s in PHYSICS_REGISTRY
                if s.task_id == "branch_entanglement_invariants")
    determinant_without_norm2 = (
        "def branch_invariants(a00, a01, a10, a11):\n"
        "    norm2 = sum(abs(a)**2 for a in (a00, a01, a10, a11))\n"
        "    determinant_magnitude = abs(a00*a11 - a01*a10)\n"
        "    return norm2, determinant_magnitude, 2*determinant_magnitude\n"
    )

    assert _run_with(spec, tmp_path, determinant_without_norm2,
                     "determinant-without-norm2") is False


def test_projected_sector_oracle_rejects_projection_without_leakage(tmp_path):
    """A conditional sector calculation must not erase amplitude outside it."""
    from harness.task_curator import _run_with

    spec = next(s for s in PHYSICS_REGISTRY
                if s.task_id == "projected_sector_audit")
    projection_without_leakage = (
        "def audit_projected_sector(amplitudes, indices):\n"
        "    a00, a01, a10, a11 = (amplitudes[i] for i in indices)\n"
        "    full_norm2 = sum(abs(a)**2 for a in amplitudes)\n"
        "    sector_norm2 = sum(abs(a)**2 for a in (a00, a01, a10, a11))\n"
        "    conditional_concurrence = 2 * abs(a00*a11 - a01*a10) / sector_norm2\n"
        "    return full_norm2, 1.0, 0.0, conditional_concurrence\n"
    )

    # The source is valid and exposes the task's exact entry point: the
    # subsequent rejection cannot be credited to a syntax or import failure.
    mutant_namespace: dict[str, object] = {}
    exec(compile(projection_without_leakage, "projection_without_leakage.py",
                 "exec"), mutant_namespace)
    audit = mutant_namespace["audit_projected_sector"]
    result = audit((3, 0, 0, 4, 12), (0, 1, 2, 3))
    assert result[0] == 169
    assert result[1] == 1.0
    assert result[2] == 0.0
    assert result[3] == pytest.approx(24 / 25)

    assert _run_with(spec, tmp_path, projection_without_leakage,
                     "projection-without-leakage") is False
