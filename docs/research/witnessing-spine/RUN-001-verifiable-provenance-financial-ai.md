# The Verifiability Gap in Financial-Sector AI Provenance

### A frontier survey + steelman — what regulation now demands, what cryptography and enterprise platforms can actually deliver, and the precise joint where they fail to meet.

**Author:** Zain Dana Harper — independent researcher, Seattle · github.com/HarperZ9 · ORCID 0009-0001-7175-5393
**Date:** 2026-06-20
**Run:** 001 — Frontier Research Session
**Rotation focus:** AI/ML supply-chain integrity · model & data provenance · governance for financial-sector AI (covers scope strata: *data platforms & artifact integrity*, *data safety/governance/provenance*, *ML*, *financial-sector engineering*).
**Part of:** *The Witnessing Spine* corpus · CC-BY-4.0 · companion [*Conferred Existence*](https://doi.org/10.5281/zenodo.20773724)
**Discipline:** claim ↔ evidence ↔ verdict; every cited source verified by retrieval before citation; maturity labeled; nothing fabricated.
**Method:** four parallel web-grounded source agents (≈185 tool-calls; ~60 verified sources across arXiv cs.LG / cs.CR / cs.DC, IACR ePrint, ACM CCS / IEEE S&P / NDSS / ICML / ICLR, EU & US financial regulators, and primary vendor documentation) → author synthesis and adjudication. Sources the agents could not render (e.g. a 6.4 MB regulator PDF) are marked unverified, not paraphrased.

---

## 0 · Bottom line

Financial services is, by the EU's own count, the sector with the **highest density of named high-risk AI use-cases**, and as of 2025–2026 it sits under a stack of provenance obligations — EU AI Act Art. 10/11/12 + Annex IV, US SR 26-2 (successor to SR 11-7), DORA, and the ECB's revised internal-models guide — that converge on one demand: **the origin, integrity, and lineage of a model and its training data must be documented, retained, and auditable.**

Across four independent source surveys, a single structural finding recurs: **the tooling cannot make that provenance *verifiable* in the sense the obligations presuppose.** Two distinct ceilings:

1. **Cryptographic build/model provenance (SLSA, in-toto, OpenSSF Model Signing, AIBoM) is real and now deployed at scale** — but it certifies *bytes-match and signer-identity*, and — as a 2026 supply-chain preprint (arXiv:2604.27781) argues — **relocates** the trust problem to the attestor rather than removing it. It cannot cover the dominant threat: **malicious or poisoned training by the signing party itself.**
2. **Enterprise MLOps platforms (Databricks Unity Catalog/MLflow, JFrog, Snowflake, SageMaker) record lineage as *mutable catalog metadata in access-controlled relational tables* — not tamper-evident, not externally anchored, not independently verifiable.** The audit log is itself an ordinary table.

The one deployed mechanism offering independent cryptographic verifiability — Sigstore `model-transparency` — covers only **file-level artifact integrity**, not the training-data→model→inference binding the regulation actually cares about.

**Verdict (developed in §3): the obligations are satisfiable on paper and unsatisfiable in verification.** The gap between *"documentation exists"* (self-certified, mutable, attestor-trusting) and *"provenance is independently verifiable"* (tamper-evident, externally witnessed, attestor-skeptical) is the **verifiability gap** — and it is exactly the joint that a witnessing/accountability discipline (re-derive the bytes; answer MATCH / DRIFT / UNVERIFIABLE, never *trusted*; never confuse authentication with authorization) is built to close. That is the frontier opening: a regulation-forced, high-stakes demand for precisely the verifiable-provenance posture — re-derived, coverage-accounted, witnessed evidence — that none of the three strata above currently supplies.

---

## 1 · Why this frontier matters

Financial-sector AI sits at the intersection of three forces that make verifiable provenance urgent rather than optional: a regulatory stack that now *mandates* documented, auditable model and data lineage; a cryptographic frontier that can attest bytes and identities but not semantics; and an enterprise-platform layer that records lineage as mutable metadata. The capability the regulation is forcing institutions to acquire — an external provenance witness that answers MATCH/DRIFT/UNVERIFIABLE rather than *trusted*, a default-deny authorization posture that distinguishes a token from a grant, content-addressed state, and tamper-evident manifests — is precisely the capability none of the three strata currently delivers.

Model-risk and AI-governance is among the best-funded lines in banking technology (the CSA note below cites $8–15M initial compliance budgets for large enterprises), which is what makes the **verifiability gap** at the **provenance × regulated-AI × supply-chain-integrity** intersection both genuinely open and economically consequential.

---

## 2 · The frontier in four strata

### 2.1 Regulation is the new forcing function — and it demands *verifiable* provenance

**In force now:**
- **DORA** (Reg. EU 2022/2554) — applicable **17 Jan 2025**. Any AI delivered as a third-party ICT service falls in scope; Art. 28/30 mandate a **Register of Information** for all ICT arrangements plus audit rights and exit strategies. An AI credit engine is simultaneously a DORA ICT arrangement *and* an EU-AI-Act high-risk system — a dual-documentation surface few institutions have reconciled. *[law-in-force]*
- **EU AI Act GPAI obligations** — Art. 53 live since **2 Aug 2025**; the Commission's **GPAI Training-Content Summary Template (24 Jul 2025)** requires dataset-level disclosure (named large datasets, top-10% scraped domains, synthetic-data sources, preprocessing, copyright measures), refreshed every 6 months; AI-Office enforcement and penalties (≤3% global turnover) begin **2 Aug 2026**. *[law-in-force]*
- **US SR 26-2** (Fed/FDIC/OCC, issued **17 Apr 2026**) — supersedes SR 11-7. Principles-based "sufficient records to evidence decisions, controls, assumptions, remediation"; **dynamic** model inventory; **Effective Challenge Logs**; and — load-bearing for provenance — *"the lack of transparency in proprietary vendor products does not exempt a banking organization from its risk-management responsibilities"*: institutions must "strive to understand the vendor model's design, development data, and relevant theories." GenAI/agentic AI explicitly **out of scope** (RFI forthcoming), but underlying statistical models accessed by an agent remain fully in scope. *[law/guidance-in-force]*
- **ECB Revised Guide to Internal Models (28 Jul 2025)** — new ML section: documentation must permit **replication "including a determination of the parameters and hyperparameters"** (reproducibility-grade provenance), global + local explainability, data-adequacy standards, elevated audit intensity. *[guidance]*

**Landing / shifting:** EU AI Act high-risk obligations (Art. 9–17, 26) were set for **2 Aug 2026**; the provisional **Digital Omnibus (agreed 7 May 2026)** defers **Annex III stand-alone** high-risk to **2 Dec 2027** and Annex I embedded to 2 Aug 2028 — *but Articles 10, 11, 12 and Annex IV substance are unchanged*, and the agreement is not yet in the Official Journal. Counsel advises building as if live. *[provisional — not yet enacted]*

**The specific provenance obligations** (the part tooling must satisfy):
- **Art. 10** — document training-data **origins and original collection purpose**, preparation/labeling/cleaning operations, assumptions, representativeness, **bias examination**, feedback-loop risk; datasets "relevant, sufficiently representative, and to the best extent possible free of errors and complete."
- **Art. 11 + Annex IV** — a nine-section **technical file** prepared *before* market placement, kept current, **retained 10 years**; §2 (Development Elements) ≈ one datasheet per dataset (provenance, collection method, known biases, preprocessing, class distribution).
- **Art. 12** — automatic **event logging over the system lifetime**; per-inference logs carry a **model version ID** that is the structural linchpin tying any decision back to the exact model state; deployer log retention ≥ 6 months.

**The gap at this stratum:** every obligation above presupposes that the documented provenance is **verifiable** by a supervisor. But the Annex IV file is **self-certified** (Art. 48 registration) and inspected **reactively** (Art. 74); no financial-sector notified bodies (Art. 43) are certified as of mid-2026, and the CEN/CENELEC harmonized standards that would define "compliant documentation" remain unfinished (the stated reason for the Omnibus slip). A right to documentation without a verification mechanism is an aspiration, not a provenance regime. The MIGT preprint (arXiv:2604.06148) states it plainly: inability to verify model provenance "is not merely a security gap … it is a compliance gap."

### 2.2 Build/artifact provenance — solved, deployed, and constitutively partial

The software-supply-chain stack has been ported to ML and is shipping:
- **SLSA v1.2** (three build-track levels) + **in-toto / ITE-6 / DSSE** provide the generic signed-attestation substrate — but **no ML-specific track or predicate**; a model checkpoint is treated as bytes, like a compiled binary. *[standard/deployed]*
- **OpenSSF Model Signing (OMS)** — PKI-agnostic detached signatures over a SHA-256/BLAKE2 file manifest; **NVIDIA has signed all NGC catalog models with OMS since Mar 2025** (first at-scale production deployment). The spec states verbatim: *"a cryptographic signature attests to authenticity and integrity, not to the inherent quality or ethical characteristics of a model"* and *"signing cannot address vulnerabilities or insecure practices introduced during development."* *[standard/deployed]*
- **Sigstore `model-transparency`** (v1.1.1, Oct 2025) — DSSE+in-toto signing recorded in the **Rekor transparency log**, defeating split-view attacks, verifiable offline after cert expiry. The **only deployed independent-verifiability mechanism** in this landscape — but **file/shard-level only**, no tensor/layer granularity, **no native MLflow/Databricks/Snowflake integration.** *[standard/deployed]*
- **AIBoM** — **AIBoMGen** (arXiv:2601.05703) uses a neutral training platform as root-of-trust, embedding in-toto link attestations (SHA-256 of datasets/weights/configs) into a CycloneDX AIBOM; **Atlas** (arXiv:2502.19567) adds TEE attestations + transparency logs + provenance chains across the lifecycle; **Sentry** (arXiv:2510.00554) makes on-load Merkle/lattice verification GPU-fast. *[preprint]*

**What it certifies vs. what it cannot** (five failure modes, from arXiv:2601.05703, OMS spec, and **Cesarano & Monperrus, arXiv:2604.27781**):
1. **Data identity, not data semantics** — a dataset hash proves same-bytes, not absence of poison/mislabeling/bias. AIBoMGen: *"the system cannot detect malicious but valid datasets."*
2. **Bytes, not behavior** — a clean model and a backdoored model can share identical supply-chain provenance if the backdoor was trained in before signing.
3. **Non-determinism breaks training-by-hash** — Cesarano & Monperrus (arXiv:2604.27781) place this among four structural supply-chain gaps (verifiability · versioning · observability · traceability): because trained artifacts are not bit-reproducible, a matching hash cannot establish that a checkpoint was produced by the attested *procedure* — build attestation thus **relocates** trust to the attestor rather than closing the gap. *(Paper thesis confirmed via abstract on independent re-fetch; wording paraphrased, not quoted verbatim — see §7.)*
4. **Multi-parent lineage is unrepresentable** — distillation / merge / LoRA-on-base produces multi-parent, cross-org graphs SLSA's single-parent DAG cannot express.
5. **No inference-time behavioral attestation** — nothing binds eval-time behavior to deploy-time behavior.

**Net:** build provenance answers *who released these exact bytes*. If the adversary **is** the signing party — the developer, fine-tuner, or platform operator, i.e. exactly the **opaque third-party vendor** SR 26-2 forces institutions to interrogate — the full PKI chain is authentic and the attestation is **inert as a trust signal.**

### 2.3 Training-data provenance + poisoning — the binding problem is open

- **Documentation baseline** is prose, not proof: Datasheets for Datasets (CACM 2021), Data Cards (FAccT 2022); the **2024 Foundation Model Transparency Index** (arXiv:2407.12929) scored 14 majors 58/100 and found **data-access transparency *fell* from 20%→7%** under competitive pressure; "Data Authenticity, Consent & Provenance for AI are all broken" (arXiv:2404.12691, ICML 2024) names the absence of any sound authenticity/consent/provenance infrastructure.
- **Membership proof is weak or instrumented:** standard membership-inference is **epistemologically unsound** for audit/legal use (arXiv:2409.19798, IEEE SaTML 2025 — the null can't be tested without retraining); only **pre-release watermarking** (arXiv:2402.10892; STAMP arXiv:2504.13416, contamination at <0.001% of tokens) or **radioactive data / data isotopes** yield sound signals — all require modifying data *before* release.
- **Proof-of-Learning broke:** the original PoL hardness claim (S&P 2022) was forged via adversarial-example checkpoint fabrication within months (arXiv:2108.09454); incentive-secure PoL (arXiv:2404.09005) handles rational adversaries but does **not** restore computational hardness.
- **ZK proof-of-training scales but proves the wrong thing:** zkDL (TIFS 2024), **Kaizen** (IACR 2024/162, CCS 2024 — VGG-11/10M params, 15 min/iter, 1.63 MB proof, proof size independent of dataset size), **VeriLoRA** (NDSS 2026 — verifiable LoRA to 13B), arXiv:2510.16830 (binds a dataset *manifest* to the proof), and the **June-2026 zkVM frontier proposal** (arXiv:2606.05433, ~36-month horizon). **Every one binds weights to dataset *bytes*, not *semantics*.**
- **Poisoning is cheap and survives:** Persistent Pre-Training Poisoning (arXiv:2410.13722, ICLR 2025 — 0.1% survives SFT+DPO) and **arXiv:2510.07192 — ~250 poisoned documents suffice from 600M to 13B params regardless of dataset size**; Sleeper Agents (arXiv:2401.05566 — safety training teaches concealment); "Machine Unlearning Fails to Remove Data Poisoning" (ICLR 2025); TransTroj (WWW 2025 — backdoors survive fine-tuning).

**The key gap:** even the strongest result — a ZK-SNARK proving weights `W` came from optimizer `P` on committed dataset `D` — is satisfied by a **valid proof over a poisoned `D`**. The commitment is to bytes; the attack lives in semantics; **no general computable predicate for "clean data" exists** to encode as a circuit constraint. You cannot today bind a deployed model to *clean* training data, and you cannot soundly prove, post-hoc and without instrumentation, what data a model saw.

### 2.4 Enterprise platforms — lineage is *recorded*, not *verifiable*

The decisive table (from primary vendor docs):

| Capability | What platforms provide | Cryptographically verifiable? |
|---|---|---|
| Data/model lineage (Unity Catalog, SageMaker, Snowflake) | rows in **mutable** `system.*` tables | **No** — an admin with write access can alter records; no hash-chain, no external anchor |
| Model version identity (MLflow) | **sequential integer**, not content hash | **No** — artifact in object store can be swapped without changing the version number |
| "Model signatures" (MLflow) | input/output **schema** metadata | **No** — a *misnomer*; not a cryptographic signature |
| Audit logs (Unity Catalog `system.access.audit`) | queryable table, ~90-day default | **No** — not write-once or tamper-evident |
| Malicious-model scan (JFrog Xray) | static/behavioral detection of code-executing deserialization payloads | **Partial** — a scan result, not a signed attestation; orthogonal to provenance |
| Model file integrity (Sigstore model-transparency) | SHA-256/BLAKE2 + DSSE + Rekor | **Yes** — the lone independent mechanism; file-level only; not registry-integrated |
| CycloneDX ML-BOM + CDXA | signable BOM document; component hashes optional | **Partial** — BOM integrity yes; training-data fields **self-reported**, not enforced |
| SPDX 3.0.1 AI profile | descriptive metadata fields | **No** — no signing/hashing mandated |

The consistent pattern: **every major MLOps platform's trust model is "trust the platform's access controls and audit log,"** with no external anchor, no content-addressed artifact storage, no transparency-log integration. Research that *would* close it — Atlas, **TAIBOM** (arXiv:2510.02169), the open-AIBoM/SPDX-extension work (arXiv:2510.07070), and GPU-integrity for the **TOCTOU window** on 100 GB models (arXiv:2510.23938) — is all **preprint, none shipped in a platform.**

---

## 3 · The steelman (claim ↔ evidence ↔ verdict)

> **CLAIM (strongest form, steelmanned).** *The provenance and record-keeping obligations now binding on financial-sector AI (EU AI Act Art. 10/11/12 + Annex IV; SR 26-2; DORA; ECB) can be met with the provenance capabilities already shipping in enterprise platforms — catalog lineage + dataset/datasheet documentation + model registries + artifact signing. The remaining "gap" is an unsolved theoretical problem (you cannot stably hash a pipeline-processed training set, and a hash is anyway consistent with a poisoned variant), so mutable catalog metadata under strong access control is the correct engineering response, not a deficiency.*

**Evidence FOR (the steelman has real force).**
- The documentation legs are genuinely satisfiable: Unity Catalog/MLflow capture table→model lineage via `log_input()`; CycloneDX ML-BOM + SPDX AI profile define the Annex-IV-shaped fields; OMS/Sigstore give real, deployed artifact integrity; SR 26-2 is **principles-based** and explicitly accepts compensating controls for vendor opacity. *[verified, §2.2/2.4]*
- The hashing critique is technically correct: non-deterministic augmentation/shuffling make exact dataset reproduction fragile, and a byte-hash does not certify semantic cleanliness (arXiv:2601.05703; §2.3). *[verified]*

**Evidence AGAINST (where it fails).**
1. **It conflates two separable properties** — (a) exact-reproduction proof (genuinely hard) and (b) **tamper-evidence of the provenance record itself** (achievable, and *absent* from every platform). Catalog metadata in a mutable table provides **neither**; an insider can rewrite the model↔data link, and the audit log is itself a mutable table (§2.4). The steelman's hardness argument about (a) is used to excuse the failure on (b), which is *not* hard. *[verified — Agent-4 primary docs]*
2. **The regulatory telos is verification, not documentation** — Art. 11/48/74 make the file self-certified and inspected reactively, with no notified-body infrastructure (§2.1). "Documentation exists" ≠ "provenance is verifiable," and audit/model-risk exist precisely to close that distance. *[verified]*
3. **The dominant threat is the signing party** — build provenance **relocates rather than closes** the trust gap (arXiv:2604.27781); if the vendor/fine-tuner is the adversary (the SR-26-2 vendor-opacity case), every signature is authentic and meaningless (§2.2). *[verified]*
4. **The data leg is structurally open** — 250 poisoned docs survive alignment (arXiv:2510.07192; 2410.13722), unlearning fails (ICLR 2025), membership-inference is unsound for audit (arXiv:2409.19798); a ZK proof binds to poisoned bytes happily (§2.3). Art. 10's "free of errors," bias, and feedback-loop requirements have **no verifiable mechanism** behind them. *[verified]*

> **VERDICT — PARTIALLY TRUE, FAILS AT THE LOAD-BEARING JOINT.** The obligations are satisfiable as *documentation* (necessary, real, shipping) and unsatisfiable as *verification* (the thing audit and model-risk actually require). The steelman is right that exact-data-reproduction is hard and right that catalog metadata is a reasonable *recording* layer — but wrong that recording is sufficient, because it smuggles the hard, unsolved data-semantics problem in to excuse the easy, unsolved **tamper-evidence + independent-verifiability** problem. The correct response to "you can't hash the data perfectly" is a *stronger* construction — **pre-commit a dataset manifest (Merkle over shards) to an external transparency log before training; content-address the model artifact; verify without trusting the platform** — not the abandonment of verifiability. TAIBOM and Atlas treat exactly this as a solvable engineering problem; no platform has shipped it.

---

## 4 · The gap, named — and the shape of what closes it

Call it the **verifiability gap**: the distance between *provenance that is documented* (self-asserted, mutable, attestor-trusting) and *provenance that is witnessed* (tamper-evident, externally anchored, attestor-skeptical, independently re-derivable). Four converging surveys put the gap at the same coordinates:

- a **witness** that re-derives an artifact's bytes and answers MATCH / DRIFT / **UNVERIFIABLE** — never *trusted* — is precisely the antidote to "trust the attestor" (§2.2) and "trust the platform's mutable audit table" (§2.4);
- the **authentication ≠ authorization** discipline is the same logical move as **identity ≠ behavior / bytes ≠ semantics** (§2.2–2.3) — a deontic/semantic bridge no quantity of identity facts entails;
- **external-anchor + content-addressed + pre-commit** is the constructive fix the steelman's own critique implies (§3 verdict).

This is not a claim that any single existing organ "solves" financial-AI provenance — the data-semantics leg (§2.3) is a genuine open research problem no one has closed. It is the narrower, defensible claim that **the *posture* the regulation is forcing institutions to buy is the witnessing/accountability posture**, and that the highest-value frontier work here is to **specify and adversarially analyze a unified protocol** — dataset-manifest commitment → ZK/optimistic training proof → content-addressed signed model → per-inference witnessed log with model-version binding → transparency-log anchoring — mapped onto **Annex IV §2 / Art. 12 / SR-26-2 inventory** as the compliance artifact. That protocol does not yet exist in composed, adversarially-analyzed form (arXiv:2503.22573 names the missing **cross-stage linkability**); building and steelmanning it is a paper-grade contribution.

---

## 5 · Open problems worth a paper (next-run candidates)

1. **Composed verifiable-provenance protocol for Annex IV.** Specify manifest-commit → training-proof → content-addressed signing → witnessed inference log → transparency anchor; adversarially analyze against the signing-party threat and the 250-doc poison; map field-by-field to Annex IV §2 + Art. 12 + SR-26-2. *(closes the cross-stage-linkability gap, arXiv:2503.22573)*
2. **Tamper-evident lineage overlay for Unity Catalog/MLflow** — external Rekor-style anchoring of lineage + audit rows so a mutable catalog becomes append-only-verifiable without re-platforming. *(directly attacks §2.4 Gaps 1–3)*
3. **Dataset-semantics attestation** — can any computable predicate ("no near-duplicate of a known poison set," distributional bounds) be made a ZK constraint? *(the §2.3 open theory problem; high risk, high reward)*
4. **DORA-RoI ↔ EU-AI-Act-Annex-IV reconciliation schema** — the un-bridged dual-documentation surface; a crosswalk + tooling spec is immediately useful to every EU bank.
5. **Quant/q-fin rotation** — steelman "deep models reliably beat classical methods out-of-sample in [credit / limit-order-book / volatility]"; the data-snooping and regime-shift critique. *(next financial-ML rotation)*

---

## 6 · Consolidated verified source ledger (selected; ~all retrieved & confirmed)

| # | Source | ID / URL | Date | Maturity |
|---|---|---|---|---|
| 1 | Sentry: Authenticating ML Artifacts on the Fly | arXiv:2510.00554 | Oct 2025 | preprint |
| 2 | AIBoMGen: AI Bill of Materials for Compliant Training | arXiv:2601.05703 | Jan 2026 | preprint |
| 3 | The Grand Software Supply Chain of AI Systems (Cesarano & Monperrus) | arXiv:2604.27781 | Apr 2026 | preprint |
| 4 | Atlas: ML Lifecycle Provenance & Transparency | arXiv:2502.19567 | Feb 2025 | preprint |
| 5 | Cryptographic Verifiability of End-to-End AI Pipelines | arXiv:2503.22573 | Mar 2025 | preprint |
| 6 | Human-Certified Module Repositories for the AI Age | arXiv:2603.02512 | Mar 2026 | preprint |
| 7 | SLSA v1.2 spec | slsa.dev/spec/v1.2/ | current | standard/deployed |
| 8 | in-toto / ITE-6 (DSSE) | github.com/in-toto/ITE | active | standard/deployed |
| 9 | OpenSSF Model Signing (OMS) spec + intro | github.com/ossf/model-signing-spec; openssf.org blog 25 Jun 2025 | 2025 | standard/deployed |
| 10 | Sigstore model-transparency v1.1.1 | github.com/sigstore/model-transparency; blog.sigstore.dev/model-transparency-v1.0 | Oct 2025 | standard/deployed |
| 11 | NVIDIA NGC OMS production signing | developer.nvidia.com/blog (bringing-verifiable-trust…) | 2025 | vendor-claim |
| 12 | Datasheets for Datasets | doi:10.1145/3458723 | 2021 | peer-reviewed |
| 13 | Data Authenticity, Consent & Provenance for AI are all broken | arXiv:2404.12691 (ICML 2024) | Apr 2024 | peer-reviewed |
| 14 | 2024 Foundation Model Transparency Index | arXiv:2407.12929 (TMLR 2025) | Jul 2024 | peer-reviewed |
| 15 | Membership Inference Cannot Prove Training-Set Membership | arXiv:2409.19798 (SaTML 2025) | Sep 2024 | peer-reviewed |
| 16 | Proving membership via data watermarks | arXiv:2402.10892 (ACL 2024) | Feb 2024 | peer-reviewed |
| 17 | STAMP: dataset membership via watermarked rephrasings | arXiv:2504.13416 (ICML 2025) | Apr 2025 | peer-reviewed |
| 18 | Proof-of-Learning (orig.) | arXiv:2103.05633 (S&P 2022) | 2021 | peer-reviewed |
| 19 | "Adversarial Examples" break Proof-of-Learning | arXiv:2108.09454 (S&P 2022) | 2021 | peer-reviewed |
| 20 | Kaizen: Zero-Knowledge Proof of Training for DNNs | IACR 2024/162 (CCS 2024) | 2024 | peer-reviewed |
| 21 | VeriLoRA: verifiable LoRA fine-tuning via ZKP | arXiv:2508.21393 (NDSS 2026) | Aug 2025 | peer-reviewed |
| 22 | Verifiable Fine-Tuning bound to data provenance | arXiv:2510.16830 | Oct 2025 | preprint |
| 23 | Zero-Knowledge Verification for Frontier AI Training is Possible | arXiv:2606.05433 | Jun 2026 | preprint |
| 24 | ZKP-Based Verifiable ML — survey | arXiv:2502.18535 | Feb 2025 | peer-reviewed |
| 25 | Persistent Pre-Training Poisoning of LLMs | arXiv:2410.13722 (ICLR 2025) | Oct 2024 | peer-reviewed |
| 26 | Poisoning LLMs needs ~constant #samples (~250 docs) | arXiv:2510.07192 | Oct 2025 | preprint |
| 27 | Sleeper Agents | arXiv:2401.05566 | Jan 2024 | preprint |
| 28 | Machine Unlearning Fails to Remove Data Poisoning | ICLR 2025 (iclr.cc/…/30218) | 2025 | peer-reviewed |
| 29 | TransTroj: model-supply-chain poisoning | arXiv:2401.15883 (WWW 2025) | 2024 | peer-reviewed |
| 30 | TAIBOM: trustworthiness for AI-enabled systems | arXiv:2510.02169 | Oct 2025 | preprint |
| 31 | Building an Open AIBOM Standard (SPDX ext.) | arXiv:2510.07070 | Feb 2026 | preprint |
| 32 | GPU-Based Integrity Verification (TOCTOU on 100GB models) | arXiv:2510.23938 | Oct 2025 | preprint |
| 33 | CycloneDX ML-BOM + v1.6/CDXA | cyclonedx.org/capabilities/mlbom; /news/cyclonedx-v1.6-released | 2024–25 | standard |
| 34 | SPDX 3.0.1 AI profile | spdx.github.io/spdx-spec/v3.0.1/model/AI/AI | current | standard |
| 35 | C2PA v2.2/2.3 AI/ML guidance | spec.c2pa.org/…/2.3/ai-ml | May/Dec 2025 | standard/deployed |
| 36 | EU AI Act Art. 10 / 11 / 12 / Annex IV | artificialintelligenceact.eu/article/{10,11,12}; /annex/4 | 2024, verified Jun 2026 | law-in-force |
| 37 | GPAI Training-Content Summary Template | ec.europa.eu; securiti.ai analysis | 24 Jul 2025 | law-in-force |
| 38 | Digital Omnibus (high-risk deferral) | gibsondunn.com analysis | 7 May 2026 | provisional |
| 39 | US SR 26-2 Model Risk Management | federalreserve.gov/…/SR2602.htm; Sia/Lumenova analyses | 17 Apr 2026 | guidance-in-force |
| 40 | DORA Art. 28 / 30 (Register of Information) | digital-operational-resilience-act.com; securiti.ai | in force 17 Jan 2025 | law-in-force |
| 41 | ECB Revised Guide to Internal Models (ML chapter) | bankingsupervision.europa.eu press 28 Jul 2025; Finalyse analysis | Jul 2025 | guidance |
| 42 | Machine Identity Governance Taxonomy (MIGT) | arXiv:2604.06148 | Apr 2026 | preprint |
| 43 | yProv4ML (W3C PROV provenance for ML) | arXiv:2507.01075 | Jul 2025 | preprint |
| 44 | Optimistic Verifiable Training (HW nondeterminism) | arXiv:2403.09603 | 2024 | preprint |
| 45 | CSA Research Note — EU AI Act high-risk readiness | labs.cloudsecurityalliance.org | 2025–26 | advisory |

*(Full per-agent ledgers with one-line findings retained in run notes; this is the deduplicated cross-cut.)*

---

## 7 · Honest limits of this run

- **Recency risk.** Several of the freshest preprints (arXiv:2604.27781, 2606.05433, 2603.02512, 2601.05703) are weeks-to-months old and **not peer-reviewed**; labeled `[preprint]` and load-bearing claims are attributed, not asserted as settled. Two arXiv IDs in the June-2026 band were confirmed to exist/match by retrieval but the field's churn is real.
- **Unrendered primaries.** The *International AI Safety Report 2026* (arXiv:2602.21012) PDF (6.4 MB) and the SR 26-2 attachment PDF did not render via fetch; SR 26-2 is cited from the official `.htm` landing page + two advisory analyses that quote it directly, and the Safety Report's financial-sector specifics are **explicitly not cited**.
- **Provisional law.** The Digital Omnibus deferral is an agreement, **not yet in the Official Journal**; treated as provisional throughout.
- **Vendor claims.** Platform capabilities are from primary vendor docs and labeled `[vendor-claim]`; "what it does *not* do" is inferred from the *absence* of documented signing/anchoring, which is strong but not a vendor admission.
- **No independent benchmarking.** This run synthesizes the literature; it does not re-run any experiment. Performance figures (e.g., Kaizen 15 min/iter) are as-reported.
- **Spot-verification performed.** The two most load-bearing future-dated preprints were independently re-fetched: **arXiv:2606.05433** (Peigné, Nguyen, Wang; 3 Jun 2026; zkVM frontier-training verification) — *fully confirmed* (title/authors/date/content). **arXiv:2604.27781** (Cesarano & Monperrus; 30 Apr 2026; *The Grand Software Supply Chain of AI Systems*) — *existence, authorship, date, and the four-gaps thesis confirmed via abstract*, but the source-gathering pass's verbatim quotes from its body could not be confirmed and were downgraded to attributed paraphrase (§2.2, §3). The remaining sources rest on the gathering agents' fetch-verification, not a second independent pass.

---

## 8 · Deepen next

- **Next rotation:** quant/algorithmic ML (q-fin) steelman (candidate #5 above) **or** COBOL/legacy-modernization provenance (mainframe→cloud lineage for core banking) to broaden sector coverage.
- **Carry-forward thread:** draft candidate #1 (the composed verifiable-provenance protocol for Annex IV) as the first *original whitepaper* artifact — it is the highest-leverage, demand-backed, paper-grade contribution and sits squarely on proven strength.
- **Watch:** OCC GenAI/agentic RFI (SR-26-2 successor scope); CEN/CENELEC harmonized-standard drafts (they define what "Annex IV compliant" means); OpenSSF OMS annotations roadmap (training-data fields are *planned*).

---

*Run 001 of* The Witnessing Spine *corpus. Claim↔evidence↔verdict; sources verified; maturity labeled; limits stated.*
