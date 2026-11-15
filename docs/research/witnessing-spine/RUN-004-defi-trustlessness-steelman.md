# Run 004 — The Trust-Relocation Gap in "Trustless" DeFi

### An adversarial steelman of the claim that cryptographic verification eliminates intermediary trust

**Owner:** Zain Dana Harper (independent researcher, Seattle · ORCID 0009-0001-7175-5393)
**Date:** 2026-06-20
**Stratum:** Blockchain + crypto-economics — the last uncovered rotation stratum.
**Form:** four-strata survey + adversarial STEELMAN (claim ↔ evidence ↔ verdict); genuine pro/con disagreement represented, not flattened.
**Method:** 4 parallel web-grounded scholar agents (≈191 tool-calls combined) → author synthesis + independent spot-verification of the two load-bearing claims. ≈80 deduplicated sources; every citation retrieval-checked; maturity labeled; UNVERIFIED items flagged and excluded from load-bearing use.
**Part of:** *The Witnessing Spine* corpus · CC-BY-4.0 · companion [*Conferred Existence*](https://doi.org/10.5281/zenodo.20773724).

---

## The claim under test

> **"DeFi is trustless: cryptographic verification replaces the need to trust intermediaries."**

This is the foundational rhetorical premise of the entire sector — "trustless," "don't trust, verify," "code is law." The steelman decomposes it into four sub-claims, one per place where trust actually hides, and tests each against the strongest available evidence:

1. **Block production** — MEV is tamed; verified inclusion is fair inclusion.
2. **The edges** — oracles and bridges extend trustlessness to off-chain and cross-chain state.
3. **Market-making economics** — providing liquidity to AMMs is a profitable, low-risk yield.
4. **The peg** — decentralized/algorithmic stablecoins hold value without centralized collateral.

---

## §0 — Executive verdict

**FALSE as stated. True only in a narrow, sharply-restricted restatement.**

Cryptographic verification in DeFi is real and load-bearing: it verifies that a state transition is *valid* — signatures check, the invariant holds, the block is well-formed. What it does **not** verify is the property the "trustless" rhetoric actually sells: that **no identifiable party holds contingent power over outcomes.** Across all four strata, verification does not *eliminate* trust — it *relocates* it, usually *upward* to a smaller, less observable set of actors with greater individual leverage than the parties they replaced. The single deepest result in the corpus is a formal impossibility theorem: **cross-chain communication without a trusted third party is impossible** (Zamyatin et al., FC 2021 — independently re-verified, §7). The committee, the builder, the oracle node-set, the collateral custodian, the sequencer, the governance whale, and ultimately the base-layer social consensus *are* that trusted third party. "Verified" and "trust-minimized" are not the same predicate.

The narrow restatement that **is** true: *cryptographic verification minimizes trust in the correctness of state transitions, and well-designed systems (ZK light-client bridges, over-collateralized stablecoins, deterministic-block-time L2s) measurably reduce specific trusted surfaces — but they cannot make economic safety a corollary of cryptographic validity, because the two are orthogonal properties.*

---

## §1 — MEV & block-production trust

**Sub-claim steelmanned:** *MEV is well-understood, largely benign, and managed; PBS / MEV-Boost and fair-ordering research have tamed it.*

**Steelman (real weight).** MEV-Boost reached >90% validator adoption post-Merge [gray-lit/data], replacing the chaotic priority-gas-auction wars of Daian et al. with a legible sealed-bid market that at least makes extraction auditable and redistributes much of it to proposers. Under PoS, the time-bandit reorg threat is dampened by endogenous slashing cost. Fair-ordering research (Kelkar et al.) has produced the first formal batch-order-fairness protocols for Byzantine consensus.

**Key evidence (claim ↔ evidence ↔ citation ↔ maturity).**
- Foundational taxonomy + consensus-instability threat — Daian, Goldfeder, Kell, Li, Zhao, Bentov, Breidenbach, Juels, **"Flash Boys 2.0,"** arXiv:1904.05234 (2019) → **IEEE S&P 2020**, DOI:10.1109/SP40000.2020.00040. [peer-reviewed]
- Time-bandit rationality threshold: a rational miner with 10% hashrate forks if a single MEV opportunity exceeds **4× the block reward**; one measured extraction was **$4.1M (616.6× block reward)**; **$540.54M** total profit measured over 32 months — Qin, Zhou, Gervais, arXiv:2101.05511 → **IEEE S&P 2022**. [peer-reviewed]
- Builder concentration: **two builders produced >85% of Ethereum blocks** — Yang, Nayak, Zhang, arXiv:2405.01329 → **IEEE S&P 2025**, DOI:10.1109/SP61157.2025.00157. [peer-reviewed]
- Private order flow = **54.59% of block value**, with monopoly-tending auction dynamics — Wang, Huang, Zhang, Huang, Wang, Tang, arXiv:2410.12352 → **WWW '25**, DOI:10.1145/3696410.3714754. [peer-reviewed]
- Censorship: **46% of blocks produced by OFAC-censoring actors at peak** — Wahrstätter et al., **"Blockchain Censorship," WWW '24**, DOI:10.1145/3589334.3645431. [peer-reviewed]
- Relay is a *trusted* mediator with no cryptographic accountability — "nothing prevents malicious relays from submitting fraudulent bids… no way of verifying that the value is indeed what is claimed" — Flashbots MEV-Boost architecture/risks docs. [vendor/gray-lit]
- Fair ordering: Aequitas (Kelkar, Zhang, Goldfeder, Juels, **CRYPTO 2020**, IACR 2020/269) and Themis (Kelkar, Deb, Long, Juels, Kannan, **CCS 2023**) — first batch-order-fairness protocols, but **permissioned-consensus** results that do not port to Ethereum's PBS auction. [peer-reviewed]
- The fairness ceiling: a **Condorcet attack with as few as two honest-looking transactions breaks batch-order-fairness even with all-honest nodes** — Vafadar, Khabbazian, arXiv:2306.15743 → **AFT 2023**. [peer-reviewed]

**Counter-evidence / where it breaks.** "Tamed" describes value *legibility*, not trust elimination. The relay is explicitly trusted (vendor's own docs); two builders hold 85% of blocks; private order flow (54.59% of value) drives the auction toward monopoly and locks out small builders structurally; a censorship vector that *did not exist before PBS* reached 46% of blocks. Encrypted-mempool and ePBS (EIP-7732) fixes remain research-grade and still rest on honest-majority keyholder assumptions.

**Verdict:** **FALSE as stated.** True restatement: *PBS converted MEV from chaotic waste into an auditable market and redistributed much of it to validators — but it relocated ordering/inclusion trust to a 2-builder oligopoly and a small set of unaccountable relays, and introduced a censorship vector absent from the pre-PBS chain. Verified inclusion ≠ fair, trust-minimized inclusion.*

---

## §2 — Oracles & bridges (trust at the edges)

**Sub-claim steelmanned:** *Decentralized oracle networks and cross-chain bridges securely extend trustlessness to off-chain and cross-chain state; this is mature infrastructure.*

**Steelman (real weight).** Chainlink distributes attestation across many independent operators with on-chain aggregation and penalties. Uniswap v3 TWAP makes single-block manipulation of a deep pool economically irrational (manipulating USDC/WETH 5 bps ~20% over two blocks would require swapping **~$709B** [vendor]). zkBridge (Xie et al., **CCS 2022**) *proves* committee-free cross-chain verification is achievable — proof gen ~20s, on-chain verify ~230K gas. [peer-reviewed]

**Key evidence (incidents with verified magnitude + root cause).**
- **bZx** (Feb 2020): two flash-loan oracle manipulations in four days, ~$1.2M combined; spot price from Uniswap v1 / Kyber used as implicit oracle, manipulated *within one atomic transaction*. [incident]
- **Harvest Finance** (Oct 2020): **$33.8M**; Curve spot price used as vault NAV oracle, manipulated via $50M flash loan. [incident]
- **Mango Markets** (Oct 2022): **~$116M** (SEC charge figure; CFTC "over $110M"); Eisenberg pumped MNGO spot ~2300% to inflate oracle-priced collateral — *not* a flash loan, but sustained manipulation of a low-liquidity aggregate feed. [primary — SEC 2023-13 / CFTC 2023-8647]
- **Ronin** (Mar 2022): **~$625M**; nominal 5-of-9 multisig compressed to 4 phished Sky Mavis keys + 1 stale allowlist signature; **Lazarus**. [incident + FBI attribution]
- **Wormhole** (Feb 2022): **~$326M**; a single unchecked Solana syscall (`load_instruction_at` vs `…_checked`) bypassed guardian signature verification. [incident]
- **Nomad** (Aug 2022): **~$190M**; a `0x00` Merkle root made acceptable during a proxy upgrade → "crowd-sourced" drain by ~300 copycat addresses in 150 minutes. [incident]
- **Poly Network** (Aug 2021): **~$611M** (returned); unconstrained external call enabled keeper-key replacement. [incident]
- **Harmony Horizon** (Jun 2022): **~$100M**; 2-of-5 multisig, two keys compromised; **Lazarus**. [incident + FBI]
- Aggregate: **~$2B across 13 bridge hacks = 69% of all 2022 DeFi theft** to Aug 2022 — Chainalysis. [data/gray-lit]
- Oracle attacks = **15% of 181 DeFi incidents (2018–2022), ≥$3.24B** — Zhou, Qin et al., "SoK: DeFi Attacks," arXiv:2208.13035. [preprint]
- TWAP manipulation "easier than said" under low liquidity / multi-block proposer control — Mackinga, Nadahalli, Wattenhofer, IACR 2022/445 → **IEEE ICBC 2022**. [peer-reviewed]
- **Foundational impossibility:** cross-chain communication is **impossible without a trusted third party** — Zamyatin, Al-Bassam, Zindros, Kokoris-Kogias, Moreno-Sanchez, Kiayias, Knottenbelt, "SoK: Communication Across Distributed Ledgers," **FC 2021**, DOI:10.1007/978-3-662-64331-0_1 (IACR 2019/1128). **[peer-reviewed — independently re-verified, §7]**

**Counter-evidence / where it breaks.** Zamyatin et al. set the structural ceiling: every deployed committee bridge reduces to an n-of-m honest-majority assumption over a *named, targetable* operator set — which Lazarus defeated twice via key extraction. Any protocol that reads a manipulable spot price in the same transaction as a value-sensitive op inherits that source's liquidity-depth risk; the AMM faithfully reports a price that is *economically fraudulent in context*. Pyth's first-party model and Chainlink's reputation committee both relocate trust rather than remove it. ZK bridges are the credible exit, but they are not the deployed majority.

**Verdict:** **FALSE as stated.** True restatement: *oracles and bridges transform trust from a single party into a committee / publisher-set / liquidity-pool — each with a characterized, repeatedly-exploited failure mode. Committee-free verification (ZK / light clients) is provably possible but not yet the deployed norm. On-chain verification cannot cover off-chain or cross-chain truth without importing a trusted third party — this is a theorem, not a maturity gap.*

---

## §3 — AMM liquidity economics (loss-versus-rebalancing)

**Sub-claim steelmanned:** *Providing liquidity to AMMs is a profitable, low-risk passive yield; fees compensate LPs.*

**Steelman (real weight).** For correlated/stable pairs (USDC/USDT), σ→0 so LVR→0 and fees dominate. Sophisticated active LPs using concentrated v3 ranges and JIT can capture amplified fees; some high-fee/high-volume, low-vol pools satisfy the break-even `fee_rate × volume/TVL > σ²/8`. Auction-managed designs (am-AMM, **AFT 2025**) can in theory return arbitrage surplus to LPs.

**Key evidence.**
- **LVR framework:** instantaneous LP loss to arbitrage = **σ²/8 × pool value per unit time** for a constant-product AMM ("the Black-Scholes of AMMs") — Milionis, Moallemi, Roughgarden, Zhang, arXiv:2208.06046 (CCS DeFi 2022). **[σ²/8 coefficient independently re-verified, §7]**
- LVR ≠ impermanent loss: IL is loss-vs-*holding* (reversible, path-dependent); LVR is loss-vs-*rebalancing* (a monotone, irreversible running cost). [preprint]
- Fees damp but do not eliminate LVR — Milionis, Moallemi, Roughgarden, arXiv:2305.14604 → **FC 2024**. [peer-reviewed]
- Earliest large v3 study: across 17 pools (43% of TVL, 2021), fees **$199.3M < IL $260.1M**; **49.5% of positions net-negative vs HODL** — Loesch, Hindman, Richardson, Welch, arXiv:2111.09192. **[preprint — Bancor-commissioned, conflict-of-interest flagged]**
- Independent 2022–2023 replication: **arbitrage losses exceed fees across many of the largest pools**, and **v2 pools are more profitable for passive LPs than v3** — Fritsch, Canidio, arXiv:2404.05803. [preprint]
- "Returns and risks vary wildly… concentrated liquidity requires active management; IL increases faster" — Heimbach, Schertenleib, Wattenhofer, **AFT 2022**. [peer-reviewed]
- CFMM arbitrage is structural, not accidental — Angeris, Chitra, "Improved Price Oracles: CFMMs," **AFT 2020**. [peer-reviewed]

**Counter-evidence / where it breaks.** Advertised APR is a *gross* fee rate over TVL; it omits LVR (≈11% annualized drag at 5% daily ETH vol *before* fees), gas, out-of-range opportunity cost, and the HODL counterfactual. For volatile pairs the empirical aggregate is net-negative vs HODL; concentrated liquidity *worsened* passive outcomes; JIT bots cannibalize the fees passive LPs would have earned without bearing proportional LVR. Under GBM dynamics LVR is structural and non-diversifiable.

**Verdict:** **FALSE as stated.** True restatement: *AMM LP earns visible gross fees but pays a continuous, quantifiable adverse-selection cost (LVR ≈ σ²/8 × pool value) to arbitrageurs. Net-positive provision is real but narrow — stable/correlated pairs, sophisticated active managers, high-volume/low-vol regimes. For the median passive LP in a volatile pair, advertised APR ≠ realized risk-adjusted P&L; the gap is precisely the LVR term.* (Direct echo of Run 003: the displayed number is not the witnessed outcome.)

---

## §4 — Stablecoins & algorithmic pegs

**Sub-claim steelmanned:** *Decentralized/algorithmic stablecoins hold their peg without centralized fiat collateral; crypto-economic design is sufficient for monetary stability.*

**Steelman (real weight).** Over-collateralized, governance-controlled DAI held its peg through Black Thursday, the 2022 winter, and the 2023 SVB episode. Kozhan & Viswanath-Natraj show *arbitrage frictions* (not the mechanism per se) drive DAI deviations. Lyons & Viswanath-Natraj (**NBER w27136 / JIMF 131, 2023**) [peer-reviewed] find demand-side arbitrage is the dominant peg mechanism — market participants, not a treasury, do the stabilizing in normal times.

**Key evidence.**
- **Terra/UST:** LUNA supply **1B → 6T in three days**; **~$50B** wiped; reflexive mint-burn made collateral and peg co-determined — Liu, Makarov, Schoar, **NBER w31160 (2023)**. [working-paper]
- Anchor's **19.5% yield** (≈$6M/day subsidy by Apr 2022; ~75% of UST deposited) was *purchased* demand, not organic stability. [working-paper]
- **Death spirals were formally predicted three years pre-Terra** — Klages-Mundt, Minca, "(In)Stability for the Blockchain," arXiv:1906.02152 → **Cryptoeconomic Systems 2021**. [peer-reviewed]
- **MakerDAO Black Thursday** (Mar 2020): **$8.325M of collateral liquidated for 0 DAI**; 36.6% of auctions cleared at 100% discount; $4M system deficit — matching the model's predicted mempool-congestion attack. [gray-lit incident + peer-reviewed model]
- Over-collateralization requires **≥150% (canonical) / ~300% in practice** — a permanent capital-inefficiency cost. [gray-lit + working-paper]
- **USDC depeg to ~$0.87** (Mar 2023) when Circle disclosed **$3.3B (8% of reserves)** stuck at SVB — even fiat-backed coins carry off-chain custody trust. [gray-lit/incident]
- Under full collateral, redemption promises are **not credible without structural binding** (immutable contracts / decentralized issuance) — d'Avernas, Maurin, Vandeweyer, **Management Science 2026**, DOI:10.1287/mnsc.2024.06992. [peer-reviewed]
- **Tether allows ~6 redeemers per average month**; "improving price stability may increase run risk" — Ma, Zeng, Zhang, **NBER w33882**. [working-paper]

**Counter-evidence / where it breaks.** UST's algorithm executed correctly; the *logic* (self-referential collateral) was insolvent-by-construction once LUNA cap fell below UST supply. DAI's survival is the *opposite* of the claim — it survives by over-collateralization that now leans on **~55% US Treasuries via Coinbase Custody**, reintroducing exactly the fiat-custodian trust the claim denies. The USDC episode proves cryptographic proof of on-chain balances cannot verify off-chain custodian solvency.

**Verdict:** **FALSE as stated.** True restatement: *over-collateralized designs maintain peg across moderate stress, but stability is conferred by the credibility and excess value of backing collateral — which in practice has required centralized/fiat-backed assets — not by the algorithm. Purely algorithmic seigniorage designs are provably death-spiral-prone under large demand shocks. A token asserting "$1" is a claim, not its warrant.*

---

## §5 — Where trust actually resides (the map)

| Layer | The concrete trusted party "trustless" obscures | Evidence | Maturity |
|---|---|---|---|
| Block production | 2-builder oligopoly (>85% of blocks) + unaccountable relays | Yang-Nayak-Zhang (S&P '25); Flashbots docs | peer-reviewed / vendor |
| Oracles | Permissioned node committees / first-party publishers; DEX liquidity depth | Caldarelli (Applied Sci. 2021); Werner et al. SoK (AFT '22) | peer-reviewed |
| Bridges | n-of-m validator multisigs (Ronin 5/9, Wormhole 13/19, Harmony 2/5) | Zamyatin et al. (FC '21) impossibility | peer-reviewed + incident |
| Stablecoins | Collateral custodians (fiat/Treasuries), governance token holders | USDC/SVB; DAI Treasury backing | gray-lit + working-paper |
| L2 sequencer | Single centralized sequencer (reorder/delay/censor) | L2Beat staging — no Stage 2 as of 2026 | gray-lit |
| L2 upgrade keys | Security-council multisig (e.g. 9-of-12) with fast upgrade authority | L2Beat Stage-1 classifications | gray-lit |
| Governance | Token-weighted plutocracy; ~5–12% turnout; few delegates dominate | Eisermann et al. arXiv:2501.13377 | preprint + gray-lit |
| Base layer | Core-dev + social consensus; the 2016 DAO-fork precedent ($150M reversed) | DAO hard-fork history | gray-lit/incident |

**Synthesis.** At *every* functional layer, named parties hold contingent authority. A transaction can be cryptographically valid while being economically unsafe — because the price it consumed was manipulated, the bridge validator was bribed, the sequencer reordered it, or the governance vote that set its parameters was captured by three whales. "Trustless" confuses *verifiability* with *safety*; they are orthogonal.

---

## §6 — The unifying finding: the FOURTH convergence on the witnessing spine

This is the headline. Four rotations, four sectors, **one identical structural gap** — a verified or asserted artifact mistaken for the warranted property it only resembles:

| Run | Sector | The artifact that *is* verified/asserted | The warrant it is NOT |
|---|---|---|---|
| 001 | Financial-AI provenance | documented lineage, signed build provenance | **witnessed** provenance — *authentication ≠ authorization* |
| 002 | GenAI COBOL modernization | a syntactically translated program | **behavioral equivalence** — *translation ≠ equivalence* |
| 003 | Quant/ML alpha | a backtest Sharpe / advertised APR | **deflated, out-of-sample** alpha — *backtest ≠ realized return* |
| 004 | DeFi "trustlessness" | a cryptographically valid state transition | **economic safety** — *verification ≠ trust-minimization* |

Each gap is closed by the same move: **re-derive the warrant from primary evidence, account for coverage, and stamp MATCH / DRIFT / UNVERIFIABLE** rather than accept the artifact's self-report. The cross-sector convergence is itself the finding: this witnessing / proof-before-trust discipline is **a general contribution**, not a niche. DeFi makes the gap most legible because it is the field that most loudly asserts the artifact (cryptographic validity) *is* the warrant (trustlessness) — and a $50B collapse, $2B in bridge theft, and a formal impossibility theorem all sit in that exact gap.

---

## §7 — Spot-verification log (independent author checks)

Per discipline, I independently re-fetched the two most load-bearing claims that the agents flagged as not-fully-extracted, before relying on them:

1. **LVR = σ²/8 (constant-product, per unit time).** Agent flagged "moderate confidence — coefficient not extracted from PDF body." **Independent check CONFIRMED:** the loss per unit time as a fraction of mark-to-market pool value "is simply 1/8 times the instantaneous variance." Upgraded to **verified**; it is now load-bearing in §3.
2. **Zamyatin et al. cross-chain impossibility.** Agent confirmed venue/authors but flagged the theorem phrasing as abstract-only (IACR PDF 403'd). **Independent check CONFIRMED:** the paper "shows that cross-chain communication (CCC) is impossible without a trusted third party, contrary to common beliefs." Full author list and FC 2021 DOI confirmed. It is now the load-bearing spine of §2 and §0.

One false start logged honestly: my first fetch used a wrong arXiv ID (1912.09063 → an unrelated harmonic-analysis paper); I did not let it contaminate the record and re-verified via the correct IACR/FC source. (The same no-fabrication discipline is applied throughout the corpus.)

---

## §8 — Limits logged

- **MEV gray-lit anchors:** ">90% MEV-Boost adoption," "~80% OFAC-compliant blocks (Nov 2022)," and the exact 96% builder-outsourcing figure are gray-lit/data, not peer-reviewed; the peer-reviewed censorship anchor is the WWW '24 **46%**. The ">95% of auctions won by top-3 builders" line was **UNVERIFIED** (not in the abstract) and is excluded; only the confirmed 54.59% private-order-flow figure is used.
- **Incident magnitudes** vary by source (bZx ~$1.2M combined is approximate; Mango uses the SEC's $116M; Harmony's key-compromise vector was never fully disclosed). The big bridge numbers (Ronin/Wormhole/Nomad/Poly) are cross-confirmed.
- **LP-loss COI:** the Loesch/Topaze-Blue 49.5%-negative figure is **Bancor-commissioned** (a competing AMM) — flagged, and only used because Fritsch-Canidio independently replicate the *direction* on 2022–2023 data.
- **Stablecoin magnitudes:** UST loss cited at the **NBER $50B**; popular-press $60B+ (contagion) is UNVERIFIED against a primary. USDC low printed at ~$0.87 (CNBC) vs an $0.85 outlier — the $0.88 in the brief falls within intraday range but is not primary-sourced.
- **Disagreement is real:** the steelman camp (ZK bridges, DAI's durability, active-LP profitability, demand-side peg stabilization) is genuine and credited; the verdict targets the *strong universal* claim and credits the *narrow* wins.
- Several primaries were abstract-only / 403 (IACR PDFs, paywalled SIAM JFM, NBER binary PDFs); core facts cross-confirmed via ≥2 independent secondaries where the primary did not render.

## §9 — Frontier opening

The §6 convergence promotes the carry-forward whitepaper from "candidate" to "load-bearing." The most concrete instantiation is the **Annex-IV verifiable-provenance protocol** (Run 001); the most *novel* is the unifying abstraction itself — **coverage-accounted witnessed evidence** (re-derive the warrant; MATCH/DRIFT/UNVERIFIABLE) as a sector-agnostic discipline now demonstrated across regulation, legacy migration, quant diligence, and on-chain economics. A DeFi-specific organ would be a **"validity ≠ safety" attestor**: a tool that, given a transaction or position, separates what is cryptographically verified from what is economically trusted, and names the trusted party at each layer (the §5 map, mechanized).

---

*Run 004 of* The Witnessing Spine *corpus.*
