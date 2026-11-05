"""Planted-truth models for checking d2 (the paper's SI 3.2 and 3.3), standard library only.

AR(n): truth is core.d_beta of the true kernel at the fitted order.
Hawkes: lambda(t) = mu + A sum_{t_i < t} exp(-(t - t_i)), critical at A = 1. Truth: the KL rate per unit time to
  the nearest critical Hawkes (1, mu_c), mu_c optimised exactly, from the point-process likelihood on the
  simulated trajectory.
Langevin: dx = -(b x^2 + c x^3) dt + sigma dW, Euler step dt, critical only at b = c = 0. Truth (sigma_c
  optimised): ln(1 + dt E[f^2] / sigma^2) / (2 dt) per unit time, E over the stationary density by quadrature.
"""
from __future__ import annotations

import math
import random


def ar_sim(phi, T, seed, sigma=1.0, burn=1000):
    rng = random.Random(seed)
    phi = [float(v) for v in phi]
    n = len(phi)
    buf = [0.0] * n
    out = []
    for t in range(T + burn):
        v = sum(phi[j] * buf[-1 - j] for j in range(n)) + rng.gauss(0.0, sigma) if n else rng.gauss(0.0, sigma)
        if n:
            buf = buf[1:] + [v]
        if t >= burn:
            out.append(v)
    return out


def hawkes_sim(A, mu, K, seed):
    """Exact simulation (Dassios and Zhao 2013, exponential kernel, decay 1).

    Returns spike times and e_i = sum_{j<i} exp(-(t_i - t_j)) just before each spike."""
    rng = random.Random(seed)
    t = e = 0.0
    times, epre = [], []
    for _ in range(K):
        s1 = -math.log(1.0 - rng.random()) / mu
        s2 = math.inf
        if A * e > 0.0:
            d = 1.0 + math.log(1.0 - rng.random()) / (A * e)
            if d > 0.0:
                s2 = -math.log(d)
        else:
            rng.random()
        tau = min(s1, s2)
        t += tau
        e *= math.exp(-tau)
        times.append(t)
        epre.append(e)
        e += 1.0
    return times, epre


def hawkes_counts(times, dt_bin):
    nb = int(times[-1] // dt_bin)
    c = [0.0] * nb
    for t in times:
        i = int(t // dt_bin)
        if i < nb:
            c[i] += 1.0
    return c


def hawkes_truth(A, mu, times, epre):
    """Nats per unit time from Hawkes(A, mu) to the nearest critical Hawkes(1, mu_c). Returns (J, mu_c)."""
    T = times[-1]
    S = sum(1.0 - math.exp(-(T - t)) for t in times)

    def dJ(m):
        return T - sum(1.0 / (m + e) for e in epre)

    lo, hi = 1e-12, 1e6
    if dJ(lo) > 0:
        muc = lo
    else:
        for _ in range(200):
            mid = math.sqrt(lo * hi)
            lo, hi = (mid, hi) if dJ(mid) < 0 else (lo, mid)
        muc = math.sqrt(lo * hi)
    ll = sum(math.log((mu + A * e) / (muc + e)) for e in epre)
    return (ll - mu * T - A * S + muc * T + S) / T, muc


def langevin_sim(b, c, sigma, dt, n, seed, burn=20000):
    rng = random.Random(seed)
    v = -b / c if c > 0 else 0.0
    s = sigma * math.sqrt(dt)
    out = []
    for i in range(n + burn):
        v = v - (b * v * v + c * v * v * v) * dt + s * rng.gauss(0.0, 1.0)
        if i >= burn:
            out.append(v)
    return out


def langevin_truth(b, c, sigma, dt, npts=200001):
    """Truth in nats per unit time for the Euler chain at step dt, and its dt -> 0 limit E[f^2] / (2 sigma^2)."""
    scale = max((sigma ** 2 / c) ** 0.25, abs(b / c)) if c > 0 else 1.0
    lo, hi = -12 * scale - abs(b / c), 12 * scale + abs(b / c)
    h = (hi - lo) / (npts - 1)
    xs = [lo + i * h for i in range(npts)]
    lp = [-2 * (b * x ** 3 / 3 + c * x ** 4 / 4) / sigma ** 2 for x in xs]
    m = max(lp)
    p = [math.exp(v - m) for v in lp]
    w = [0.5 if i in (0, npts - 1) else 1.0 for i in range(npts)]
    Z = sum(wi * pi for wi, pi in zip(w, p))
    f2 = sum(wi * pi * (b * x * x + c * x ** 3) ** 2 for wi, pi, x in zip(w, p, xs)) / Z
    return math.log1p(dt * f2 / sigma ** 2) / (2 * dt), f2 / (2 * sigma ** 2)
