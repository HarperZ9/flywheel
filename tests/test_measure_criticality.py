"""harness.measure.criticality: the closed form, the fits, the early-warning plumbing and the planted truths.

False-success controls: the closed form is compared with a direct numerical minimisation of the paper's integral
over the paper's own parameterisation (first n - beta/2 coefficients free, the rest lifted by the linear
constraints), so it cannot pass by agreeing with itself, and a plausible wrong formula (no differencing) must
fail that comparison. The causal-detrend test changes only future values and requires the past to stay identical.
"""
import math
import random

import pytest

from harness.measure.criticality import core, measure, sims


def random_stable(n, rng):
    """Kernel whose polynomial has real roots of modulus 1.1 to 3 (product of first-order factors)."""
    poly = [1.0]
    for _ in range(n):
        r = rng.uniform(1.1, 3.0) * rng.choice([-1, 1])
        poly = [a - b / r for a, b in zip(poly + [0.0], [0.0] + poly)]
    return [-c for c in poly[1:]]


def lift(red, n, k):
    if k == 0:
        return list(red)
    tl = [float(t) for t in range(n - k + 1, n + 1)]
    tf = [float(t) for t in range(1, n - k + 1)]
    M = [[t ** m for t in tl] for m in range(k)]
    rhs = [(1.0 if m == 0 else 0.0) - sum((t ** m) * v for t, v in zip(tf, red)) for m in range(k)]
    return list(red) + core.solve(M, rhs)


def numeric_d(phi, beta, npts=1 << 11):
    opt = pytest.importorskip("scipy.optimize")
    n, k = len(phi), beta // 2

    def J(red, N=npts):
        pb = lift(red, n, k)
        ws = [(i + 0.5) * 2 * math.pi / N - math.pi for i in range(N)]
        s2 = sum(core._g(pb, 1.0, w) / core._g(phi, 1.0, w) for w in ws) / N
        return core.kl_rate(phi, 1.0, pb, s2, npts=N)

    x0 = core.d_beta(phi, beta)[1][: n - k]
    if n - k == 0:
        return J([], 1 << 16)
    best = None
    for shift in (0.0, 0.15, -0.15):
        r = opt.minimize(J, [v + shift for v in x0], method="Nelder-Mead",
                         options={"xatol": 1e-7, "fatol": 1e-11, "maxiter": 3000})
        best = r if best is None or r.fun < best.fun else best
    return J(list(best.x), 1 << 16)


@pytest.mark.parametrize("n,beta", [(1, 2), (2, 2), (3, 2), (3, 4), (4, 4)])
def test_closed_form_is_the_numeric_minimum(n, beta):
    phi = random_stable(n, random.Random(10 * n + beta))
    d = core.d_beta(phi, beta)[0]
    dn = numeric_d(phi, beta)
    assert dn >= d - 3e-5          # midpoint bias at 2^16 points is about 1e-5
    assert dn - d < 5e-5


def test_mutant_without_differencing_fails():
    phi = random_stable(3, random.Random(3))
    _, pev = core.levinson(core.ar_acov(phi, 1.0, 3), 2)
    assert abs(0.5 * math.log(pev) - numeric_d(phi, 2)) > 1e-3


def test_analytic_values():
    for p in (0.0, 0.5, 0.9, 0.99):
        assert abs(core.d_beta_bits([p]) - 0.5 * math.log2(2 / (1 + p))) < 1e-12
    for n in (1, 2, 5, 10):
        assert abs(core.d_beta_bits([0.0] * n) - core.white_noise_bits(n)) < 1e-12


def test_nesting_and_refusals():
    rng = random.Random(11)
    for _ in range(5):
        phi = random_stable(6, rng)
        d2, d4, d6 = (core.d_beta(phi, b)[0] for b in (2, 4, 6))
        assert d2 <= d4 + 1e-12 and d4 <= d6 + 1e-12
    assert core.d_beta_bits([0.99999]) < 1e-5
    for bad in ([1.0], [0.5, 0.6]):
        with pytest.raises(ValueError):
            core.d_beta(bad)
    with pytest.raises(ValueError):
        core.d_beta([0.5], 4)


def test_stationarity_step_down():
    assert core.is_stationary([0.5, 0.3]) and core.is_stationary([0.0, 0.0])
    assert not core.is_stationary([0.5, 0.5]) and not core.is_stationary([1.2, -0.1])
    assert not core.is_stationary([0.0, -1.0])


def test_closest_kernel_is_critical():
    _, phic = core.d_beta([0.6, -0.2, 0.1], 2)
    assert abs(sum(phic) - 1.0) < 1e-10


def test_fits_recover_kernel_and_d2():
    x = sims.ar_sim([0.7, 0.2], 60000, seed=9)
    truth = core.d_beta_bits([0.7, 0.2])
    for fit in ("yw", "yw_unbiased", "ols"):
        r = measure.d2(x, 2, fit=fit)
        assert r["ok"] and r["scope"] == measure.SCOPE_D2
        assert all(abs(a - b) < 0.02 for a, b in zip(r["phi"], [0.7, 0.2]))
        assert abs(r["d"] - truth) < 0.05 * truth


def test_error_bar_matches_ar1_delta_method():
    x = sims.ar_sim([0.9], 5000, seed=13)
    r = measure.d2(x, 1, fit="ols", err=True)
    expect = math.sqrt((1 - 0.81) / 5000) / (2 * math.log(2) * 1.9)
    assert abs(r["se"] - expect) < 0.15 * expect


def test_causal_detrend_never_reads_the_future():
    x = sims.ar_sim([0.5], 300, seed=4)
    y = list(x[:200]) + [v + 10.0 for v in x[200:]]          # a step after t = 199
    a, b = measure.detrend(x, 10), measure.detrend(y, 10)
    assert max(abs(p - q) for p, q in zip(a[:200], b[:200])) == 0.0
    s1, s2 = measure.detrend(x, 10, causal=False), measure.detrend(y, 10, causal=False)
    assert max(abs(p - q) for p, q in zip(s1[150:200], s2[150:200])) > 0.1   # the two-sided smoother leaks


def test_sliding_default_is_causal():
    x = sims.ar_sim([0.5], 300, seed=5)
    y = list(x[:200]) + [v + 10.0 for v in x[200:]]
    e1, v1 = measure.sliding(x, 40, 1, 1, detrend_bw=10)
    e2, v2 = measure.sliding(y, 40, 1, 1, detrend_bw=10)
    pre = [i for i, e in enumerate(e1) if e < 200]
    assert all(v1[i] == v2[i] for i in pre)


def test_kendall():
    assert measure.kendall_tau(list(range(10))) == 1.0
    assert measure.kendall_tau(list(range(10, 0, -1))) == -1.0


def test_hawkes_rate_and_truth_monotone():
    js = []
    for A in (0.2, 0.6, 0.9):
        t, e = sims.hawkes_sim(A, 1.0, 60000, seed=int(A * 100))
        assert abs(len(t) / t[-1] - 1 / (1 - A)) < 0.08 / (1 - A)
        js.append(sims.hawkes_truth(A, 1.0, t, e)[0])
    assert js[0] > js[1] > js[2] > 0


def test_d2_tracks_hawkes_distance():
    """Planted truth: across A, d2 / bin rises and falls with the exact distance (Spearman 1 on 4 points)."""
    rows = []
    for A in (0.3, 0.7, 0.9, 0.98):
        t, e = sims.hawkes_sim(A, 1.0, 80000, seed=int(A * 1000))
        rows.append((sims.hawkes_truth(A, 1.0, t, e)[0], measure.d2(sims.hawkes_counts(t, 0.5), 10, dt=0.5)["d"]))
    order_t = sorted(range(4), key=lambda i: rows[i][0])
    order_d = sorted(range(4), key=lambda i: rows[i][1])
    assert order_t == order_d


def test_langevin_truth_matches_euler_monte_carlo():
    b, c, dt = 0.0, 0.5, 0.01
    x = sims.langevin_sim(b, c, 1.0, dt, 400000, seed=31)
    dx2 = sum((x[i + 1] - x[i]) ** 2 for i in range(len(x) - 1)) / (len(x) - 1)
    r2 = sum((x[i + 1] - x[i] + (b * x[i] ** 2 + c * x[i] ** 3) * dt) ** 2 for i in range(len(x) - 1)) / (len(x) - 1)
    mc = (0.5 * math.log(dx2 / dt) - 0.5 * r2 / dt + 0.5) / dt
    jt, _ = sims.langevin_truth(b, c, 1.0, dt)
    assert abs(jt - mc) < 0.08 * jt
