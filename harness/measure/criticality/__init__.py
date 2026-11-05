"""criticality: distance to criticality (d_beta) for univariate time series, standard library only.

    from harness.measure.criticality import d2, sliding
    r = d2(series, order=5)          # r["d"] in bits per step; r["scope"] names what it covers

Method: Sooter, Fontenele, Barreiro, Ly, Hengen and Shew 2026, "Defining and measuring proximity to criticality
based on univariate time series", PNAS 123(44) e2526984123, CC BY 4.0. This is a clean-room implementation from
the paper's equations. The authors' MATLAB toolkit is CC BY-NC 4.0; it was read to check conventions and was
neither copied nor executed. The closed form for d_beta (core.py) is this package's own derivation.
See docs/features/criticality.md.
"""
from .core import d_beta, d_beta_bits, is_stationary, kl_rate, white_noise_bits
from .measure import SCOPE_D2, d2, detrend, fit_ols, fit_yw, kendall_tau, sliding

__all__ = ["d2", "d_beta", "d_beta_bits", "detrend", "fit_ols", "fit_yw", "is_stationary", "kendall_tau", "kl_rate",
           "sliding", "white_noise_bits", "SCOPE_D2"]
