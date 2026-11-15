# The Equivalence Gap in GenAI Mainframe Modernization

### An adversarial steelman — is LLM tooling (watsonx Code Assistant for Z, AWS Transform/BluAge, et al.) production-ready to modernize core-banking COBOL at scale? The translation is the easy 20%; the unforgiving 80% is verified behavioral equivalence — and nobody ships it.

**Author:** Zain Dana Harper — independent researcher, Seattle · github.com/HarperZ9 · ORCID 0009-0001-7175-5393
**Date:** 2026-06-20
**Run:** 002 — Frontier Research Session
**Rotation focus:** COBOL & legacy-system modernization (× fintech/financial-sector engineering; × ML code-translation; × verification).
**Part of:** *The Witnessing Spine* corpus · CC-BY-4.0 · companion [*Conferred Existence*](https://doi.org/10.5281/zenodo.20773724)
**Discipline:** claim ↔ evidence ↔ verdict; every cited source verified by retrieval; maturity labeled; nothing fabricated. Unverifiable folk-statistics are flagged and dropped, not repeated.
**Method:** four parallel web-grounded scholar agents (≈220 tool-calls; ~70 verified sources across arXiv cs.SE/cs.PL/cs.LG, ACM FSE/ASE/ISSTA/ICSE, IEEE TSE, US GAO, UK FCA/PRA/NAO/Treasury Committee, EUR-Lex, IBM/AWS/Rocket primary docs, IEEE Spectrum) → author synthesis and adjudication.

---

## 0 · Bottom line

The mainframe still runs the money — ~$3T/day in CICS transactions, 60M+ lines of COBOL at SSA alone, eight of eleven of the US government's most critical legacy systems on COBOL/Assembler costing **$754M/yr** (GAO-25-107795, Jul 2025). A 2025–2026 wave of GenAI tooling promises to finally modernize it. The steelman of that promise, adjudicated against the evidence, **fails at one precise joint**:

- **The easy ~20% is genuinely improved.** LLM tooling (IBM watsonx Code Assistant for Z; AWS Transform on the 15-year BluAge engine; Rocket/Micro Focus + GenAI) delivers real value in **comprehension, documentation, dependency mapping, and syntax-level translation**. The strongest *verified* case study (Egypt's NOSI, via WCA4Z) is a **comprehension** win — 79% less time to understand an app, 94% less to find dead code — not a conversion.
- **The hard ~80% — verified behavioral equivalence — is constitutively unmet.** Measured translation correctness collapses with scale and semantic complexity; no method can *certify* equivalence without a specification, which 50-year COBOL does not have; and in finance the arithmetic is *definitional*, so a sub-penny rounding mismatch is a regulatory event a 90-day parallel run cannot see.

Independent signal is blunt: **Gartner (Apr 2026): "more than 70% of mainframe exit projects initiated in 2026 will fail to produce the intended benefits due to an overestimation of generative AI tooling capabilities."** IBM's *own* validation papers state the translated code "cannot be trusted to correctly translate the original code." A differential-fuzzing study finds **19–35%** of LLM refactorings are non-equivalent and **21%** of those slip past existing test suites.

**Verdict (developed in §3): the claim is FALSE as stated.** The binding constraint of mainframe modernization was never translation — it is **verified equivalence without a spec**, and that is a witnessing/differential-evidence problem (re-derive behavior; compare to the legacy oracle; answer MATCH / DRIFT / UNVERIFIABLE *per path*, with explicit coverage accounting), not a code-generation one. That is the frontier opening: a high-budget, regulator-pressured need for exactly the proof-before-trust posture — re-derive behavior, compare to the legacy oracle, answer MATCH/DRIFT/UNVERIFIABLE per path with explicit coverage accounting — that current tooling cannot supply.

---

## 1 · Why this frontier matters

Run 001 mapped verifiable provenance for financial AI. Run 002 rotates to legacy/COBOL modernization — an underserved, high-budget stratum — and finds the *same shape of gap* (documented/translated vs. **verified**), now in a market where the buyers are banks, insurers, and governments with nine-figure programs and regulators watching. The relevant discipline is **semantic equivalence at the machine level** — compiler-internals and reverse-engineering reasoning — which is precisely what the GenAI translation wave cannot certify.

---

## 2 · The frontier in four strata

### 2.1 The tooling — what actually ships vs. what's marketed

- **IBM watsonx Code Assistant for Z (GA Oct 2023 → v2.6 Jun 2025).** Granite 20B code LLM fine-tuned on COBOL↔Java pairs. *Shipped:* code explanation (the feature reviewers consistently praise), refactoring assistance, paragraph-by-paragraph COBOL→Java transform, symbolic-execution unit-test generation, business-rule *documentation*, on-prem LLM. *Marketed:* "90%/59%/38%" productivity gains — from an internal IBM test, undisclosed methodology `[vendor-claim]`. IBM's own ICSE-2026 pipeline paper reports **median structural >80%, functional >75%** — but on **30 programs**, scored by **LLM-as-Judge**, by IBM Research `[IBM-authored]`. Independent IBM partner **CROZ**: transformation output "often requires significant manual clean up"; real value is explanation/knowledge-transfer, *not* automated transformation `[independent-practitioner]`.
- **AWS Transform (May 2025) on BluAge (acq. 2021).** Deterministic compiler-like COBOL→Java + JCL→Groovy + CICS/VSAM/Db2 runtime emulation — the mature part predates the AI layer. The agentic "Transform" orchestration claims **4.5B lines processed / 1.6M hours saved / 810 dev-years** — *no disclosed methodology* `[vendor-claim]`. Named customers (Itaú, Danske, BMW, Fiserv…) appear without auditable output metrics. **The managed runtime closed to new customers Nov 7 2025** (AWS lifecycle docs) — a notable signal.
- **Rocket Software (ex-Micro Focus/OpenText AMC, May 2024).** Visual/Rocket COBOL *compiles* COBOL for distributed/cloud/ARM; COBOL Analyzer + GenAI (Sep 2025) adds *explanation*, not automated translation `[vendor-claim]`.
- **Independent verdict — Gartner (Apr 2026, "Too Big to Fail…"):** **>70% of 2026 mainframe-exit projects will fail** from overestimating GenAI; AI is limited to identifying technical debt, "cannot handle comprehensive transformation" (via The Register, Heise) `[analyst-report]`.

### 2.2 Measured translation correctness — the compilation-vs-correctness gap

The single most replicated empirical finding: a 30–60 point gap between *compiles* and *behaves correctly*, widening with scale.
- **AlphaTrans** (arXiv:2410.24117): **96.4% syntactic → 25.1% functional** on real Java repos. `[preprint]`
- **RepoTransBench** (arXiv:2412.17744, IEEE TSE 2026): best **32.8%** success; **dynamic→static <10%** (COBOL→typed-OO is the hard direction). `[peer-reviewed]`
- **RepoMod-Bench** (arXiv:2602.22518): **91.3%** pass on <10K-LOC repos → **15.3%** on >50K — *scale collapse*, not a prompt-tuning problem. `[preprint]`
- **ClassEval-T** (arXiv:2411.06145, ISSTA 2025): method-level 80%+ does **not** transfer to class-level real code. `[peer-reviewed]`
- **Lost in Translation** (arXiv:2308.03109, ICSE 2024): **2.1–47.3%** correct depending on pair; "LLMs are yet to be reliably used to automate code translation." `[peer-reviewed]`
- **COBOL specifically — COBOL-Coder** (arXiv:2604.03986): GPT-4o **16.4% Pass@1 / 41.8% compile** on COBOL; StarCoder2/DeepSeek **0%/0%**; domain-adapted COBOL-Coder reaches 49.3% Pass@1 — still a coin-flip-grade ceiling, and Pass@1 ≠ behavioral equivalence. `[preprint]`
- **Silent errors undercount** — differential fuzzing (arXiv:2602.15761): **19–35%** of LLM refactorings non-equivalent, **21% undetected by existing tests**; ProbeGen (arXiv:2502.18473): **18%** of benchmark-"equivalent" pairs fail under counterexample search. `[preprint]`

### 2.3 The equivalence-verification gap — you cannot certify what you cannot specify

- **The test-oracle problem.** Migrating 40-year-old COBOL: the spec doesn't exist, the authors are gone, the business logic *is* the code, and the existing tests validate the old behavior without semantic coverage. Passing them proves only that you pass them. The translated program's correctness cannot be certified against a reference that was never written.
- **LLM-as-Judge is near-chance on equivalence** — **EquiBench** (arXiv:2502.12466): best models **63.8%** on the hardest equivalence-checking categories (50% = random); "models rely on syntactic similarity, not robust reasoning about semantics." This directly undercuts IBM's LLM-as-Judge "functional >75%."
- **What formal methods reach — and don't.** VERT (arXiv:2404.18852, ASE 2025) verifies via a WebAssembly oracle — **COBOL doesn't compile to WASM**. LLMLift (arXiv:2406.03003, NeurIPS 2024) hits 100% on **23 curated kernels** in a narrow domain. Symbolic execution for COBOL→Java (Sneed & Verhoef, SWQD 2017 — *manual* path alignment; IBM Hans et al., FSE 2025, DOI 10.1145/3696630.3728548 — automated test-gen) is the most principled approach but is bounded to *procedure scope*, struggles with COBOL's REDEFINES/implicit-file semantics, and publishes no recall/coverage numbers at scale. "Articulate but Wrong" (arXiv:2605.21537, ASE 2026): **39.7% semantic drift** on tricky legacy code, **31.7% silently endorsed by the producing model.**

### 2.4 The hard 80% — semantics, data, orchestration

The non-code substance that resists translation:
- **Arithmetic is definitional.** COMP-3 **packed decimal** / zoned decimal are **base-10 fixed-point**; PIC `9(7)V99` encodes an *implied* decimal point as a type constraint. Mapping to Java `double`/`float` (IEEE-754 binary) cannot represent base-10 exactly; even `BigDecimal` matches COBOL only if **rounding mode and scale are pinned per field** (IBM documents precision loss on COMP-1/2→IEEE via `__fp_htob()`). A tool that auto-maps to `double` injects systematic, sub-penny, compounding error. `[vendor-spec]`
- **EBCDIC ≠ ASCII** — different *collation order* (lowercase < uppercase in EBCDIC); any sort/compare/range silently changes unless the collating sequence is remapped. Byte-level file conversion **corrupts interleaved COMP-3** fields (shared byte values) — field-aware conversion is mandatory. `[industry/vendor-doc]`
- **REDEFINES** (same memory, multiple types, app-selected), **level-88** (SET-TO-TRUE writes the *first* VALUE — no modern equivalent), **OCCURS DEPENDING ON** (runtime size set by a counter that may arrive from a *different program upstream*), **ALTER** (runtime self-modification of GO TO targets; ANSI-1985-obsolete but still compiled) — each breaks the modern assumption "a location has one type and static control flow is knowable." `[industry; arXiv:2604.00936 names REDEFINES/OCCURS/COMP-3 as concrete obstacles]`
- **JCL + VSAM/IMS** — the under-weighted orchestration layer: return-code conditional chains, symbolic PROC overrides, GDG/tape/scheduler (CA-7/TWS) integration, orphaned-but-runnable jobs; IMS hierarchy→relational and VSAM-KSDS status-code semantics don't map cleanly; **copybook** changes ripple across hundreds of programs via an undocumented dependency graph. `[industry; in-com, softwaremining, keyhole, Thoughtworks]`

### 2.5 The stakes and the failure record (verified)

- **TSB (Apr 2018)** — 5.2M records to Proteo4UK; ~8 months disruption, **225,492 complaints**, **£32.7M redress**, **£48.65M FCA+PRA fine** (a former CIO individually fined). Nine dress rehearsals didn't catch it. `[regulator-primary]`
- **SSA DCPS** — **$355M spent, discontinued May 2015**; killed by *state-specific business-logic* variation that couldn't be abstracted (SSA OIG, 2016). `[gov-report]`
- **RBS/NatWest CA-7 (2012)** — scheduler corruption → **100M unprocessed payments**, 6.5M customers, **£56M fine**. The batch layer carries catastrophic concentration risk. `[regulatory]`
- **CA DMV ($134M abandoned, 2013), PA UCMS ($166.9M, 42 mo late), GAO-25-107795 (11 systems, $754M/yr, 8 COBOL, 7 unfixable-without-modernization vulns).** `[gov-reports / IEEE Spectrum]`
- **Barclays (Jan–Feb 2025)** — mainframe OS-module defect, 3 days over payday + HMRC deadline; **of authenticated users, 17% tried to pay and 56% of those failed**; £5–7.5M comp. Treasury Committee: **158 incidents / 803 outage-hours** across nine UK banks (Jan 2023–Feb 2025). **CBE Ethiopia (Mar 2024)** — a *routine update* opened a 12-hour unlimited-withdrawal window, ~490K transactions: the same failure mode (undetected behavioral regression from a system change) outside a migration. `[parliamentary / regulatory / press]`

### 2.6 What current best-practice verification actually achieves

Parallel/dual run, shadow/traffic-replay, golden-master/characterization testing (Feathers 2004), symbolic execution (Sneed–Verhoef; IBM FSE 2025), behavioral-comparison via state machines (Hendriks, arXiv:2205.08201). Their *shared* ceiling:
- **Coverage gap** — a 90-day parallel run covers daily/monthly paths well and **annual batch, rare product codes, and 30–50-year loan-maturity edges ≈ zero**.
- **Semantic gap** — golden-master "does not infer correctness of the results … merely detect[s] unwanted effects of change"; it canonizes the legacy bug as the oracle.
- **Arithmetic gap** — a 0.001¢/txn error is below the parallel-run detection threshold yet material at month-end accrual / annual report — i.e. **after cutover**.
AWS BluAge's own "validate functional equivalence" reduces, in the docs, to **manual scenario comparison** ("capture and replay"). The MDPI 2024 survey on formal verification of code conversion explicitly identifies "a significant research gap in pinpointing appropriate formal verification approaches."

---

## 3 · The adversarial steelman (claim ↔ evidence ↔ verdict)

> **CLAIM (strongest form).** *GenAI/LLM tooling (WCA4Z, AWS Transform/BluAge, Rocket+GenAI) is now production-ready to modernize core-banking COBOL legacy at scale — automating translation, accelerating projects, and de-risking the work that used to fail.*

**Evidence FOR (steelmanned).** The comprehension/documentation/dependency-mapping value is real and verified (NOSI 79%/94%; CROZ and Thoughtworks both credit comprehension). Domain fine-tuning genuinely beats general LLMs on COBOL (COBOL-Coder 16.4%→49.3% Pass@1; WCA4Z >> ChatGPT on the IBM benchmark). The mature deterministic engines (BluAge) have 15 years of refactoring track record. IBM's ICSE-2026 functional >75% is the most specific number in the field. `[verified]`

**Evidence AGAINST (decisive).**
1. **Correctness collapses exactly where core banking lives — at scale and at semantic complexity.** 96%→25% (AlphaTrans); 91%→15% at >50K LOC (RepoMod-Bench); GPT-4o 16.4% Pass@1 on COBOL; 2.1–47.3% (Lost in Translation). `[peer-reviewed/preprint]`
2. **The headline correctness number is judge-by-LLM, and LLMs are near-chance at equivalence.** IBM's >75% is LLM-as-Judge on 30 programs; EquiBench shows 63.8% on hard equivalence (≈random). IBM's own validation papers premise themselves on translated code being *untrustworthy*. `[verified]`
3. **Silent non-equivalence is systematically undercounted** — 19–35% non-equivalent, 21% test-invisible (differential fuzzing); 18% false-equivalent (ProbeGen); 31.7% of semantic drifts self-endorsed (Articulate-but-Wrong). `[verified]`
4. **The 80% is not code** — COMP-3 arithmetic, EBCDIC collation, REDEFINES/level-88/ODO/ALTER, JCL orchestration, VSAM/IMS data — none of which any tool *claims* to certify, and data migration is out of scope for all three. `[verified]`
5. **Verification can't certify equivalence without a spec the legacy lacks; finance makes the residue catastrophic** — sub-penny COMP-3→IEEE/BigDecimal error invisible to parallel run, material over a loan lifecycle; the failure record ($355M SSA, £330M+fine TSB, $754M/yr GAO) and Gartner's >70%-fail prediction are the empirical seal. `[verified]`

> **VERDICT — FALSE AS STATED.** "Production-ready to modernize core-banking COBOL at scale" conflates the solved-and-valuable easy 20% (assistive comprehension + syntax translation) with the unsolved load-bearing 80% (**verified behavioral equivalence** of semantics, data, and orchestration, under a regulator, with no spec). The honest claim is narrower and true: *GenAI is a strong comprehension and developer-assist accelerator that reduces — but cannot retire — the equivalence-verification burden, which remains the binding risk.* Treating tool output as production-safe migration is precisely the overestimation Gartner forecasts will sink >70% of 2026 exits.

---

## 4 · The gap, named — and the shape of what closes it

The binding constraint is **verified equivalence without a specification**. That is not a code-generation problem; it is a **witnessing / differential-evidence** problem, and the current ceiling exists because the field reports a *binary project-level* "the parallel run passed" instead of a *per-path, coverage-accounted* verdict.

What the missing layer looks like:
- **A differential equivalence harness that answers MATCH / DRIFT / UNVERIFIABLE per execution path**, not pass/fail per project — exactly EMET's MATCH/DRIFT/UNVERIFIABLE turned on behavior instead of bytes.
- **Explicit coverage accounting** — it says "these N paths are witnessed-equivalent over this input distribution; these M (annual batch, rare product codes, 50-year maturities) are UNVERIFIED" — replacing risk-management evidence (parallel run) with verification evidence honestly bounded. This is *proof before trust* made operational.
- **Arithmetic-semantics oracles** — pinned COMP-3/rounding-mode differential checks at field granularity (a compiler/RE-grade concern), the class of error machine-level (compiler/RE) analysis is built to catch.
- **Symbolic + replay composition** — extend procedure-scope symbolic execution (IBM FSE 2025) with cross-program/integration witnessing, the unaddressed seam (Run 001's "cross-stage linkability" reappears here as cross-program equivalence).

No vendor ships this; the academic pieces (symbolic exec, differential fuzzing, behavioral comparison) are not composed into a coverage-accounted, finance-grade, witnessed equivalence protocol. Specifying and adversarially analyzing one is the paper-grade contribution.

---

## 5 · Open problems worth a paper (next-run candidates)

1. **Coverage-accounted differential equivalence harness for legacy migration** — per-path MATCH/DRIFT/UNVERIFIABLE + an explicit unverified-path ledger; arithmetic-semantics (COMP-3/rounding) oracles; integrate symbolic-exec + traffic-replay; map to DORA/PS21/3 resilience-testing evidence. *(the §4 build; highest leverage)*
2. **A defensible COBOL-migration equivalence benchmark** — the field has no enterprise-scale, spec-free, behavioral-equivalence ground truth (every current number is LLM-judged or tiny). Constructing one is itself publishable.
3. **Quantifying the arithmetic residue** — empirically measure COMP-3→IEEE/BigDecimal divergence accumulation over realistic loan/insurance lifecycles; turn the "sub-penny → material" argument into measured curves.
4. **Cross-program / JCL-orchestration equivalence** — the integration seam symbolic execution doesn't reach.

---

## 6 · Consolidated verified source ledger (selected)

| # | Source | ID / URL | Date | Maturity |
|---|---|---|---|---|
| 1 | Gartner via The Register — >70% of 2026 mainframe exits to fail (AI overestimation) | theregister.com/2026/04/15/gartner_mainframe_exit_analysis | Apr 2026 | analyst |
| 2 | IBM Research — Enterprise-Scale COBOL→Java (ICSE 2026 SEIP) | research.ibm.com (…cobol-to-java…) | Apr 2026 | IBM-authored peer-reviewed |
| 3 | Automated Testing of COBOL→Java Transformation (IBM, FSE 2025) | arXiv:2504.10548 / DOI 10.1145/3696630.3728548 | 2025 | peer-reviewed |
| 4 | Automated Validation of COBOL→Java (IBM, ASE 2024) | arXiv:2506.10999 | 2024 | peer-reviewed |
| 5 | Differential-Fuzzing Eval of Equivalence in LLM Refactorings | arXiv:2602.15761 | Feb 2026 | preprint (independent) |
| 6 | AlphaTrans — repo-level translation | arXiv:2410.24117 | Oct 2024 | preprint |
| 7 | RepoTransBench | arXiv:2412.17744 (IEEE TSE 2026) | Dec 2024 | peer-reviewed |
| 8 | RepoMod-Bench — implementation-agnostic testing | arXiv:2602.22518 | Feb 2026 | preprint |
| 9 | ClassEval-T | arXiv:2411.06145 (ISSTA 2025) | Nov 2024 | peer-reviewed |
| 10 | Lost in Translation: Bugs Introduced by LLMs | arXiv:2308.03109 (ICSE 2024) | 2023 | peer-reviewed |
| 11 | EquiBench — equivalence checking | arXiv:2502.12466 | Feb 2025 | preprint |
| 12 | ProbeGen — disproving equivalence | arXiv:2502.18473 | Feb 2025 | preprint |
| 13 | COBOL-Coder | arXiv:2604.03986 | Apr 2026 | preprint |
| 14 | VERT — verified Rust transpilation | arXiv:2404.18852 (ASE 2025) | 2024 | peer-reviewed |
| 15 | LLMLift — verified transpilation | arXiv:2406.03003 (NeurIPS 2024) | 2024 | peer-reviewed |
| 16 | Articulate but Wrong — self-review failures in modernization | arXiv:2605.21537 (ASE 2026) | May 2026 | peer-reviewed |
| 17 | Portable & Secure CI/CD for COBOL (REDEFINES/OCCURS/COMP-3) | arXiv:2604.00936 | 2026 | peer-reviewed |
| 18 | Sneed & Verhoef — Validating Converted Java via Symbolic Execution | VU Research Portal (SWQD 2017) | 2017 | peer-reviewed |
| 19 | Hendriks et al. — Multi-level Behavioral Comparison | arXiv:2205.08201 | 2022 | preprint/peer-reviewed |
| 20 | IBM COBOL↔Java type mapping (COMP-3/IEEE precision loss) | ibm.com/docs cobol-zos 6.4 | current | vendor-spec |
| 21 | CROZ — honest WCA4Z review | croz.net/honest-take-on-watsonx-code-assistant-for-z | 2025 | independent-practitioner |
| 22 | Thoughtworks — Claude Code & COBOL reality | thoughtworks.com/insights (…cobol…) | 2025/26 | industry |
| 23 | AWS Transform one-year milestone (4.5B lines; no methodology) | aws.amazon.com/blogs/…/aws-transform-one-year-milestone | May 2026 | vendor-claim |
| 24 | AWS Mainframe Modernization lifecycle (managed runtime closed) | docs.aws.amazon.com/m2/…/lifecycle-m2 | Nov 2025 | official-docs |
| 25 | FCA — TSB fined £48.65m | fca.org.uk/news/…/tsb-fined-48m | Dec 2022 | regulator-primary |
| 26 | SSA OIG — DCPS modernization testimony ($355M) | oig.ssa.gov/…/2016-07-14… | Jul 2016 | gov-report |
| 27 | GAO-25-107795 — critical legacy systems ($754M/yr; 8 COBOL) | files.gao.gov/reports/GAO-25-107795 | Jul 2025 | gov-report |
| 28 | GAO-23-106821 — legacy systems | gao.gov/products/gao-23-106821 | May 2023 | gov-report |
| 29 | 2012 RBS CA-7 failure (£56M; 100M payments) | en.wikipedia.org/wiki/2012_RBS_Group_computer_system_problems | 2012/26 | secondary (cites regulator) |
| 30 | IEEE Spectrum — California DMV cancelled ($134M) | spectrum.ieee.org/…californias-dmv-it-project-cancelled | 2013 | industry |
| 31 | UK Treasury Committee — 158 incidents / 803 outage-hours | committees.parliament.uk/…/205611 | Mar 2025 | parliamentary |
| 32 | Barclays mainframe incident (via Global Treasurer / Committee) | theglobaltreasurer.com/2025/03/06/… | Mar 2025 | press/parliamentary |
| 33 | CBE Ethiopia glitch (routine update → unlimited withdrawals) | cnbc.com/2024/03/19/… | Mar 2024 | press |
| 34 | EU DORA Reg. (EU) 2022/2554 | eur-lex.europa.eu/eli/reg/2022/2554 | in force Jan 2025 | law |
| 35 | FCA PS21/3 Building Operational Resilience | fca.org.uk/publications/…/ps21-3 | Mar 2021 | regulator |
| 36 | OCC Bulletin 2026-13 (MRM revised; excludes migrations/GenAI) | occ.gov/…/bulletin-2026-13 | Apr 2026 | regulator |
| 37 | NAO — BoE RTGS renewal (£431M, 18-mo overrun) | nao.org.uk/press-releases/…rtgs… | Dec 2025 | gov-audit |
| 38 | MDPI — Formal Verification of Code Conversion: Survey | doi.org/10.3390/technologies12120244 | Dec 2024 | peer-reviewed (403; via secondary) |
| 39 | EBCDIC↔ASCII / COMP-3 corruption in migration | softwaremining.com/papers/Ebcdic-To-Ascii.jsp | 2026 | industry |
| 40 | JCL→COBOL mapping / orphaned jobs | in-com.com/blog/how-to-map-jcl-to-cobol… | 2026 | industry |

---

## 7 · Honest limits of this run

- **"60–67% of COBOL/mainframe migrations fail" is folklore.** No traceable primary source; Standish CHAOS is all-IT (~66% partial/total) not COBOL-specific; the "67% of mainframe-to-cloud" stat traces to a ~29-migration vendor sample. **Dropped** — the *named, verified* failures ($355M SSA, £330M TSB, CA DMV, PA, GAO totals) are damning without a fabricated rate.
- **Cross-domain extrapolation labeled.** The strongest silent-error numbers (differential fuzzing, ProbeGen, Articulate-but-Wrong) are general LLM-code or Python-2→3, *not* COBOL-specific; used as the *class* signal with that caveat, not as COBOL measurements.
- **Vendor numbers are vendor numbers.** IBM 90/59/38% and ICSE >75%, AWS 4.5B/1.6M-hours — undisclosed methodology / LLM-as-Judge; labeled and not treated as verified equivalence.
- **Unread primaries.** MDPI survey (HTTP 403) and the PA Auditor PDF were cited via secondary analyses, flagged. Some arXiv items were abstract-only (numbers not extracted) and excluded from quantitative claims.

---

## 8 · Deepen next

- **Next rotation:** quant/algorithmic ML (q-fin) adversarial steelman — *"deep models reliably beat classical methods out-of-sample"* (data-snooping, regime shift, backtest overfitting) — OR blockchain/crypto-economics (uncovered). Lean q-fin to close the financial-ML thread.
- **Carry-forward whitepaper:** the §5 #1 coverage-accounted differential equivalence harness — converges with Run-001's verifiable-provenance protocol on the *same* operator thesis (witnessed, coverage-honest, MATCH/DRIFT/UNVERIFIABLE evidence). Two rotations, one spine.

---

*Run 002 of* The Witnessing Spine *corpus. Claim↔evidence↔verdict; sources verified; folklore flagged and dropped; limits stated.*
