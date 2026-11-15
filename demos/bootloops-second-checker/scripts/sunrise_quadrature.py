"""Low-precision outside check of the equal-mass sunrise at one Euclidean point.

In d = 2 with m = mu = 1 and the 1/(i pi^{d/2}) per-loop measure, the Feynman
parameter form of the sunrise with unit propagator powers is
    S_111(2, t) = integral over the simplex x1+x2+x3 = 1 of  1 / F,
    F = (x1 + x2 + x3)(x1 x2 + x2 x3 + x3 x1) - t x1 x2 x3,
and the page's convention is J_111 = -S_111. This script integrates that form
with mpmath quadrature and compares with the published value at t = -3.

This is NOT a derivation of the closed form and NOT research-scale: it is a
standard textbook parametrization evaluated to a modest number of digits.
The convention mapping above is from the literature, and a mismatch would
first point at the mapping, not at the published result.
"""
import sys

import mpmath as mp

PUBLISHED_T_MINUS_3 = ("-2.0589766979254918724182799691488449049958852132591171652425844676811576183594946409331691857618941814230305619")


def S111(t, dps=30):
    mp.mp.dps = dps

    def integrand(u, v):
        # x1 = u, x2 = (1-u) v, x3 = (1-u)(1-v); Jacobian (1-u)
        x1, x2, x3 = u, (1 - u) * v, (1 - u) * (1 - v)
        F = (x1 * x2 + x2 * x3 + x3 * x1) - t * x1 * x2 * x3  # x1+x2+x3 = 1
        return (1 - u) / F

    return mp.quad(integrand, [0, 1], [0, 1])


if __name__ == "__main__":
    dps = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    J = -S111(mp.mpf(-3), dps)
    mp.mp.dps = dps + 10  # compare with 10 guard digits so agreement is a number, not "inf"
    pub = mp.mpf(PUBLISHED_T_MINUS_3)  # parsed after dps is set
    agree = -mp.log10(abs(J - pub) / abs(pub))
    print(f"J(-3) quadrature at dps={dps}: {mp.nstr(J, dps)}")
    print(f"published:                   {mp.nstr(pub, dps)}")
    print(f"agreement: {mp.nstr(agree, 4)} digits")
