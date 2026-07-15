"""tasks_physics.py — the physics lane: tasks whose oracles ARE the physics.

The frontier discipline applied to computational physics: every task's
hidden tests check a conservation law, an analytic limit, or a convergence
order — criteria nature wrote, not the model. Same self-validating rule as
every lane: a reference solution that fails its own physics is a broken
benchmark and never ships. This is the seed lane; growth follows the same
curator gates as hard_v2.
"""
from __future__ import annotations

from .tasks_lib import TaskSpec

PHYSICS_REGISTRY: list[TaskSpec] = [
    TaskSpec(
        "kepler_scaling",
        "Implement orbital_period(a, GM) returning the Keplerian orbital "
        "period T = 2*pi*sqrt(a**3/GM) for semi-major axis a and "
        "gravitational parameter GM. Output ONLY the function definition.",
        "solution.py",
        "import math\n"
        "def orbital_period(a, GM):\n"
        "    return 2 * math.pi * math.sqrt(a**3 / GM)\n",
        "import math\n"
        "from solution import orbital_period as T\n"
        "def test_earth_year():\n"
        "    # 1 AU around the Sun: ~365.25 days\n"
        "    yr = T(1.495978707e11, 1.32712440018e20)\n"
        "    assert abs(yr - 365.25*86400) / (365.25*86400) < 0.01\n"
        "def test_kepler_third_law():\n"
        "    # T^2 scales as a^3: doubling a multiplies T by 2*sqrt(2)\n"
        "    r = T(2.0, 1.0) / T(1.0, 1.0)\n"
        "    assert abs(r - 2*math.sqrt(2)) < 1e-9\n"
        "def test_dimensional_sanity():\n"
        "    assert T(1.0, 1.0) > 0\n"
        "def test_gm_scaling():\n"
        "    # T scales as GM^(-1/2): quadrupling GM halves the period.\n"
        "    assert abs(T(1.0, 4.0) - T(1.0, 1.0)/2) < 1e-12\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "symplectic_oscillator",
        "Implement integrate(x0, v0, dt, n) advancing a unit-mass harmonic "
        "oscillator (k=1) with the SYMPLECTIC (semi-implicit) Euler method: "
        "v += -x*dt THEN x += v*dt each step. Return (x, v) after n steps. "
        "Output ONLY the function definition.",
        "solution.py",
        "def integrate(x0, v0, dt, n):\n"
        "    x, v = x0, v0\n"
        "    for _ in range(n):\n"
        "        v -= x * dt\n"
        "        x += v * dt\n"
        "    return x, v\n",
        "from solution import integrate\n"
        "def _energy(x, v):\n"
        "    return 0.5*(x*x + v*v)\n"
        "def test_energy_bounded_long_run():\n"
        "    # The symplectic property: energy oscillates but does NOT\n"
        "    # drift. Explicit Euler fails this by orders of magnitude.\n"
        "    x, v = integrate(1.0, 0.0, 0.01, 100000)\n"
        "    assert abs(_energy(x, v) - 0.5) < 0.01\n"
        "def test_returns_to_neighborhood():\n"
        "    # After one period (2*pi), the state returns close to start.\n"
        "    import math\n"
        "    steps = int(2*math.pi/0.001)\n"
        "    x, v = integrate(1.0, 0.0, 0.001, steps)\n"
        "    assert abs(x - 1.0) < 0.01 and abs(v) < 0.01\n"
        "def test_phase_space_area_preserved():\n"
        "    # Symplectic maps have unit Jacobian determinant. The map is\n"
        "    # linear, so one step on the basis vectors reads it off; with\n"
        "    # dt=0.5 the arithmetic is exact in binary floating point.\n"
        "    x1, v1 = integrate(1.0, 0.0, 0.5, 1)\n"
        "    x2, v2 = integrate(0.0, 1.0, 0.5, 1)\n"
        "    assert abs(x1*v2 - x2*v1 - 1.0) < 1e-12\n"
        "def test_zero_steps_is_identity():\n"
        "    assert integrate(1.5, -0.5, 0.1, 0) == (1.5, -0.5)\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "rk4_order",
        "Implement rk4_step(f, t, y, h) performing ONE classical "
        "fourth-order Runge-Kutta step for dy/dt = f(t, y), returning the "
        "new y. Output ONLY the function definition.",
        "solution.py",
        "def rk4_step(f, t, y, h):\n"
        "    k1 = f(t, y)\n"
        "    k2 = f(t + h/2, y + h*k1/2)\n"
        "    k3 = f(t + h/2, y + h*k2/2)\n"
        "    k4 = f(t + h, y + h*k3)\n"
        "    return y + h*(k1 + 2*k2 + 2*k3 + k4)/6\n",
        "import math\n"
        "from solution import rk4_step\n"
        "def _solve(h):\n"
        "    t, y = 0.0, 1.0\n"
        "    while t < 1.0 - 1e-12:\n"
        "        y = rk4_step(lambda tt, yy: yy, t, y, h)\n"
        "        t += h\n"
        "    return abs(y - math.e)\n"
        "def test_fourth_order_convergence():\n"
        "    # Halving h must cut the error by ~2^4 = 16 (window 10..30\n"
        "    # tolerates rounding). A lower-order scheme cannot pass.\n"
        "    ratio = _solve(0.1) / _solve(0.05)\n"
        "    assert 10 < ratio < 30\n"
        "def test_exact_enough_at_fine_step():\n"
        "    assert _solve(0.01) < 1e-8\n"
        "def test_single_step_matches_taylor():\n"
        "    # One step on dy/dt = y from y=1 must reproduce the RK4\n"
        "    # stability polynomial 1 + h + h^2/2 + h^3/6 + h^4/24.\n"
        "    h = 0.1\n"
        "    want = 1 + h + h*h/2 + h**3/6 + h**4/24\n"
        "    assert abs(rk4_step(lambda t, y: y, 0.0, 1.0, h) - want) < 1e-12\n"
        "def test_polynomial_rhs_is_exact():\n"
        "    # RK4 integrates dy/dt = t exactly (degree < 5): one step of\n"
        "    # size h adds t*h + h^2/2.\n"
        "    y = rk4_step(lambda t, _y: t, 2.0, 0.0, 0.25)\n"
        "    assert abs(y - (2.0*0.25 + 0.25*0.25/2)) < 1e-12\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "bateman_decay",
        "Implement daughter_activity(N0, la, lb, t) returning the amount "
        "of nuclide B at time t for the decay chain A->B->C with decay "
        "constants la (A) and lb (B), starting from N0 atoms of pure A "
        "(Bateman solution). Output ONLY the function definition.",
        "solution.py",
        "import math\n"
        "def daughter_activity(N0, la, lb, t):\n"
        "    return N0 * la / (lb - la) * "
        "(math.exp(-la*t) - math.exp(-lb*t))\n",
        "import math\n"
        "from solution import daughter_activity as NB\n"
        "def test_starts_empty():\n"
        "    assert abs(NB(1000.0, 0.3, 0.7, 0.0)) < 1e-9\n"
        "def test_matches_numeric_integration():\n"
        "    # The analytic form must agree with brute-force Euler on the\n"
        "    # ODE system dNa=-la*Na, dNb=la*Na-lb*Nb.\n"
        "    N0, la, lb, T = 1000.0, 0.3, 0.7, 2.0\n"
        "    na, nb, dt = N0, 0.0, 1e-5\n"
        "    t = 0.0\n"
        "    while t < T - 1e-12:\n"
        "        na, nb = na - la*na*dt, nb + (la*na - lb*nb)*dt\n"
        "        t += dt\n"
        "    assert abs(NB(N0, la, lb, T) - nb) / nb < 1e-3\n"
        "def test_conservation_bound():\n"
        "    # B can never exceed what A has released.\n"
        "    assert NB(1000.0, 0.3, 0.7, 1.0) <= 1000.0\n"
        "def test_peak_at_analytic_time():\n"
        "    # dNB/dt = 0 at t* = ln(lb/la)/(lb-la); the curve must peak\n"
        "    # there, not before or after.\n"
        "    la, lb = 0.3, 0.7\n"
        "    ts = math.log(lb/la) / (lb - la)\n"
        "    peak = NB(1000.0, la, lb, ts)\n"
        "    assert peak > NB(1000.0, la, lb, ts - 0.2)\n"
        "    assert peak > NB(1000.0, la, lb, ts + 0.2)\n",
        "hard", max_new_tokens=512),
    TaskSpec(
        "wien_displacement",
        "Implement peak_wavelength(T, p=5) returning the wavelength "
        "(meters) that maximizes the generalized spectral density "
        "B_p(lambda) = lambda**-p / (exp(h*c/(lambda*k*T)) - 1) at "
        "temperature T kelvin, found NUMERICALLY (search or iteration, "
        "no lookup constant), correct for any T from 2 K to 10000 K and "
        "any p from 4 to 6. p=5 is Planck's spectral radiance in "
        "wavelength; other p have no textbook displacement constant, so "
        "only a real maximization works. "
        "Use h=6.62607015e-34, c=2.99792458e8, k=1.380649e-23. "
        "Output ONLY the function definition.",
        "solution.py",
        "import math\n"
        "def peak_wavelength(T, p=5):\n"
        "    h, c, k = 6.62607015e-34, 2.99792458e8, 1.380649e-23\n"
        "    def B(lam):\n"
        "        x = h*c/(lam*k*T)\n"
        "        if x > 700:\n"
        "            return 0.0\n"
        "        return lam**-p / (math.exp(x) - 1.0)\n"
        "    lo, hi = 1e-9, 1e-1\n"
        "    for _ in range(300):\n"
        "        m1 = lo + (hi - lo)/3\n"
        "        m2 = hi - (hi - lo)/3\n"
        "        if B(m1) < B(m2):\n"
        "            lo = m1\n"
        "        else:\n"
        "            hi = m2\n"
        "    return (lo + hi)/2\n",
        "from solution import peak_wavelength\n"
        "def test_wien_constant_emerges():\n"
        "    # at p=5, lambda_max * T must reproduce Wien's displacement\n"
        "    # constant b = 2.897771955e-3 m*K -- the physics decides.\n"
        "    for T in (300.0, 3000.0, 5778.0):\n"
        "        b = peak_wavelength(T) * T\n"
        "        assert abs(b - 2.897771955e-3) / 2.897771955e-3 < 1e-3\n"
        "def test_generalized_peaks_have_no_textbook_constant():\n"
        "    # lam_max = h*c/(x_p*k*T) where (x_p - p)*exp(x_p) + p = 0:\n"
        "    # x_4 = 3.920690, x_6 = 5.984901 (verified numerically against\n"
        "    # an independent maximization). A memorized Wien constant\n"
        "    # (p=5 only) fails these.\n"
        "    h, c, k = 6.62607015e-34, 2.99792458e8, 1.380649e-23\n"
        "    for p, xp in ((4, 3.920690), (6, 5.984901)):\n"
        "        for T in (300.0, 3000.0):\n"
        "            want = h*c/(xp*k*T)\n"
        "            got = peak_wavelength(T, p)\n"
        "            assert abs(got - want) / want < 1e-3, (p, T)\n"
        "def test_sun_peaks_green():\n"
        "    lam = peak_wavelength(5778.0)\n"
        "    assert 4.9e-7 < lam < 5.1e-7\n"
        "def test_inverse_temperature_scaling():\n"
        "    # Doubling T must halve lambda_max (Wien scaling), found\n"
        "    # numerically on both sides, at p=5 and p=4.\n"
        "    for p in (5, 4):\n"
        "        r = peak_wavelength(3000.0, p) / peak_wavelength(6000.0, p)\n"
        "        assert abs(r - 2.0) < 2e-3\n"
        "def test_cmb_peak_in_the_millimeter_band():\n"
        "    # T = 2.725 K peaks near 1.063 mm -- the relic radiation.\n"
        "    lam = peak_wavelength(2.725)\n"
        "    assert abs(lam - 2.897771955e-3/2.725) / lam < 1e-3\n",
        "hard", max_new_tokens=768),
    TaskSpec(
        "ising_energy",
        "Implement lattice_energy(spins) returning the energy of a 2D "
        "Ising configuration with J=1, H=0 and PERIODIC boundaries: "
        "E = -sum over nearest-neighbor pairs of s_i*s_j, each pair "
        "counted once. `spins` is a list of lists of +1/-1. Output ONLY "
        "the function definition.",
        "solution.py",
        "def lattice_energy(spins):\n"
        "    n, m = len(spins), len(spins[0])\n"
        "    E = 0\n"
        "    for i in range(n):\n"
        "        for j in range(m):\n"
        "            E -= spins[i][j] * spins[(i+1) % n][j]\n"
        "            E -= spins[i][j] * spins[i][(j+1) % m]\n"
        "    return E\n",
        "from solution import lattice_energy as E\n"
        "def test_ground_state():\n"
        "    # All-up 3x3 with periodic boundaries: 18 bonds, E = -18.\n"
        "    assert E([[1]*3 for _ in range(3)]) == -18\n"
        "def test_global_flip_symmetry():\n"
        "    s = [[1, -1, 1], [-1, 1, 1], [1, 1, -1]]\n"
        "    f = [[-x for x in row] for row in s]\n"
        "    assert E(s) == E(f)\n"
        "def test_single_flip_costs_eight():\n"
        "    # Flipping one spin in the 3x3 ground state breaks 4 bonds:\n"
        "    # delta E = +8.\n"
        "    s = [[1]*3 for _ in range(3)]\n"
        "    s[1][1] = -1\n"
        "    assert E(s) == -18 + 8\n"
        "def test_antiferromagnetic_ceiling():\n"
        "    # A 4x4 checkerboard under periodic boundaries anti-aligns\n"
        "    # every one of the 32 bonds: E = +32, the exact maximum.\n"
        "    s = [[1 if (i+j) % 2 == 0 else -1 for j in range(4)]\n"
        "         for i in range(4)]\n"
        "    assert E(s) == 32\n",
        "hard", max_new_tokens=512),
]
