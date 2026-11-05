# Criticality: how close a time series runs to the edge

`harness.measure.criticality` measures d2, the distance from a series to the nearest critical model, in bits per
step. Near 0, the series sits at a tipping point: slow, scale-free fluctuations, the edge between stable and
unstable. Large means the series forgets fast. The number reads as distinguishability: how many bits per step an
observer gains toward "this is the fitted model, not a critical one".

It works on one univariate series: a learning curve, a population rate, a latency trace, a count per bin. It needs
no knowledge of the system's control parameters.

## Run it

```python
from harness.measure.criticality import d2, sliding, kendall_tau

r = d2(series, order=5)              # r["d"]: bits per step; r["phi_c"]: nearest critical kernel
r = d2(counts, order=10, dt=0.5)     # per unit time, for counts in bins of 0.5
r = d2(series, order=1, fit="ols", err=True)   # with the delta-method standard error, r["se"]

ends, vals = sliding(series, win=30, step=1, order=1, detrend_bw=10)   # time-resolved d2
kendall_tau(vals[-15:])              # a falling trend is the early-warning reading
```

Every result carries `scope`: the KL rate to the nearest critical AR model of the same order, under a Gaussian AR
fit of the series. Standard library only.

## The method

Source: Sooter, Fontenele, Barreiro, Ly, Hengen and Shew 2026, "Defining and measuring proximity to criticality
based on univariate time series", PNAS 123(44) e2526984123, CC BY 4.0.

1. Fit an order-n autoregressive model to the z-scored series (Yule-Walker by default).
2. Temporal renormalisation sorts AR models by the low-frequency exponent beta of
   g(w) = |1 - phi~(w)|^2 / (2 pi sigma)^2. The beta = 2 critical models are those with sum(phi) = 1; beta = 4
   adds a vanishing first moment, and so on.
3. d_beta is the minimum KL divergence rate from the fitted model to a critical model of the same order.

The paper minimises that rate numerically. This package uses an exact closed form, derived here: with the critical
model's noise at its optimum, the rate is half the log of the order-(n - beta/2) prediction error variance of the
(beta/2)-times differenced fitted process. The tests check it against a direct numerical minimisation of the
paper's integral over the paper's own parameterisation, and check that a formula without the differencing fails.

This is a clean-room implementation from the paper's equations. The authors' MATLAB toolkit is licensed CC BY-NC
4.0; it was read to check conventions and was neither copied nor run.

## Benchmarks

The paper's ground-truth models, each with a truth computed apart from the AR fit, run under a preregistered study
with forecasts hashed before the power simulations. 13 of 13 verdicts passed:

| Model | Truth | Result |
|---|---|---|
| AR(1), phi 0 to 0.999, 50 series of 10^4 | closed form | worst miss 0.010 in log10 up to phi 0.99; error-bar coverage 0.954 |
| White noise, order 5 | 0.5 log2(6/5) = 0.1315 | median 0.1317, cv 0.029 |
| Hawkes, critical at A = 1, 10^6 spikes | exact likelihood ratio | log r^2 0.992; d2 reads 0.91 of the truth |
| Langevin in a quartic potential, critical at b = c = 0 | quadrature | linear r^2 0.990 (paper: 0.95), log r^2 0.968; d2 reads 0.72 of the truth |
| Bursty (CIR), critical at b = 0 | Monte Carlo likelihood ratio | overestimates 10.7 x at the burstiest setting, agrees (0.89) when not bursty |

The last row reproduces the paper's stated limit: on silence-separated bursts an AR model fits badly and d2 reads
too high. With every series shuffled in time, the tracking verdicts passed 0 or 1 time in 10.

## Reading d2 as an early warning

Critical slowing down predicts that d2 falls before a switch a system makes itself. Read it in windows that end
before the event, and detrend with the past only. `sliding` does that by default (`detrend_mode="causal"`).

The default matters. On one learning-curve study, a two-sided smoother produced a pre-leap fall in d2 (p 0.018)
that vanished under a past-only detrend (p 0.175), while the same past-only pipeline still found a planted slowing
down and stayed quiet on its twin without the slowing. A two-sided smoother lets the event itself leak into the
residuals before it. Use `detrend_mode="gaussian"` only for whole-series summaries.

## Choices that set the scale

- Order and bin. For counts, d2 depends on the reach, order times bin (SI section 4). Compare readings only at
  equal reach.
- Detrending removes slow drift, so d2 then reads fluctuations around it. A smoother also shifts the white-noise
  reference; read it through the same pipeline before calling a series white.
- Short series. At 160 points d2 recovered planted AR(1) truths within 0.05 in log10; windows of 20 to 30
  points need many events before a trend is readable.

Verified: the benchmark values above were read from the study's scored result by the study runner; the unit tests
in `tests/test_measure_criticality.py` pass, including the comparison with numerical minimisation.
