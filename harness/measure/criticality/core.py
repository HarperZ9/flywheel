"""Distance to criticality d_beta for autoregressive models: the exact closed form, standard library only.

Definition (Sooter et al. 2026, PNAS 123(44) e2526984123, CC BY 4.0): an order-n AR model
x_t = sum_j phi_j x_{t-j} + xi_t flows into the temporal-RG fixed point beta (2, 4, ...) when its polynomial
B(z) = 1 - sum_j phi_j z^j has a root of multiplicity beta / 2 at z = 1. d_beta(A) is the minimum KL divergence
rate J(A||B) over critical AR models B of the same order, with
    J(A||B) = (1/4pi) int [ln(gA/gB) + gB/gA - 1] dw,   g(w) = |1 - phi~(w)|^2 / (2 pi sigma)^2.

Closed form used here. With sigma_B at its optimum, J = 0.5 ln(b' Gamma_A b), where b = (1, -phi_B) and Gamma_A
is the autocovariance of the unit-noise AR(A) process: the log-integral of a minimum-phase polynomial is zero
(Jensen). Writing B(z) = (1 - z)^k C(z), k = beta / 2, b' Gamma_A b is the variance of C(L) applied to the k-times
differenced process, so its minimum over C (c_0 = 1, degree n - k) is the order-(n - k) one-step prediction error
variance of that process. Yule-Walker on a valid autocovariance gives a minimum-phase C, so the minimiser is
feasible and the value is the exact minimum. tests/test_measure_criticality.py checks it against a direct
numerical minimisation of the integral over the paper's own parameterisation.
"""
from __future__ import annotations

import math

LN2 = math.log(2.0)


def solve(A, b):
    """Gaussian elimination with partial pivoting on small dense systems."""
    n = len(b)
    M = [list(map(float, row)) + [float(v)] for row, v in zip(A, b)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-300:
            raise ValueError("singular system")
        M[c], M[p] = M[p], M[c]
        for r in range(c + 1, n):
            f = M[r][c] / M[c][c]
            if f:
                for j in range(c, n + 1):
                    M[r][j] -= f * M[c][j]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (M[r][n] - sum(M[r][j] * x[j] for j in range(r + 1, n))) / M[r][r]
    return x


def is_stationary(phi, tol=0.0):
    """True when every root of 1 - sum phi_j z^j lies strictly outside the unit circle.

    Step-down (Schur-Cohn) recursion: stationary iff every reflection coefficient has |k| < 1."""
    a = [float(v) for v in phi]
    while a and a[-1] == 0.0:
        a.pop()
    while a:
        k = a[-1]
        if abs(k) >= 1.0 - tol:
            return False
        m = len(a) - 1
        d = 1.0 - k * k
        a = [(a[j] + k * a[m - 1 - j]) / d for j in range(m)]
    return True


def ar_acov(phi, sigma2=1.0, maxlag=None):
    """Exact autocovariance gamma(0..maxlag) of a stationary AR(phi) with innovation variance sigma2."""
    phi = [float(v) for v in phi]
    n = len(phi)
    maxlag = n if maxlag is None else maxlag
    if n == 0:
        return [float(sigma2)] + [0.0] * maxlag
    M = [[1.0 if i == j else 0.0 for j in range(n + 1)] for i in range(n + 1)]
    for h in range(n + 1):
        for j in range(1, n + 1):
            M[h][abs(h - j)] -= phi[j - 1]
    g = solve(M, [float(sigma2)] + [0.0] * n)
    while len(g) < maxlag + 1:
        g.append(sum(phi[j] * g[-1 - j] for j in range(n)))
    return g[: maxlag + 1]


def diff_acov(gamma, k):
    """Autocovariance of the k-times differenced process from gamma(0..L); lags 0..L-k."""
    d = [1.0]
    for _ in range(k):
        d = [a - b for a, b in zip(d + [0.0], [0.0] + d)]
    L = len(gamma) - 1

    def g(h):
        return gamma[abs(h)]

    return [sum(d[i] * d[j] * g(h + i - j) for i in range(k + 1) for j in range(k + 1)) for h in range(L - k + 1)]


def levinson(gamma, m):
    """Order-m Yule-Walker predictor (Levinson-Durbin). Returns (coefficients a_1..a_m, prediction error variance)."""
    if m == 0:
        return [], float(gamma[0])
    a, e = [], float(gamma[0])
    for i in range(1, m + 1):
        acc = gamma[i] - sum(a[j] * gamma[i - 1 - j] for j in range(i - 1))
        k = acc / e
        a = [a[j] - k * a[i - 2 - j] for j in range(i - 1)] + [k]
        e *= 1.0 - k * k
        if e <= 0.0:
            raise ValueError("autocovariance is not positive definite at this order")
    return a, e


def d_beta(phi, beta=2):
    """Distance in nats per step from AR(phi) to the beta critical manifold of AR models of the same order.

    Returns (d_nats, phi_closest). Raises ValueError for a non-stationary kernel or beta / 2 above the order."""
    phi = [float(v) for v in phi]
    n, k = len(phi), beta // 2
    if beta < 2 or beta % 2:
        raise ValueError("beta must be an even integer >= 2")
    if k > n:
        raise ValueError(f"beta {beta} needs AR order >= {k}")
    if not is_stationary(phi):
        raise ValueError("kernel is not stationary (a root on or inside the unit circle)")
    gd = diff_acov(ar_acov(phi, 1.0, n + k), k)
    a, pev = levinson(gd, n - k)
    b = [1.0] + [-v for v in a]
    for _ in range(k):
        b = [x - y for x, y in zip(b + [0.0], [0.0] + b)]
    return 0.5 * math.log(pev), [-v for v in b[1:]]


def d_beta_bits(phi, beta=2):
    return d_beta(phi, beta)[0] / LN2


def white_noise_bits(order):
    """d2 of white noise at AR order n: 0.5 log2((n + 1) / n) bits per step."""
    return 0.5 * math.log2((order + 1) / order)


def kl_rate(phiA, s2A, phiB, s2B, npts=1 << 14):
    """KL divergence rate J(A||B), nats per step, by midpoint quadrature of the paper's integral.

    An independent check of d_beta. The integrand has a log singularity where gB vanishes, so the midpoint rule
    carries a bias of about 0.7 / npts nats."""
    tot = 0.0
    for i in range(npts):
        w = (i + 0.5) * 2 * math.pi / npts - math.pi
        gA, gB = _g(phiA, s2A, w), _g(phiB, s2B, w)
        r = gA / gB
        tot += math.log(r) + 1.0 / r - 1.0
    return tot / npts / 2.0


def _g(phi, s2, w):
    re = 1.0 - sum(p * math.cos(w * (t + 1)) for t, p in enumerate(phi))
    im = sum(p * math.sin(w * (t + 1)) for t, p in enumerate(phi))
    return (re * re + im * im) / ((2 * math.pi) ** 2 * s2)
