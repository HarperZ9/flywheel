# Synthesis: Verification-Grounded Infrastructure Requirements

**Synthesis date:** 2026-07-25. **Provenance caveat that governs everything below:** every claim dated after January 2026 comes from the five upstream research passes, which obtained it by live retrieval on 2026-07-25. I did not independently re-verify any of it in this pass. Where an upstream pass labeled a claim vendor-reported, single-author, secondary-source, or disputed, that label is carried forward and is load-bearing. Confidence labels are mine, derived from the upstream verification notes.

---

## 1. What AI is currently solving, and at what pace

The corpus does not organize cleanly by domain. It organizes by **what kind of oracle checked the result**, and that reorganization is the finding: pace tracks verification cost, not model capability.

### Tier A: machine-checkable artifact (kernel check, or a certificate a deterministic checker validates in seconds)

| Result | Date | Source | Confidence |
|---|---|---|---|
| Erdős #728 resolved: informal argument from GPT-5.2 Pro piped into Harmonic Aristotle, Lean-kernel-checked | 2026-01-04 | arXiv:2601.07421 | high (kernel artifact exists) |
| AlphaProof: AlphaZero-style RL entirely inside Lean, 80M-problem auto-formalized curriculum, IMO 2024 silver | 2025-11 | Nature s41586-025-09833-y (peer-reviewed) | high |
| Aristotle: IMO 2025 5/6 with every solution Lean 4 verified | 2025-07 / 2025-10 | arXiv:2510.01346 | high |
| Gauss: Lean formalization of the strong Prime Number Theorem, ~25k lines, ~1,000 theorems | announced 2025 | math.inc/gauss; artifact checkable | moderate (3-week timeline is a company claim; the Lean artifact is not) |
| AlphaEvolve: 48-scalar-multiplication 4x4 complex matmul (first improvement over 49 in that setting since 1969); matched SOTA on ~75% and improved ~20% of ~50 open problems | 2025, follow-ups to 2026-02 | arXiv:2506.13131; arXiv:2602.13171 | high (certificates re-verified by community) |
| Ramsey lower bounds via AlphaEvolve: R(3,13)>=61, R(3,18)>=100, R(4,13)>=139, R(4,14)>=148, R(4,15)>=159 | 2026-03-10 | arXiv:2603.09172 | high (witness graphs checkable); note the two upstream passes report **partially different value sets** from the same paper, so the exact table needs re-reading before republication |
| 41 new Zarankiewicz lower bounds using open-source OpenEvolve, reported under $30 per parameter combination | 2026-05-01 | arXiv:2605.01120 | high on existence, moderate on the cost figure |
| Constant-weight binary code bounds A(n,d,w) improved in 24 parameter combinations, single author | 2026-02-26 | arXiv:2603.00174 | high |
| New champion linear codes (transformer distance predictor + genetic search) | 2025-12 / 2026 | arXiv:2512.13370; npj Artificial Intelligence (peer-reviewed) | high |
| NP-hardness-of-approximation improvements: MAX-4-CUT 0.9883 to 0.987 via a discovered 19-variable gadget; MAX-3-CUT 0.9649 | 2025-09 | arXiv:2509.18057 | high |
| Decade-old online submodular optimization conjecture falsified by a three-item counterexample | 2026-02 | arXiv:2602.03837; DeepMind blog | high |
| Closed-form exact solutions for the cosmic-string gravitational-radiation integral I(N,alpha), cross-checked by quadrature and six independent derivations | 2026-03-05 | arXiv:2603.04735 | high (preprint) |
| Research-level physics autoformalized in Lean 4: fundamental theorem of matrix-product states, plus TNLean libraries | 2026-07-08 | arXiv:2607.07857 | high (preprint) |
| Production Rust cryptographic code verified through Charon/Aeneas/Hax into Lean 4 with AI provers closing obligations | 2026-05/06 | arXiv:2605.30106 | high (experience report) |
| Open-weight provers at local scale: Goedel-Prover-V2 32B (ICLR 2026); Goedel-Architect 99.2% pass@1 MiniF2F-test, 75.6% pass@1 PutnamBench; Goedel-Code-Prover-8B 62% | 2026 | ICLR 2026 poster; arXiv:2606.06468 | high on acceptance, moderate on the specific percentages |
| Lossless compression as a self-verifying oracle: Nacrith (135M SmolLM2 + arithmetic coder); 2026 AIT Compression Challenge, 117 compressors, multi-metric Pareto | 2026-02 / 2026-06 | arXiv:2602.19626; arXiv:2606.17712 | moderate (snippet-level) |

### Tier B: re-runnable simulation reference

| Result | Date | Source | Confidence |
|---|---|---|---|
| RL trained purely on procedurally generated physics-engine scenes; zero-shot transfer, +5 to +10pp on IPhO problems | 2026-04-13 | arXiv:2604.11805 | high (preprint) |
| Fine-tuning improves all five leading foundation MLIPs: forces 5-15x, energies 2-4 orders of magnitude; MLIP Arena as independent arbitration | 2026 | 10.1021/acs.jpclett.5c03801; arXiv:2605.22601; arXiv:2509.20630 | moderate |
| FHE kernels on TPUv5e: TFHE bootstrap 2.5x, CKKS rotation/mult 1.31x/1.18x, correctness oracle in the loop | 2026-05 | arXiv:2605.14718 | moderate (snippet-level) |
| THOR tensor-network configurational integrals, >400x speedup, agreeing with prior Los Alamos simulations for Cu, high-pressure Ar, Sn | paper 2025, press 2026-03 | Phys. Rev. Materials vol 9 iss 8 (2025) | moderate on content; **high that the "2026 breakthrough" framing is a press artifact** |

### Tier C: human expert review (no formal oracle)

| Result | Date | Source | Confidence |
|---|---|---|---|
| Erdős planar unit-distance conjecture disproved; Will Sawin extended to explicit n^1.014 lower bound; reviewed by mathematicians with early access | 2026-05-20 | understandingai.org; Scientific American; Physics World | moderate. **No arXiv preprint and no Lean formalization were located.** Gap to the n^1.333 upper bound remains |
| Aletheia (Gemini 3 Deep Think): 6/10 FirstProof research-level problems by majority expert assessment; four Erdős questions semi-autonomously; one solve (#1051) generalized into a research paper | 2026-02/03 | arXiv:2602.21201; arXiv:2602.10177 | moderate. **IMO-ProofBench Advanced figure is inconsistent across sources (95.1% secondary vs 90% in DeepMind's own blog).** No formal verification |
| Gemini Erdős-database study: of 13 "open" problems addressed, 4 genuinely novel, 8 already solved in obscure literature; v1 to v3 downgraded one claimed-novel solve to independent rediscovery; paper flags "subconscious plagiarism" | 2026-01-29 to 02-05 | arXiv:2601.22401 | high (the self-correction is in the record) |
| GPT-5.5 contributed a new proof of an off-diagonal Ramsey asymptotic, subsequently Lean-verified | 2026-04 | OpenAI blog | moderate (lab blog; harness not public) |

### Tier D: wet lab

| Result | Date | Source | Confidence |
|---|---|---|---|
| Germinal: de novo epitope-targeted nanobodies, 4-22% experimental success across four targets while testing only 43-101 designs per antigen; affinities 140-560 nM | 2026 | Nat Biotechnol 10.1038/s41587-026-03187-0 | moderate-high. **The reported denominator is what makes this the model citation** |
| ProteinMPNN-stabilized protease scaffolds into PACE evolution: variants cleave ataxin-2 79x better than variants evolved from the natural protease, A/B against the honest baseline | 2026-07-24 | Nature 10.1038/s41586-026-10820-0 | high on the report, moderate on the 79x figure (primary text not read) |
| Co-Scientist: AML repurposing candidates active in cell lines; vorinostat reduced a TGF-beta chromatin change 91% in hepatic organoids | 2026-05-19 | Nature 10.1038/s41586-026-10644-y | moderate. Surrogate endpoints only; validation stayed with humans and instruments |
| MOFGen: hundreds of thousands of MOF structures generated, five synthesized | 2025-04 (outside window) | arXiv:2504.14110 | moderate. The ratio is the point |
| BEE-NET to DFT to synthesis: YRu3B2 (Tc 0.81 K) and LuRu3B2 (Tc 0.95 K) confirmed by magnetization, specific heat, transport | 2026-06-17 | Phys. Rev. Research | moderate. **Verified and modest. Press framing as a room-temperature-superconductor race overclaims** |

### Tier E: randomized human endpoint

| Result | Date | Source | Confidence |
|---|---|---|---|
| Rentosertib (AI-discovered target and molecule), Phase IIa: +98.4 mL FVC at 60 mg QD vs -20.3 mL placebo, n=71 | 2025-06 | Nature Medicine | moderate-high. Highest oracle tier any AI-originated molecule has reached. Took roughly six years |
| RaDaR, open 32B, ~154k clinical cases: +21.44pp physician rare-disease accuracy vs internet search in a randomized assistance trial; >61% pre-suspicion surfacing implying ~1.87 months lead time | 2026-06-23 | arXiv:2606.24510 | moderate. **Preprint, not peer-reviewed. The lead-time figure is retrospective chart review and is the weakest number in the set** |
| Two clinician RCTs: 70-clinician workflow trial, 85% (AI first opinion) vs 82% (second opinion); ~58-60 Pakistani physicians, +27.5% with GPT-4o after a 20-hour AI-literacy curriculum | 2026 | npj Digital Medicine s41746-026-02545-1; Nature Health s44360-025-00007-8; medRxiv 2025.06.06.25329104 | moderate |

### Honest nulls, kept

- **The only independently checked analysis step in the corpus failed.** Robin's own analysis agent reported ripasudil boosting RPE phagocytosis 7.5-fold; human re-analysis of the same flow-cytometry data gave 1.75-fold, a 4.3x inflation, acknowledged in the supplement (Nature 10.1038/s41586-026-10652-y; preprint arXiv:2505.13400). The upstream pass notes it found **no other 2026 example of an end-to-end loop whose analysis step was independently verified**. Absence of other reported checks is more likely under-inspection than a clean record.
- **No AI break or meaningful AI-driven weakening of NIST-standardized lattice cryptography is published.** 2026 LWE progress is classical (eprint 2026/1048, 2026/1060). ML lines (SALSA, NoMod arXiv:2510.02162) recover only small or sparse-secret toy instances.
- **LLMs show no advance on open graph-theory problems without search/verification scaffolding**, despite strong performance on solved ones (arXiv:2602.05059).
- **Plain repeated-sampling baselines match or exceed AlphaEvolve-style evolutionary pipelines** on bound-finding, scaffold design, and ML competitions; search-space design and prompt-embedded domain knowledge carry the signal, and high variance with small eval sets corrupts selection (arXiv:2602.16805).
- **On-chain agent reputation is empirically failing.** ERC-8004 launched on Ethereum mainnet 2026-01-29; the first empirical study finds minimal reputation activity, sybil vulnerability, and a large empty-feedback problem, concluding registries alone cannot produce trust (arXiv:2606.26028).
- **A published position that contemporary AI lacks the capacity to diverge or negate in science** exists in the record (arXiv:2606.08251) and is not resolved.
- **No system was found that lets a receipt minted in one trust domain be spent in another.** That is a search-based null, not proof of absence.

### Disputed, flag on every use

- **Axiom Math autonomy claims.** A June 2026 single-author critique ("Axiom AI, the Theranos of mathematical AI?", Medium) alleges the "Fel's Conjecture" end-to-end-formalization claim concealed human labor: the input .tex reportedly carried the full proof strategy, generating functions, and English proofs. **Correctness of the Lean proofs is not disputed. Provenance and autonomy are.** Axiom's separate claim of five journal acceptances is promotional and unverified.
- **IMO 2026 official 42/42 gradings** (Huawei Celia, Xiaohongshu dots-note-3.0): secondary outlets only, not confirmed against imo-official.org. Within the same event: NVIDIA Nemotron 3 Ultra at 30/42 with open weights released 2026-06-04 (above the 29-point gold threshold); AxiomProver Lean 4 proofs for all six problems (~8,000 lines, ~25h) published on GitHub but **not officially IMO-verified**; Deedy Das's self-administered harness scored three models at 42/42 with Claude-based agent graders, **explicitly labeled by its own operator as "strong but not authoritative"**. 7 of 666 human contestants scored 42/42.
- **Vendor-only percentages, not independently verifiable:** 0.7% of Google fleet compute recovered by an AlphaEvolve Borg heuristic, 23% kernel tiling speedup, 32.5% FlashAttention implementation speedup, ~1% Gemini training-time cut. Also Unsloth's "~80% less VRAM for GRPO", "2,500+ environments" on the Environments Hub, and "Verifiers v1 DAG branching" (TechTimes, not cross-checked against the repo).
- **Single-author preprints with unreplicated numbers:** NabaOS tool receipts (91% hallucination detection, <15ms overhead, 98.7% correctness on "Fully Verified"), EG-VAR, MolTrust (a startup publishing about its own product). Promising designs, not established results.
- **Amateur GPT-5.4 Pro solve of an Erdős prime-sets problem** (Liam Price): press mention only, no primary writeup located.
- **Excluded as unverifiable or likely SEO-generated:** IsoDDE "doubling AlphaFold 3 accuracy", "15 to 20 AI programs entering pivotal Phase III this year", EPT-2 weather claims (vendor benchmark), "AI-authored paper passed peer review" (July 2026 WAIC coverage).

### Pace, stated honestly

Pace is inversely proportional to verification cost, and the spread is roughly four orders of magnitude in wall-clock:

- **Certificate-checkable classes: weeks.** Erdős #728 in January, Ramsey bounds in March, 41 Zarankiewicz bounds in May at reported cost under $30 per parameter combination. Verification is seconds and can be done by anyone.
- **Formal-proof classes: months, and amortizing.** Gauss converted a stalled 18-month human formalization effort into ~3 weeks of agent work (company timeline claim; the artifact is checkable). Once it exists, every downstream use of the strong PNT is a free kernel-checked receipt.
- **Simulation-reference classes: months, bounded by compute.**
- **Wet lab: months to years, and the denominator is the real cost.** Germinal spends 43-101 designs per antigen for a 4-22% hit rate. MOFGen spends hundreds of thousands for five.
- **Randomized human endpoints: years and millions.** Rentosertib took roughly six years to a Phase IIa signal at n=71.

There is no observed acceleration in tiers D and E. All of the visible 2026 acceleration is in tiers A and B. **A trust economy is the only mechanism in this corpus that makes the top tiers pay for themselves.**

---

## 2. What infrastructure for "AI solving human problems, trustably, at low verification cost" must provide

Each requirement traces to named evidence. These are ordered by how badly the corpus punishes getting them wrong.

**R1. Oracle tier must be a first-class, non-collapsible field in the receipt schema.** Five tiers with wildly different cost and transferability (proof checker, numeric/symbolic self-check, simulation reference, wet-lab assay, randomized human endpoint). A receipt that does not name its tier is unpriceable. A system that lets a tier-3 receipt buy tier-4 credibility inflates silently, which is the exact failure mode of preference reward. Evidence: the whole tier structure of section 1; the "verified but modest" superconductor case; the five-tier separation named independently by both the sci and infocs passes.

**R2. Receipts must bind inputs, not only outputs.** Hash the prompt, seed files, retrieved literature, tool versions, and environment. Evidence: the Axiom provenance dispute (a kernel-checked proof certifies correctness, not authorship); the Gemini study's explicit "subconscious plagiarism" caveat.

**R3. Receipts must bind to raw instrument or oracle output plus a re-runnable analysis script, never to a model's summary of a result.** This is the single strongest empirical constraint in the corpus. Robin's wet-lab step was real and the pipeline still produced a number inflated 4.3x, because verification stopped at the experiment and trusted the model's readout. Content-hash the raw data, the analysis code, and the environment, so any party recomputes the claimed statistic. This demotes analysis from unverified inference to a cheap deterministic check.

**R4. Price receipts in oracle calls, with the denominator mandatory.** Record attempts, oracle calls consumed, and hits. Without a denominator, a generator firing a million shots is indistinguishable from one firing ten, and the economy rewards volume over calibration. Evidence: Germinal (denominator reported) versus MOFGen (not).

**R5. A novelty oracle is a separate instrument from a correctness oracle.** 8 of 13 "solved" problems in the Gemini study were rediscoveries of obscure literature. Aletheia uses live search specifically to suppress citation hallucination. Ready-made cheap oracles exist: CiteCheck (arXiv:2605.27700), CiteAudit (arXiv:2602.23452), multi-agent citation-hallucination detection (arXiv:2605.08583).

**R6. Verifier QA precedes training.** Fuzz every oracle for false accepts and false rejects before any reward it emits is treated as a receipt (arXiv:2606.01066). Prefer isomorphic/structural checks over extensional answer-matching, which demonstrably induces shortcut strategies (arXiv:2604.15149). Grade the graders: IMO 2026 exhibited three receipt classes with different trustworthiness in one event.

**R7. Two-tier propose/dispose is the economic core.** Cheap signals (majority vote, rubric or generative-reward-model scores, fast surrogate verifiers) may only **propose**. An expensive oracle (executor, kernel, external ground truth) **disposes**. Inconclusive cases receive zero-mean variance-preserving credit, never positive reward. Evidence: JURY-RL (arXiv:2604.25419) with its ResZero fallback; AlphaEvolve's ~10,000x branch-and-bound surrogate with final re-verification by the original brute-force checker. Corollary: rubric and LLM-judge signals may shape intermediate steps but must never be the receipt of record, because judges are attackable (AdvJudge-Zero, arXiv:2512.17375).

**R8. Amortization needs two concrete mechanisms, both already published.** (a) **Audit-once lifts plus replay artifacts**: audit each source, tool, or oracle adapter once at curation time, mint a reusable attestation, and never re-enter the verification loop per query; ship a replay artifact any third party can re-check without re-running the model (EG-VAR, arXiv:2607.12650). (b) **Certify-fast-against-slow with a versioned reference-set registry**: certify a cheap method against an expensive oracle on a fixed reference set, then spend that certificate on new inputs (THOR against prior simulations; MLIP fine-tuning against DFT and QMC). Both require **explicit scope bounds**: a certificate earned on copper does not transfer to a molecular crystal, and the receipt must say where it stops being valid.

**R9. Trust scores must be recomputable from the ledger, not stored.** Derive them deterministically from receipts so any party re-derives the identical score from evidence (MolTrust pattern, arXiv:2605.06738, single-author, startup-affiliated). This delivers the non-volatile, non-competitive property for free: there is no score to game, only keys to protect.

**R10. Signed receipts at the tool boundary are the right cryptographic primitive. Skip zkML and TEEs.** ZK-proving LLM inference remains 10^4 to 10^5 times slower than native inference even after production milestones (arXiv:2603.18046). TEE attestation is where industry landed but is cloud hardware a local operator does not control. HMAC or Ed25519 over {tool, input hash, output hash, extracted facts, timestamp}, with the key held outside the model's reach, is the affordable per-turn option (NabaOS's <15ms is single-author and unreplicated; treat the design as sound and the number as unverified).

**R11. Verify untrusted compute asymmetrically, commit-then-spot-check.** TOPLOC uses locality-sensitive hashing over intermediate activations: 258 bytes per 32 tokens, validation up to 100x cheaper than the original inference, robust across GPUs, kernels, and tensor-parallel configurations; v2 extends to pipeline-parallel with stage-by-stage replay on failure (arXiv:2501.16007, ICML 2025; v2 details from the vendor blog). This is the only asymmetric-verification scheme in the corpus demonstrated at open-training scale.

**R12. Named invalidation is the hard part of any reuse-without-re-verification scheme.** A receipt system needs to answer precisely which receipts a change voided, plus freshness certificates, plus decay for receipts nobody has re-verified recently. Value should decay for staleness rather than be adjudicated by a scoreboard (the MLIP Arena lesson: receipts issued by the party that benefits need an independent re-execution path, and the non-competitive form of that is a re-verification service, not a ranking).

**R13. Split every receipt into a machine-verified component and a human-attested statement-fidelity component.** The machine-verified part is freely spendable. The attested part (does the formal statement mean what the domain expert meant, does the assay measure the biology, does the endpoint matter clinically) is not transferable without re-attestation and should decay. Cirac's group names this directly: the bottleneck in large-scale autoformalization is "enforcing mathematical intent", not proof search (arXiv:2607.07857). EG-VAR's own stated limitation is the same shape: a semantically wrong audited lift certifies wrong claims forever. **Conflating these two components is the easiest way for a verification economy to quietly become a preference economy again.**

**R14. The trust edge is (issuer, verifier, workflow, operator calibration), not (claim, verdict).** The 2026 clinical RCTs measured the human-model pair: one ran a 20-hour AI-literacy curriculum before randomization, and first-opinion versus second-opinion framing changed accuracy (85% vs 82%). A receipt that omits who was holding it and under what workflow does not transfer between operators.

**R15. Negative and null receipts must be spendable.** They are cheap to produce, expensive to rediscover, and a system whose only currency is positive results reproduces exactly the publication bias that makes the current literature expensive to verify. Concrete nulls to encode at zero trust pending certificate: no AI break of standardized lattice crypto; no LLM advance on open problems without verification scaffolding; vendor infrastructure percentages marked non-independently-verifiable rather than spendable.

**R16. The ledger substrate is commodity. Do not invent it.** Append-only hash-chained log, UTC timestamps, trace IDs, OpenTelemetry GenAI semantic conventions for entry vocabulary, WORM storage with per-entry hashing. Regulation is forcing this tooling into existence anyway (EU AI Act Article 12 queryable tamper-evident records, Article 50 machine-readable marking, both from 2026-08-02, moderate-high confidence, regulation text not checked). Invest the effort in attestation **semantics**, which is the unclaimed layer.

**R17. Local-first and offline-verifiable is a genuine gap, not a preference.** Every shipping system in the trust pass assumes cloud or chain. There is no local-first, offline-verifiable receipt system for local models in the landscape found.

**R18. Cross-domain receipt interchange is a genuine gap.** No format lets a C2PA media credential, an AP2 payment mandate, a runtime tool receipt, a Lean replay artifact, or a TOPLOC commitment be spent in another domain. Nor is there a standard for delegation and endorsement chains ("I trust X's verification of Y"). The April 2026 AI-identity survey (arXiv:2604.23280) names delegated-authority chains, standardized agent reputation, and output traceability as explicitly unaddressed across all surveyed standards bodies.

---

## 3. Where public sentiment says trust is broken, and what would actually rebuild it

### What is broken

| Broken thing | Evidence | Confidence |
|---|---|---|
| Trust in vendors and in regulators simultaneously | 59% distrust US companies to develop AI responsibly; 67% lack confidence in government regulation; 71% think AI makes their personal information less secure; 63% say AI advances too quickly. Pew, 5,119 adults, fielded 2026-02-17/23, published 2026-06-17 | high (primary, fetched) |
| Familiarity is not producing trust | Usage rose from 33% (2024) to 49% (2026) while 40% expect net-negative societal impact; 48% of 18-29-year-olds predict negative impact vs 37% of 50+ | high (Pew) |
| Model self-report as a trust signal | Best models ~0.7% hallucination on summarization, some over 25%; models were **34% more likely to use certainty words when wrong** | moderate (aggregator sources) |
| Verification capacity, named as the scarce resource | Developer discourse converged on agents generating code faster than humans can verify; teams reporting "agents don't work" typically have verification pipelines that cannot absorb volume. KPMG Global AI Pulse independently finds value concentrating in organizations investing in governance and accountability rather than in those deploying the most AI | moderate-high |
| Infrastructure legitimacy | Local opposition blocked or delayed 48 US data-center projects worth $156B in a year; governor candidates in at least a dozen states back moratoriums; S.4214 proposed nationally; violence at the extreme end | moderate (snippet-level for most figures) |
| Economic credibility | Federal Reserve listed AI among top systemic financial-stability risks; ~$1T data-center construction planned for 2026 against ~$12B/yr US consumer AI spend; JP Morgan found 60% of 2027-slated capacity has not broken ground | moderate |
| Jobs | 71% of professionals expect AI to eliminate more jobs than it creates within three years; ~80,000 workers in AI-attributed layoffs in 2026 so far | moderate |
| Autonomous self-improvement, specifically | 69% say superintelligence should be prohibited until broad scientific consensus on safety; 64% say not until "provably safe and controllable"; ~95% reject a race | **advocacy-sourced (FLI, PauseAI, Public Citizen); direction corroborated by Time; exact percentages carry that caveat.** No poll specifically about "AI improving itself" was found; this is inferred, not measured |

### What would actually rebuild it

1. **Third-party checkability, never authority assertion.** With both vendors and regulators distrusted, "trust our platform" has no purchase. Receipts must verify offline, by anyone, without the issuer's cooperation.
2. **Manifest-shaped signed provenance, because that is the pattern the internet already chose.** The converged answer to untrusted generation is cryptographically signed provenance (C2PA Content Credentials, SynthID), not post-hoc detection, which is considered unreliable. C2PA has real cross-vendor adoption; newsroom and camera-firmware specifics in the sentiment pass are moderate-to-low confidence. Aligning receipt format with manifest-style attestation rides an existing standard rather than competing with one.
3. **Calibration bound to external outcomes, never to model confidence.** The +34% certainty-when-wrong finding makes self-report actively anti-informative.
4. **Near-zero setup friction on prosumer hardware.** The local-model community is large and motivated by sovereignty (no data leaving the device, no terms-of-service revision revoking access), open weights trail frontier by roughly 3-6 months, and its loudest complaint is evenings lost to drivers and quantization.
5. **Verification-gated improvement, framed as such.** "Provably safe and controllable" is literally the stated public acceptance criterion. Human-approval-gated improvement is the only self-improvement story with public license, and the elite discourse independently treats the human gate as the safety property.
6. **Low cost as strategy, not thrift.** With bubble warnings from the Fed and IMF and data-center moratoriums as midterm campaign planks, hyperscale is both financially and politically exposed. Small local compute sits outside that blast radius.
7. **Human receipts as spendable assets, framed as agency rather than oversight theater.** The backlash is substantially about lost agency and jobs. A person's verified receipt being spendable positions humans as the value source.
8. **The publishing register the discourse now rewards:** benchmarks with intervals and evidence files, honest nulls, no predictions reported as discoveries. Among corporate researchers, 44% will not use AI to draft papers, 47% not to generate hypotheses, 49% not to design experiments. Credibility currently accrues only where external validation exists.

### What would not rebuild it

Leaderboards and rankings. Detection classifiers. Model-reported confidence. On-chain reputation markets (empirically empty and sybil-prone per arXiv:2606.26028). Vendor-asserted percentages. Predictions reported as discoveries. Any framing that competes on capability rather than on checkability.

---

## 4. Verifier-grounded RL: state of the art, and what a local environment can realistically achieve in 2026

### Settled as of mid-2026

- **RLVR is the mainstream post-training paradigm for reasoning, with GRPO as the de facto algorithm.** The design question has moved from "does verifier reward work" to "how do you keep verifiers honest and exploration alive". AlphaProof in Nature is the peer-reviewed evidence that accept/reject alone suffices as the training signal at scale, including test-time RL on auto-generated problem variants.
- **Zero-label RL scales.** Ring-Zero (Ring-2.5-1T-Zero, arXiv:2607.12395, verified by direct fetch upstream) reports RLVR from a base model with no human annotation at trillion scale, with phase-structured training and emergent self-verification. **Author-reported, no independent replication found.** The transferable part for small models is the stability machinery (clipped importance sampling, training-inference ratio correction, mixed-precision control), not the sample-efficiency claim.
- **Entropy collapse is the central failure mode and is now mechanistically understood.** Tokens with high covariance between log-probability and logit change drive it (Clip-Cov and KL-Cov target them); PPO clip bounds are asymmetric levers, clip-low raises entropy and clip-high lowers it. Crucially, collapse is now **recoverable**: TS-OPSD (arXiv:2606.00755) builds a self-teacher by temperature-scaling the collapsed model's own logits and distilling the smoother distribution back, with no external teacher and no extra inference cost, outperforming both continued RL and rollout-temperature reheating on Qwen3-4B/8B. Collapse becomes an incident, not a lost run.
- **The GRPO variant space has consolidated without a dominant winner.** Practical starting point: Dr.GRPO-style unbiased advantages (no length or std normalization bias) plus DAPO's clip-higher and dynamic difficulty filtering; GSPO's sequence-level ratios for large or MoE models. All shipped in local tooling.
- **Reward hacking of verifiers is a first-class research subject with a three-phase defense pattern:** fuzz verifiers for false accept/reject before training (arXiv:2606.01066); instrument environments with detectable exploits so gaming is itself measurable during training (Hack-Verifiable Environments, arXiv:2605.20744); run adversarial hacker-fixer hardening loops after (arXiv:2606.08960, following seven attack patterns achieving near-100% exploit success across eight benchmarks).
- **Consensus is not a verifier.** Majority-vote, confidence, and self-consistency rewards (the TTRL lineage) cause confirmation bias and entropy collapse, disproportionately penalizing high-entropy structural tokens. JURY-RL (arXiv:2604.25419) resolves this cleanly: votes propose, proofs dispose, and ResZero redistributes zero-mean variance-preserving signal when verification is inconclusive rather than reinforcing unverified agreement, matching ground-truth-supervised pass@1 with better pass@k and diversity.
- **The verifier is also the curriculum engine.** Online difficulty filtering keeps prompts in the learnable band; a proposer targeting "barely provable by the current prover" (STP, Absolute Zero at ICLR 2026, Bourbaki) turns the same verifier into a task generator. One grading pass buys both signal and syllabus, which is itself verification amortization.
- **Calibration is a published reward component.** RLCR (arXiv:2507.16806) augments binary correctness with a Brier-score term, improving calibration at no accuracy cost and beating post-hoc classifiers; TruthRL rewards truthfulness including abstention.
- **The local stack is settled and cheap.** TRL GRPOTrainer as the reference implementation, Unsloth kernels, vLLM for rollouts, verl for multi-node. Reward functions are plain Python callables, which is precisely the seam a receipt-issuing oracle layer wraps. Environments are now distributable artifacts (Prime Intellect `verifiers`, Hugging Face OpenEnv), so packaging and distribution are solved problems.
- **Standing sanity controls, from 2025 landmines:** a random-reward control arm every experiment (spurious rewards improved Qwen math scores, meaning apparent RLVR gains can be model-family artifacts); a non-Qwen base replication before claiming uplift; pass@k tracked as an exploration diagnostic rather than an objective.

### Genuinely unresolved

**Elicitation versus expansion.** Whether RLVR sharpens sampling toward what the base model could already do (base models winning pass@k at large k) or creates capability where the base is at 0% at any sampling budget (shown for VLM spatial reasoning at ACL 2026) has peer-reviewed support on both sides and no settling result as of 2026-07. Overtraining-driven diversity collapse is a confound.

### What a local-model epistemic training environment can realistically achieve in 2026

**Achievable, with named precedent:**

- Reliability and calibration gains on certificate-producing task families. This is the uncontested part of the verifier-RL benefit.
- 1.5B to 8B GRPO on a single consumer 12-24GB GPU (vendor VRAM claim aside, the stack is public).
- A 14B to 32B domain specialist wrapped in a strong oracle outperforming larger generalists in-domain. Precedents: RaDaR 32B (preprint), Goedel-Prover-V2 32B (ICLR 2026), Nemotron 3 Ultra open weights above the IMO gold threshold.
- Publishable results in extremal combinatorics and coding theory at tens of dollars of compute, using open tooling. Precedents: Zarankiewicz via OpenEvolve, constant-weight codes via a single-author LLM protocol.
- A working receipt ledger with audit-once amortization and replay artifacts. Every component exists as published design.
- Curriculum generated free from verifier pass-rate bands.
- Entropy collapse as a recoverable incident.
- Lossless compression and Lean kernel checks as zero-marginal-cost, unforgeable local oracles.

**Not achievable, or unproven, in 2026 at local scale:**

- New capability where the base model scores 0% at any sampling budget. Contested in the literature; do not design success metrics around it.
- Frontier-level open-conjecture resolution locally. The Erdős-class 2026 results used frontier generators, even when a local-runnable checker minted the receipt.
- A verified end-to-end analysis pipeline. **There is no precedent. The one checked case failed by 4.3x.** Building this is original work, not integration.
- Cross-domain receipt interchange. No standard exists to adopt.
- Cryptographic proof of inference. Off by four to five orders of magnitude.
- Wet-lab and randomized-endpoint tiers. Out of reach entirely; the environment can only consume receipts from them, never mint them.

**A realistic success criterion, stated in the register the discourse rewards:** the environment demonstrates that N oracle calls buy K verified receipts at a measured, falling marginal cost as the audit-once corpus grows, on task families where a third party can re-verify every claim offline. Not "the model got smarter".

---

## 5. Lane mapping: role in the training environment and the trust economy

| Lane | Training-environment role | Trust-economy role | Maturity | What it does not cover |
|---|---|---|---|---|
| **crucible** `C:\dev\public\crucible` | **Reward function of record.** `verdict_for` is pure, deterministic, fail-closed, with the model outside the verdict step, so fluent-but-wrong output cannot move the score. ProofMeasure gives the formal-oracle seam (Lean/Coq/type-checker). JudgeMeasure keeps a rubric judge strictly outside the verdict, satisfying R7's propose/dispose split. The refine loop's weakest-axis grading plus typed missing-evidence explanations give shaped feedback and credit assignment instead of bare pass/fail. UNVERIFIABLE as a first-class verdict is R15 already implemented. | **Receipt mint and standing check.** Sealed assessments with sha256 per claim; tamper detection (MATCH/MISSING/CORRUPT); `crucible ci` proves standing has not regressed against a sealed baseline; cleanroom `--bundle` packets let a third party accept a result from the packet boundary alone (R8b replay artifact); `recheck` oracle replay packs give bounded spot re-verification without opening a second verdict path (R11 commit-then-audit). TelosMeasure re-runs the named verifier rather than trusting a carried certificate, which is the correct trust-boundary posture. | Shipped, PyPI crucible-bench 1.2.0, zero third-party runtime deps | Oracle-tier field (R1); input-manifest hashing (R2); verifier fuzzing (R6); denominator accounting (R4); statement-fidelity attestation split (R13); signing keys held outside model reach (R10) |
| **forum** `C:\dev\public\forum` | **Rollout harness.** `forum submit --cmd "ollama run <local-model>"` runs local episodes with budgets and deterministic routing; every request, plan, task, result, and verdict lands in a causal chain, i.e. trajectories with full provenance. The `VerifierProvider` seam is where crucible plugs in as reward. Tiered executors (`--cheap-cmd`/`--capable-cmd`/`--frontier-cmd`) with witnessed escalation produce graded-difficulty signal: what the small model failed and a stronger tier passed is a natural preference pair and a natural learnable-band probe. Human gates with durable deadlines are the verification-gated-improvement mechanism section 3 says has public license. | **Receipt substrate.** Hash-chained content-addressed ledger; `verify(deep=True)` catches body tampering a chain-only check misses; crash-safe resume already implements reuse-without-re-execution for tasks witnessed successful; ledger capsules compact a verified run into a reusable brief; `bench-deep-verify` prices verification cost honestly (R4-adjacent). Satisfies R16 without inventing a log format. | Shipped, PyPI forum-engine 1.13.0, 533 tests, zero runtime deps | Per-entry cryptographic signatures (R10); OpenTelemetry GenAI vocabulary alignment (R16); receipt decay and cross-lane invalidation (R12); the RL trainer itself |
| **learn** `C:\dev\public\learn` | **Curriculum generator over verified knowledge, and calibration trainer.** The mastery gate reads only witnessed attempts, so reward never comes from the scheduler. Misconception aggregation is error-driven sampling for the next batch. Predict-then-observe is a calibration mechanism and the natural home for an RLCR-style Brier term (R6 of the VRL implications). `prooflesson` already converts verified-claim packets with MATCH/DRIFT/UNVERIFIABLE verdicts into curriculum items, which is the R8a amortization pattern applied to pedagogy. `derive-schedule` replays the witnessed log and audits cached state as DRIFT with per-field diff, which is R9 recomputable-not-stored. | **Portable competence receipts, and the operator-calibration record (R14).** Study receipts re-verify from their own recorded evidence rather than a stored boolean, with typed failure modes (CHAIN_BROKEN, VERDICT_MISMATCH, UNVERIFIED). The credential engine halting at every graded step is the human-attestation boundary R13 needs, though it currently attests consent rather than statement fidelity. | Shipped, npm @harperz9/learn, registry pins 1.6.0, 284 tests, zero deps. Repo runs ahead of npm | Abstention as a reward channel; statement-fidelity attestation with decay (R13); operator calibration as a receipt field rather than a local log |
| **index** `C:\dev\public\index` | **Auto-gradeable task supply over real code, plus the honest-uncertainty trainer.** Structure questions (does A depend on B, who calls X, which layer rule is breached) with ground truth re-derived cheaply and deterministically by `verify`/`check`/`symbols`. Context envelopes carry typed omission codes (e.g. `budget_exceeded`), so the model learns to request more context instead of inheriting confidence from a missing file. That is the closest thing in the six lanes to training abstention. | **Cache invalidation, which is R12 and the hardest part.** Commit-pinned sealed wikis and envelopes with `--verify` freshness re-derivation; FRESH/STALE certificates; `index invalidate` names exactly which artifacts a change voided with typed reasons. Deterministic byte-identical output makes every artifact independently re-derivable. | Shipped, PyPI index-graph 2.9.0, Beta, 585 tests | Nothing about oracle tiers or non-code domains; its invalidation model is per-artifact and not yet generalized to receipts minted by other lanes |
| **gather** `C:\dev\public\gather` | **Evidence supply line and built-in grounding check.** `verify_record` rejects any LLM-proposed field value not grounded in fetched content, which makes grounded extraction a directly rewardable task and is R3 at the intake boundary. The `method` field keeps directness of evidence on the record (HTTP fetch vs OCR vs synthesis), so reward can be weighted by evidence quality, which is R1 applied to sources. `gather.track` element MATCH/RELOCATED/DRIFT/GONE gives a freshness signal on live sources. | **Cross-lane amortization, already operating.** Sealed digests over content-addressed bodies mean `gather corpus verify` proves a corpus untampered once, and crucible's GatherDigestMeasure consumes those digests as evidence without re-fetching. That is R8a working across lanes today. Per-item provenance receipts (source, ref, method, timestamp, sha256) are the R2 shape at the source layer. | Shipped, PyPI gather-engine 1.6.1, zero-dep core | **Novelty verdicts (R5).** `scholar` reaches OpenAlex, Semantic Scholar, and Crossref with DOI dedup and citation edges, which is the retrieval half; there is no oracle that returns "this result is or is not already in the literature" |
| **telos** `C:\dev\public\telos` | **Episode definition format and the propose-verify-promote loop.** Proof packets are complete verifiable episodes whose pass/fail recomputes from materials embedded in the packet, making a canned pass structurally impossible, with negative controls guarding against reward hacking (directly answering R6 and the Hack-Verifiable Environments pattern). The learning-forge daemon promotes only verified changes, which is the loop shape section 3 says has public license. model-foundry is the routing contract for splitting work between a local 14B and frontier APIs. The nine doctors are offline auto-gradeable task families. | **Exchange unit.** The self-contained proof packet is the natural spendable receipt: anyone replays `proof.mjs verify` from the packet alone (R8a). The `telos.witnessed-artifact/v1` envelope consumed by crucible's TelosMeasure defines the honest boundary of the economy: receipts travel, and cheap re-verification stays possible and is exercised at trust boundaries (R11). Every command emitting a `project-telos.flagship-action/v1` envelope with MATCH/DRIFT/UNVERIFIABLE is uniform verdict vocabulary across the workbench. | **Pre-release, 0.2.0.** 60+ contract test files run individually in CI on Node 24, npm publishing operator-gated, interfaces may move between minors. Least shipped, most integration-critical | Interchange to non-telos trust domains (R18); signing and key custody (R10); tier-aware pricing of the packets it mints (R1) |
| **lane layer** `C:\dev\local-model\harness\lanes.py` | **Provisioning, and reward integrity via honest degradation.** Spins up all six flagships as MCP tools the local model can call inside rollouts. The health model matters for correctness of reward: an absent or stale verifier lane reports `missing`/`stale`, so the environment degrades to UNVERIFIABLE rather than a fake pass. The `local-model` lane's organ name, propose-verify, is the training thesis. | **Provenance of the mint.** Pins expected versions, detects drift as `stale`, and records the installed roster at `FLYWHEEL_HOME/lanes.json`, so every receipt can answer: which lane, which version, was it live when this was witnessed. That is R2 at the tooling layer. | Internal harness module, 0.1.0, bundled, not published, docstring-level spec | Version pins are declared, not cryptographically bound to receipts; no attestation that the roster recorded is the roster that ran |

### Roles with no lane coverage

Ordered by how much they block the design.

1. **The RL trainer itself.** No lane implements a GRPO loop, entropy and log-prob/logit-covariance instrumentation, clip-low/clip-high asymmetry control, or TS-OPSD reheating recovery. `lanes.py` provisions oracles; nothing consumes their verdicts as gradient. This is the largest single gap and the one with the most settled external stack to adopt (TRL GRPOTrainer plus Unsloth plus vLLM).
2. **A Lean 4 plus Mathlib toolchain as a managed oracle.** crucible's ProofMeasure is a seam; telos declares proof lanes. Nobody provisions, pins, caches, or version-tracks the actual kernel and library corpus, and R8a amortization depends entirely on a growing local formal corpus.
3. **A construction-certificate checker library.** Ramsey and Zarankiewicz witness graphs, constant-weight codebooks, generator matrices with exact distance computation, matrix-multiplication tensor decompositions, packings, gadget reductions. This is the cheapest oracle class in the entire corpus and the correct first curriculum, and no lane contains a single such checker.
4. **A pinned-version, seeded simulator harness.** Physics engine, ODE/PDE solvers, molecular dynamics, DFT, open-weight MLIPs and predictors callable as local oracles. arXiv:2604.11805 is the existence proof for this as a training signal, and there is no lane for it.
5. **Verifier QA: adversarial fuzzing of oracles for false accepts and false rejects.** crucible measures are fail-closed by construction, which is necessary but not the same as tested. R6 requires oracles be attacked before their verdicts are treated as receipts.
6. **Reward-hacking instrumentation.** No lane embeds detectable exploit opportunities whose exploitation is itself verifiable, and none runs periodic hacker-fixer hardening as maintenance.
7. **A novelty oracle (R5).** gather retrieves; nothing renders a novelty verdict. Given that 8 of 13 "solved" Erdős problems were rediscoveries, a correctness-only economy will mint false novelty receipts at a high base rate.
8. **Signing and key custody outside model reach (R10).** All lanes use hash chains and content addressing, which detect tampering by an honest-but-careless party. None holds a signing key the model cannot reach, which is what makes a receipt unforgeable rather than merely tamper-evident.
9. **Oracle-tier and denominator fields in the receipt schema (R1, R4).** No lane records which tier of oracle disposed a verdict, nor attempts / oracle calls consumed / hits. Both are schema changes, cheap to make now and expensive to retrofit after receipts accumulate.
10. **The statement-fidelity attestation tier with decay (R13).** learn halts at consent and grading steps; telos packets carry non-claims. Neither is a human attestation that a formal statement means what the domain expert meant, non-transferable and decaying.
11. **Cross-lane receipt decay and expiry policy (R12).** index has per-artifact freshness and named invalidation; that model is not generalized to receipts minted by crucible, telos, or gather, and no lane implements value decay for receipts nobody has re-verified.
12. **Cross-domain interchange (R18).** Nothing translates a telos packet, a crucible seal, or a gather digest into a form spendable outside the Flywheel, and no standard exists to adopt.
13. **Operator calibration as a receipt field (R14).** learn tracks a learner's state locally. No receipt carries who was holding it, under what workflow, with what demonstrated calibration.
14. **Distribution as a `verifiers`-compatible package.** Prime Intellect `verifiers` and OpenEnv are the existing packaging and distribution channels for RL environments. Shipping into them is the difference between an environment the operator runs and one the local-model community can run.

---

## 6. Explicit unknowns

**About the evidence itself**

1. I did not independently verify any claim in this synthesis. Everything post-January-2026 rests on the upstream passes' retrieval on 2026-07-25, most of it at abstract or snippet level rather than primary full text.
2. The two upstream passes report **different value sets** for the Ramsey bounds in arXiv:2603.09172. At least one is wrong. Resolve by reading the paper before any republication.
3. Aletheia's IMO-ProofBench Advanced figure is 95.1% in secondary coverage and 90% in DeepMind's own blog. Possibly different checkpoints, possibly an error.
4. Numeric details quoted from machine-generated search overlays (25,000 Lean lines, exact percentages, the 91% chromatin reduction, the 79x cleavage ratio, the 10-25% AlphaGenome margin) are unconfirmed at primary source.
5. The unit-distance conjecture disproof, the most-covered mathematical result of 2026, has **no located preprint and no Lean formalization**. Its receipt is human review only.

**About the design**

6. **Whether verifier-RL creates capability or only sharpens sampling is unresolved in the published record.** Both positions have peer-reviewed support. This changes what the environment can promise, not whether it is worth building.
7. **Whether Ring-Zero-scale zero-label results transfer downward** to 14B-32B is untested. No independent replication of Ring-Zero exists.
8. **Whether the analysis step can be made verifiable in practice.** No precedent exists. The one measured attempt failed by 4.3x. Content-hashing raw data plus analysis code is the obvious mechanism; whether it survives contact with real oracle output is unknown.
9. **Whether audit-once lifts stay correct as sources change.** EG-VAR names the failure directly: a semantically wrong audited lift certifies wrong claims forever. There is no published estimate of lift-drift rate, and gather's element-tracking DRIFT signal is the closest available proxy.
10. **What a novelty oracle actually costs.** Literature identification is a verification problem, not a retrieval problem, and nobody in the corpus reports its price per claim.
11. **What receipt decay rate is correct.** Too fast and nothing amortizes; too slow and stale receipts circulate. No published system reports a rate. This will have to be measured locally.
12. **Whether the trust economy can operate with a single operator.** Every trust mechanism in the corpus assumes multiple parties. A single-maintainer receipt economy has no counterparty to spend receipts with, which may mean the initial value is entirely intertemporal (today's operator spending yesterday's receipts) rather than social. Untested.
13. **Whether receipts survive the local-first constraint.** Every shipping trust system assumes cloud or chain. Local-first offline-verifiable receipts are absent from the landscape, which means either an unclaimed opportunity or an unrecognized impossibility, and the corpus cannot distinguish these.
14. **Public sentiment on AI self-improvement specifically has never been measured.** The superintelligence-prohibition polls are the closest proxy and come from advocacy organizations. The claim that verification-gated improvement has public license is inferred, not established.
15. **Whether verification-cost amortization actually reduces marginal cost in practice** rather than shifting it into audit, invalidation, and re-verification overhead. This is the central economic claim of the design, and nothing in the corpus measures it end to end. It is the first thing the environment should instrument on itself.