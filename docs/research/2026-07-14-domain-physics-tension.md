# Domain dossier: physics-tension (2026-07-14)

Method: claims gathered live, then adversarially checked against the cited
sources (full-text search where the claim named specific numbers). Every claim
below carries its source URL and the source's own date inline. Confidence
labels (high/moderate/low) mark non-trivial numbers. Nothing load-bearing is
from model memory without a label.

## 1. The frontier in five sentences

Physics-tension covers the headline disagreements between precision
measurements and standard-theory predictions: muon g-2, the W-boson mass, the
Hubble constant, the S8 lensing amplitude, and DESI's evolving-dark-energy
preference. Between 2024 and 2025 this frontier moved mostly by subtraction:
the muon g-2 anomaly dissolved under theory revision, the CDF W-mass excess
failed replication at matched precision, and the S8 tension shrank to
statistical agreement after a redshift-calibration audit. What remains alive
is narrower than the popular picture: the Hubble discrepancy persists at 5.8
sigma on the SH0ES-versus-Planck axis but lives in calibrator and
supernova-sample choices, and DESI's dark-energy preference sits below
discovery threshold. Every resolution in this window came from re-checking
inputs (lattice QCD versus e+e- data, redshift calibration, independent
replication), not from new physics. For a verified-inference platform this
domain is a natural corpus: claims with explicit uncertainty intervals,
version-pinned sources, and documented expiry dates.

## 2. Confirmed findings

None. Every claim that survived adversarial checking in this pass is a
negative result and is filed under honest nulls below. The domain produced no
confirmed positive finding, meaning no live, replicated, above-threshold
anomaly, in this cycle. That emptiness is itself the domain's signal.

## 3. Honest nulls

These survived verification. They are first-class content: each one is a
widely repeated claim whose current status differs from its popular form.

### 3.1 The muon g-2 anomaly no longer exists

The 4.2-sigma anomaly announced in April 2021 is gone against the current
theory consensus. The final Fermilab measurement is a_mu = 116 592 070.5
(± 11.4 stat ± 9.1 syst) x 10^-11 at 127 ppb, beating the 140 ppb design goal
(high; press release dated June 3, 2025,
https://news.fnal.gov/2025/06/muon-g-2-most-precise-measurement-of-muon-magnetic-anomaly/;
the ± 2.1 external term appears in the PRL submission, not on the press page).
The 2025 Theory Initiative White Paper gives a_mu(SM) = 116 592 033(62) x
10^-11 at 530 ppb, so exp minus SM = 38(63) x 10^-11, about 0.6 sigma (high;
arXiv:2505.21476, v1 May 27, 2025, v3 September 11, 2025,
https://arxiv.org/abs/2505.21476). The measurement was vindicated; the anomaly
died because the lattice-based WP25 prediction sits about 223 x 10^-11 above
the data-driven WP20 value of 116 591 810(43) x 10^-11 (high; CERN Courier,
Jul/Aug 2025 issue, https://cerncourier.com/a/shifting-sands-for-muon-g-2/).
Platform relevance: a claim can be exactly right about the measurement and
wrong about the conclusion when the comparison baseline moves.

### 3.2 The CDF W-mass anomaly failed to replicate

CDF measured 80,433.5 ± 9.4 MeV in 2022, about 7 sigma above the SM fit of
80,357 ± 6 MeV (moderate on exact figures; CDF Collaboration, Science, April
7, 2022, https://www.science.org/doi/10.1126/science.abk1781, DOI slug from
memory). CMS then measured 80,360.2 ± 9.9 MeV, matching CDF's precision and
agreeing with the SM, ATLAS, and LHCb (high; CMS news page dated September
17, 2024,
https://cms.cern/news/cms-delivers-best-precision-measurement-w-boson-mass-lhc;
paper at https://arxiv.org/abs/2412.13872, December 2024). The gap to CDF is
about 73 MeV, above 5 sigma given roughly 13.6 MeV combined uncertainty
(arithmetic from the quoted intervals; high). No systematic in CDF has been
identified, so the discrepancy is unexplained but isolated. Platform
relevance: replication at matched precision, not argument, is what closed
this; the CDF number remains an open data point, not a discovery.

### 3.3 The S8 "lensing is low" tension largely dissolved

Widely cited at 2-3 sigma from 2020 to 2023, it is now statistical agreement:
KiDS-Legacy reports S8 = 0.815 +0.016/-0.021, consistent with Planck at 0.73
sigma, a 2.2-sigma decrease in tension versus the previous KiDS release, with
approximately two-thirds of the reduction traced to improved
redshift-distribution calibration methodology rather than new sky data (high;
arXiv:2503.19441, March 25, 2025, https://arxiv.org/abs/2503.19441, published
in A&A 2025). Platform relevance: the tension was substantially a calibration
artifact; methodology audits can dissolve a headline discrepancy without any
new observation.

### 3.4 The Hubble tension is not a clean experiment-versus-experiment conflict

The headline pair is real: SH0ES reports H0 = 73.17 ± 0.86 km/s/Mpc (high;
Breuval et al., arXiv:2404.08038, April 2024,
https://arxiv.org/abs/2404.08038) against Planck's 67.4 ± 0.5 (high; Planck
2018, arXiv:1807.06209, https://arxiv.org/abs/1807.06209), a 5.8-sigma gap.
But the CCHP JWST-calibrated ladders sit in between: TRGB gives 70.39 ± 1.22
± 1.33 and JAGB gives 67.80 ± 2.17 ± 1.64 (Freedman et al., arXiv:2408.06153,
August 2024, https://arxiv.org/abs/2408.06153), and the 2025 CCHP TRGB-SN
analysis reports 68.4 to 69.6 km/s/Mpc depending on the supernova magnitude
set, describing its value as increasingly at odds with SH0ES
(arXiv:2503.11769, March 2025, https://arxiv.org/abs/2503.11769). A note on
provenance: an earlier draft of this dossier attributed the 70.39/67.80
values to the 2025 paper; full-text checking refuted that attribution and it
is corrected here. What did verify from the 2025 paper: revised SH0ES-22
Cepheid distances agree with CCHP TRGB distances to shared galaxies at about
1%. And no measurement error explaining SH0ES has been found; JWST rejected
unrecognized Cepheid crowding as the cause at 8 sigma (high; Riess et al.,
arXiv:2401.04773, January 2024, https://arxiv.org/abs/2401.04773). The
disagreement lives in calibrator and supernova-sample choices. Platform
relevance: the popular "two experiments disagree" frame is wrong in shape;
the conflict is in analysis choices downstream of largely agreeing distances.

### 3.5 DESI's evolving dark energy is below discovery threshold

DESI DR2 BAO prefers w0waCDM over LCDM at 3.1 sigma with CMB data, and 2.8 to
4.2 sigma with supernovae depending on which compilation is used; DR2 BAO
alone is in mild 2.3-sigma tension with the CMB inside flat LCDM (high;
arXiv:2503.14738, v1 March 18, 2025, v3 October 9, 2025,
https://arxiv.org/abs/2503.14738). This is a model-selection statement, not a
direct interval non-overlap, and it may yet be absorbed by supernova
systematics. Platform relevance: a sigma value attached to model comparison
is a different kind of claim from a sigma value attached to two measurements,
and the two are routinely conflated in secondary sources.

### 3.6 The e+e- hadronic cross-section dispute is unresolved

The CMD-3 versus KLOE/BaBar discrepancy in the e+e- to hadrons data forced
the 2025 White Paper to drop the data-driven HVP average entirely, because
the tensions make the dispersive results impossible to combine meaningfully
(high; arXiv:2505.21476, v3 September 11, 2025,
https://arxiv.org/abs/2505.21476; CERN Courier, Jul/Aug 2025,
https://cerncourier.com/a/shifting-sands-for-muon-g-2/). No experiment has
been shown wrong as of WP25 v3. Platform relevance: this is what an honest
unresolved state looks like at the field level; the consensus process chose
"cannot combine" over a forced average.

## 4. Dropped in verification

Eight findings failed adversarial checking against their cited sources and
are excluded from this dossier rather than repeated with weaker framing.

## 5. Build candidates

### 5.1 Stale-claim eval lane (anomaly half-life tasks)

The domain's core lesson is that headline claims carry expiry dates: g-2
(2021 to 2025), CDF W mass (2022 to 2024), S8 (2020 to 2025). A model trained
on older text will confidently reproduce the dead version. Build a gradable
task set that asks for the current status of each claim and grades against
dated ground truth.

Pour-back target: `dataset/` plus the gradable-task lane under `tasks/`.
First slice: commit `dataset/physics_tension_claims.jsonl` with the six nulls
above as dated records (claim text, as-of date, current status, source URLs),
no harness wiring yet.

### 5.2 Citation-anchor verifier (number-in-source check)

Verification in this pass caught a real misattribution: the 70.39/67.80 H0
values were credited to arXiv:2503.11769 but appear only in arXiv:2408.06153.
The check that caught it is mechanical: does the quoted number appear in the
cited source's text. That is a verifier the platform can run on any claim
that pairs a number with a source ID.

Pour-back target: `scripts/` first, promotable into the harness verifier
ladder. First slice: `scripts/check_claim_in_source.py` taking (numeric
string, arXiv ID) and reporting present/absent from the fetched abstract or
full text, plus one regression test in `tests/` encoding the CCHP pair
(absent in 2503.11769, present in 2408.06153).

### 5.3 Sigma-arithmetic recompute check

Several verdicts leaned on independent arithmetic: 73 MeV over a combined
13.6 MeV is above 5 sigma; 38 over 63 is about 0.6 sigma. Recomputing a
claimed significance from the quoted central values and uncertainties is a
cheap adversarial check that needs no network access and catches both
transcription errors and stale baselines.

Pour-back target: the harness verifier set under `harness/`. First slice: a
pure function `sigma_gap(a, da, b, db)` with pytest fixtures for the W-mass,
g-2, and Hubble pairs, asserting the recomputed sigmas match the published
characterizations.
