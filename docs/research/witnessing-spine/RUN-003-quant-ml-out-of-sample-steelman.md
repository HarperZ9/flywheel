# Does Machine Learning Reliably Beat Classical Methods Out-of-Sample in Finance?

### An adversarial steelman — the honest decomposition: where ML adds real value, where "reliably beats" is an artifact of methodology, microcaps, costs, and the overfitting surface, and where the literature genuinely disagrees.

**Author:** Zain Dana Harper — independent researcher, Seattle · github.com/HarperZ9 · ORCID 0009-0001-7175-5393
**Date:** 2026-06-20
**Run:** 003 — Frontier Research Session
**Rotation focus:** ML + algorithmic/quant methods (q-fin) × financial-sector engineering.
**Part of:** *The Witnessing Spine* corpus · CC-BY-4.0 · companion [*Conferred Existence*](https://doi.org/10.5281/zenodo.20773724)
**Discipline:** claim ↔ evidence ↔ verdict; sources verified by retrieval; maturity labeled; nothing fabricated; the genuine pro/con disagreement is represented, not collapsed.
**Method:** four parallel web-grounded scholar agents (≈205 tool-calls; ~75 verified sources across *J. Finance*, *RFS*, *J. Financial Econometrics*, *Management Science*, *JFE*, *J. Computational Finance*, arXiv q-fin/cs.LG, SSRN, NBER, S&P SPIVA) → author synthesis and adjudication.

---

## 0 · Bottom line

The claim *"deep learning / modern ML reliably beats classical methods out-of-sample in financial prediction"* is **overclaimed and task-dependent**. The verifiable decomposition:

- **ML genuinely adds value in specific tasks** — capturing nonlinear characteristic interactions in cross-sectional asset pricing (Gu-Kelly-Xiu, replicated), intraday volatility with cross-sectional pooling (Zhang et al., *J. Fin. Econometrics* 2024), and short-horizon prediction on large-tick liquid order books (Briola et al.). This is real, peer-reviewed, and not noise.
- **But "reliably beats" fails on five fronts, each grounded:** (1) the headline edges **concentrate in microcaps/illiquid names** the authors themselves call unscalable and **die to transaction costs**; (2) the canonical "DL beats HAR" result is largely a **rigged comparison** — equalize the fitting methodology and **HAR dominates all ML on 1,455 stocks, with neural nets the *worst* performers**; (3) LOB "predictability" is a **benchmark-monoculture artifact** that collapses ~21 F1 points out-of-sample and below break-even under costs, with the authors stating it is "not sufficiently mature for live trading"; (4) ML **multiplies the backtest-overfitting surface** by orders of magnitude (the probability of backtest overfitting → 1 as trials → ∞); and (5) **edges decay** post-publication (~58%) and most of the factor zoo fails at conservative thresholds — though this last point is **genuinely contested**.

**Verdict (§3): FALSE as stated; TRUE in a narrow, honest restatement.** ML adds *small, fragile, cost- and regime-sensitive* value concentrated exactly where it is hardest to harvest (microcaps; low-cost operators), and the apparent edge is *systematically inflated* by methodology, costs, multiple testing, and the overfitting surface. The binding problem is not "can a model fit" — it is **honest out-of-sample / live evidence under non-stationarity and the multiple-testing burden**: deflated, trial-counted, coverage-accounted, MATCH/DRIFT/UNVERIFIABLE evidence. That is proof-before-trust applied to alpha — the exact discipline that separates a quant from a backtester.

---

## 1 · Why this frontier matters

This closes the financial-ML thread opened across Runs 001–002. Quantitative finance is among the most consequential ML applications and the one most saturated with overclaiming; command of the *adversarial* literature (deflated Sharpe, PBO, replication, cost-aware comparison) is what separates a defensible result from a backtest — and it rhymes with the verification spine of the prior runs.

---

## 2 · The evidence

### 2.1 Where ML genuinely wins (peer-reviewed, with numbers)

- **Cross-sectional asset pricing — nonlinear interactions.** Gu, Kelly & Xiu (RFS 2020): on ~30,000 US stocks, 920 features, **unpenalized OLS → negative OOS R²**, while penalized linear and neural nets recover **monthly OOS R² ≈ 0.33–0.40%** and a long-short Sharpe of **2.45 (equal-weighted) / 1.35 (value-weighted)** vs ~**0.61** for penalized linear. The gain is structural — trees/NNs capture nonlinear predictor interactions linear models miss; replicated by Freyberger-Neuhierl-Weber (nonparametric), Chen-Pelger-Zhu (*Manag. Sci.* 2024, no-arbitrage deep learning outperforms benchmarks OOS on Sharpe/R²/pricing errors), Gu-Kelly-Xiu autoencoder. `[peer-reviewed]`
- **Market timing (time-series).** Kelly-Malamud-Zhou "Virtue of Complexity" (*J. Finance* 2024): overparameterized models give **~0.47 annualized OOS Sharpe** improvement, t≈3; divests before 14/15 recessions OOS. `[peer-reviewed]`
- **Intraday volatility.** Zhang-Zhang-Cucuringu-Qian (*J. Fin. Econometrics* 2024): LSTM beats OLS by **~16% QLIKE at 30-min** horizon (MCS-confirmed) — *but at the 1-day horizon, linear models win.* `[peer-reviewed]`
- **Large-tick liquid LOB.** Briola-Bartolucci-Aste (2403.09267): genuine short-horizon signal (MCC ~0.29–0.36) **only** on large-tick, liquid stocks. `[preprint]`

### 2.2 Where "reliably beats" fails

**(a) The edge lives in microcaps and dies to costs.** GKX's own caveat: the EW 2.45 "may be impossible at scale" (microcap-concentrated); the implementable VW 1.35 falls further when microcaps are excluded (Avramov-Cheng-Metzker, *Manag. Sci.* 2023: profitability "considerably attenuated" excluding microcaps/distressed/high-vol). Costs: Azevedo-Hoegner-Velikov — **13–40% gross-to-net haircut**, a **57%** joint reduction with decay+decimalization (best LSTM survives at net Sharpe ~0.84, but the *average* model does not); Detzel-Novy-Marx-Velikov (*J. Finance* 2023): **transaction costs reverse model rankings** — a gross-dominant factor delivers **negative net Sharpe**. Lalwani-Meshram-Jindal (*Eur. Fin. Manag.* 2025): across **5,376 portfolios, nonstandard errors up to 5× standard errors; only ~1/3 significant after costs.** `[peer-reviewed]`

**(b) "DL beats HAR" is often a rigged comparison.** Audrino & Chassot (2406.08041): on **1,455 US stocks**, once HAR is given the same rolling-window care as the ML models (≈630-day window, daily re-estimation), **HAR (WLS) dominates Lasso, RF, GBT, and FFNN on MSE and QLIKE** — FFNNs the **worst** (QLIKE ~0.48–0.57 vs HAR ~0.31; in the QLIKE MCS for **85.5%** of assets vs FFNN **~36%**). Much of the published DL-beats-HAR result is an artifact of a statically-fit benchmark. `[preprint, methodologically rigorous]`

**(c) LOB predictability is a benchmark-monoculture artifact.** Prata et al. (*AI Review* 2024): the best FI-2010 model (BINCTABL **82.6% F1**) collapses to **~59–61% F1** on real LOBSTER 2021/2022 data (**−21 pp**); the more a model is tuned to FI-2010 the harder it falls; simple CNN baselines barely move. TLOB (2502.15757): **92.8% F1 on FI-2010 but 39.8% on NASDAQ Tesla**, dropping to **30.8% at h=200 once average spread (a real cost) defines the trend** — and the authors state the models are **"not sufficiently mature for practical deployment in live trading."** Queue position, latency, and adverse selection are **unmodeled across the academic literature**. `[A/preprint]`

**(d) ML explodes the overfitting surface.** Bailey-Borwein-López de Prado-Zhu: the **Probability of Backtest Overfitting (PBO)** via combinatorial cross-validation rises **monotonically → 1** as the number of trials grows; the **Deflated Sharpe Ratio** corrects a reported Sharpe for trial count + non-normality. A single LSTM strategy embeds hundreds-to-hundreds-of-thousands of implicit trials (architecture × hyperparameters × features × windows), so the effective N is orders larger than for a rule-based backtest — and feature selection from a 200-indicator menu is itself a 200-hypothesis test. Backtest ≠ live: implementation risk alone (2603.20319) produces **3.71 pp** cross-engine divergence with costs and **7 previously-undocumented engine defects**; regime dependence is stark (Oxford-Man 2603.01820: a VLSTM backtests at Sharpe **2.40** but an LSTM hits a worst annual **−1.51**). `[peer-reviewed / preprint]`

**(e) Edges decay; much of the zoo is fragile.** McLean-Pontiff (*J. Finance* 2016): published predictors decay **26% OOS / 58% post-publication** (the 32 pp gap = arbitrage). Hou-Xue-Zhang (RFS 2020): of **452 anomalies, 64–65% fail t>1.96** (value-weighted, NYSE breakpoints), **82–85% fail t>2.78**, **96%** of trading-friction anomalies fail. Harvey-Liu-Zhu: **316 factors → require t>3.0**; Chordia-Goyal-Saretto: **t>3.4–3.8** from 2M simulated strategies. `[peer-reviewed]`

### 2.3 The genuine disagreement (represented, not flattened)

The pessimist reading is *contested by serious researchers using the same data*:
- **Jensen-Kelly-Pedersen (*J. Finance* 2023):** most of **153** factors **replicate**, cluster into **13 themes** (mostly significant in the tangency portfolio), work in **93 countries**, and *gain* evidential strength from the factor count under a Bayesian prior — "the frequentist crisis is overstated."
- **Chen-Zimmermann (2022/23):** publication-bias-corrected **false-discovery rate <10%**, shrinkage only **10–15%** of in-sample returns — far below what HXZ implies; and a **98%** code/data reproducibility rate (a different question than economic survival).
- **Jacobs-Müller (*JFE* 2020):** reliable post-publication decay is essentially **US-only** (241 anomalies, 39 markets) — consistent with limits-to-arbitrage, not pure data-mining.
- **The learning-limits debate is live:** Fallahgoul (2506.03780) argues ML "wins" are low-complexity artifacts (e.g., momentum) under information-theoretic limits; Chen-Kelly-Malamud (2512.12735) rebut that standard ML *understates* predictability. Both preprints, unresolved.

**Honest synthesis:** a substantial fraction of anomalies fail conservative replication; survivors cluster into a smaller set of real themes; ML adds genuine nonlinear value on those themes. "Most are false" and "ML reliably beats classical" are *both* overstatements of a contested middle.

### 2.4 Meta-evidence (humbling)

- **SPIVA US YE-2024:** over **15 years, 0 of 22** US equity fund categories had a majority of active managers beat their benchmark (large-cap active >90% underperform). (Covers active broadly, not systematic-ML specifically — but it is the population-level prior.) `[index-provider]`
- **Survivorship/backfill bias** (Fung-Hsieh 2000): ~**300 bps/yr** survivorship + **1.4%/yr** backfill — enough to roughly halve naive reported hedge-fund averages; **no clean public bias-corrected index of "ML equity long-short" exists.**
- **The one unambiguous ML triumph is uninvestable and unexplained:** Medallion **63.3% CAGR (1988–2018), no negative year** — but **closed to outsiders since 1993, capacity-capped ~$10B, and admittedly unexplained** (Cornell Capital 2020). It is the counterexample to efficiency, not evidence that the claim generalizes to investable capital. RenTec's *external* funds returned 22.7%/15.6% in 2024 — strong, not Medallion. `[practitioner]`

---

## 3 · The adversarial steelman (claim ↔ evidence ↔ verdict)

> **CLAIM (strongest form).** *Deep learning / modern ML reliably beats classical methods out-of-sample in financial prediction — return forecasting, volatility, and order-book signals — and is the new state of the art for systematic investing.*

**Evidence FOR (steelmanned, real).** GKX's nonlinear cross-sectional gain is replicated and structural; Chen-Pelger-Zhu and Kelly-Malamud-Zhou add peer-reviewed OOS wins; intraday vol and large-tick LOB show genuine MCS-confirmed DL edges; JKP/Chen-Zimmermann show the underlying signals are mostly real, giving ML real material to aggregate. `[verified]`

**Evidence AGAINST (decisive on "reliably beats").**
1. The wins **concentrate in microcaps** (unscalable by the authors' own admission) and **invert after costs** (Detzel; 13–40% haircut; ~1/3 survive; 5× nonstandard errors). `[verified]`
2. The flagship "DL beats HAR" claim **reverses under a fair fight** — HAR dominates all ML on 1,455 stocks, NNs worst (Audrino-Chassot). `[verified]`
3. LOB "predictability" **collapses ~21 F1 pts OOS and below break-even under costs**, "not mature for live trading" per the authors; queue/latency unmodeled. `[verified]`
4. ML **multiplies the overfitting surface** (PBO→1; deflated-Sharpe correction large); backtest ≠ live (implementation 3.71pp; regime worst-Sharpe −1.51). `[verified]`
5. Edges **decay** (58% post-pub) and the zoo is fragile at conservative thresholds — *contested* (JKP optimism), so this leg is a *tie-breaker, not a knockout*. `[verified, contested]`

> **VERDICT — FALSE AS STATED; TRUE ONLY IN A NARROW RESTATEMENT.** "Reliably beats" is refuted: the edge is **small, fragile, task-specific, cost- and regime-sensitive, and concentrated where it is hardest to harvest.** The defensible claim: *ML adds measurable nonlinear value in specific tasks (cross-sectional pricing, intraday vol, large-tick LOB), but the apparent magnitude is systematically inflated by microcap concentration, omitted costs, rigged baselines, the multiple-testing/overfitting surface, and non-stationarity — and net, live, value-weighted, at capacity, it is a thin and decaying premium that most operators cannot capture.* The population prior (SPIVA 0/22; the lone triumph closed and unexplained) caps the credible upside.

---

## 4 · The through-line — proof-before-trust applied to alpha

This rotation is more epistemic than build-a-tool, but the spine is identical to Runs 001–002: the binding constraint is **honest out-of-sample/live evidence under non-stationarity and the multiple-testing burden.** The witnessing discipline is the antidote to backtest overfitting — *trial-counted* (deflated-Sharpe/PBO accounting of how many configurations produced a result), *coverage-accounted* (which regimes/instruments are witnessed vs UNVERIFIED), *cost- and capacity-honest*, and skeptical-of-the-attestor (here, the backtester). A research/diligence harness that scores a claimed strategy on **MATCH / DRIFT / UNVERIFIABLE** against live-equivalence — deflating for trials, costs, microcap reliance, and regime coverage — is the same organism as the provenance witness (Run 001) and the equivalence harness (Run 002), pointed at alpha. Three rotations, one spine.

---

## 5 · Open problems / next-run candidates

1. **A deflated, coverage-accounted strategy-diligence protocol** — formalize "MATCH/DRIFT/UNVERIFIABLE on live-equivalence" combining DSR/PBO + cost model + microcap/capacity test + regime-coverage ledger. Converges with Runs 001–002 on the witnessing spine.
2. **Resolve the FI-2010 monoculture** — a cost-and-latency-aware LOB benchmark across markets/years (the field's reproducibility hole).
3. **The learning-limits question** (Fallahgoul vs Chen-Kelly-Malamud) — is the ML premium genuine high-dimensional learning or a momentum/low-complexity artifact?
4. **Next rotation:** **blockchain / crypto-economics** (uncovered) — e.g., steelman "DeFi/AMM design or on-chain ML yields a robust, defensible edge," or MEV/oracle-manipulation security — to open the last untouched financially-rewarding stratum.

---

## 6 · Consolidated verified source ledger (selected)

| # | Source | ID / URL | Date | Maturity |
|---|---|---|---|---|
| 1 | Gu, Kelly & Xiu — Empirical Asset Pricing via ML | RFS 33(5); NBER w25398 | 2020 | peer-reviewed |
| 2 | Chen, Pelger & Zhu — Deep Learning in Asset Pricing | Manag. Sci. 70(2); arXiv:1904.00745 | 2024 | peer-reviewed |
| 3 | Kelly, Malamud & Zhou — Virtue of Complexity | J. Finance, DOI 10.1111/jofi.13298 | 2024 | peer-reviewed |
| 4 | Freyberger, Neuhierl & Weber — Dissecting Characteristics Nonparametrically | RFS 33(5) | 2020 | peer-reviewed |
| 5 | Avramov, Cheng & Metzker — ML vs Economic Restrictions | Manag. Sci. 69(5) | 2023 | peer-reviewed |
| 6 | Lalwani, Meshram & Jindal — Role of Research Design Choices | Eur. Fin. Manag., 10.1111/eufm.70033 | 2025 | peer-reviewed |
| 7 | Azevedo, Hoegner & Velikov — Expected Returns on ML Strategies | SSRN 4702406 | 2024 | working paper |
| 8 | Detzel, Novy-Marx & Velikov — Model Comparison with Transaction Costs | J. Finance 78(3) | 2023 | peer-reviewed |
| 9 | Audrino & Chassot — HARd to Beat (rolling windows) | arXiv:2406.08041 | Jun 2024 | preprint |
| 10 | Zhang, Zhang, Cucuringu & Qian — Vol Forecasting + Intraday Commonality | J. Fin. Econometrics 22(2) | 2024 | peer-reviewed |
| 11 | Prata et al. — LOB DL Benchmark Study | AI Review; arXiv:2308.01915 | 2024 | peer-reviewed |
| 12 | Berti & Kasneci — TLOB | arXiv:2502.15757 | 2025 | preprint |
| 13 | Briola, Bartolucci & Aste — Deep LOB Forecasting: Microstructural Guide | arXiv:2403.09267 | 2024 | preprint |
| 14 | Harvey, Liu & Zhu — …and the Cross-Section of Expected Returns | RFS 29(1); NBER w20592 | 2016 | peer-reviewed |
| 15 | Hou, Xue & Zhang — Replicating Anomalies | RFS 33(5); NBER w23394 | 2020 | peer-reviewed |
| 16 | Chordia, Goyal & Saretto — Anomalies and False Rejections | RFS 33(5) | 2020 | peer-reviewed |
| 17 | McLean & Pontiff — Does Academic Research Destroy Predictability? | J. Finance 71(1) | 2016 | peer-reviewed |
| 18 | Bailey, Borwein, López de Prado & Zhu — Probability of Backtest Overfitting | J. Comp. Finance 20(4); SSRN 2326253 | 2017 | peer-reviewed |
| 19 | Bailey & López de Prado — Deflated Sharpe Ratio | J. Portfolio Mgmt 40(5); SSRN 2460551 | 2014 | peer-reviewed |
| 20 | Harvey & Liu — False (and Missed) Discoveries | J. Finance 75(5); arXiv:2006.04269 | 2020 | peer-reviewed |
| 21 | Jensen, Kelly & Pedersen — Is There a Replication Crisis in Finance? | J. Finance 78(5); NBER w28432 | 2023 | peer-reviewed |
| 22 | Chen & Zimmermann — Publication Bias in Asset Pricing | arXiv:2209.13623; Crit. Fin. Review | 2022/23 | working paper |
| 23 | Chen & Zimmermann — Open Source Cross-Sectional Asset Pricing | Crit. Fin. Review 11(2); openassetpricing.com | 2022 | peer-reviewed |
| 24 | Jacobs & Müller — Anomalies Across the Globe | JFE 135(1) | 2020 | peer-reviewed |
| 25 | Yin et al. — Implementation Risk in Portfolio Backtesting | arXiv:2603.20319 | Mar 2026 | working paper |
| 26 | Saly-Kaufmann et al. — Oxford-Man DL benchmark (futures) | arXiv:2603.01820 | Mar 2026 | working paper |
| 27 | Fung & Hsieh — Natural vs Spurious Biases | JFQA 35(3) | 2000 | peer-reviewed |
| 28 | SPIVA US Year-End 2024 | spglobal.com/spdji | 2025 | index-provider |
| 29 | Cornell Capital — Medallion: Ultimate Counterexample | cornell-capital.com | 2020 | practitioner |
| 30 | Lommers, El Harzli & Kim — Confronting ML with Financial Research | arXiv:2103.00366 | 2021 | preprint |
| 31 | Fallahgoul — High-Dimensional Learning in Finance | arXiv:2506.03780 | 2025 | preprint |
| 32 | Chen, Kelly & Malamud — Limits To (Machine) Learning | arXiv:2512.12735 | 2025 | preprint |
| 33 | Nagy et al. — LOB-Bench (generative LOB) | arXiv:2502.09172 | 2025 | preprint |

---

## 7 · Honest limits of this run

- **The disagreement is real and unresolved.** I did not "pick a side"; the verdict targets the *strong* claim ("reliably beats") while crediting the verified narrow wins and representing the optimist camp (JKP, Chen-Zimmermann) in full.
- **Paywalls.** Many SSRN/Wiley/T&F PDFs returned 403; their numbers come from confirmed abstracts/secondary cross-references and are labeled (e.g., the GKX 2.45/1.35 figures are journal-confirmed via multiple secondary summaries, the Oxford journal page being navigation-only).
- **Withdrawn/very-new preprints flagged and down-weighted** — the crowding-decay paper (2512.11913) was *withdrawn*; the T-KAN 132% return (2601.02310) and the "18-month half-life" SSRN claim are **not** treated as established facts.
- **Backtest ≠ live remains structurally unmeasured** — there is no clean, bias-corrected public record of systematic-ML *live* fund performance; the Medallion datum is practitioner-sourced, not audited.

---

## 8 · Deepen next

- **Next rotation:** blockchain / crypto-economics (the last uncovered stratum) — adversarial steelman of an on-chain/DeFi "edge" or a security claim (MEV, oracle manipulation, AMM design).
- **Carry-forward whitepaper:** §5 #1 — a deflated, coverage-accounted **strategy-diligence harness** (MATCH/DRIFT/UNVERIFIABLE on live-equivalence). This is now the **third** rotation to converge on the same witnessing/proof-before-trust spine (provenance → equivalence → alpha-diligence) — strong evidence the spine is the real, cross-sector contribution.

---

*Run 003 of* The Witnessing Spine *corpus. Claim↔evidence↔verdict; genuine disagreement represented; folklore flagged; limits stated.*
