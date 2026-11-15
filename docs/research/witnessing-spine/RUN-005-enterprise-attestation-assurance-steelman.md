# Run 005 — The Attestation Gap in Proprietary Enterprise Software

### An adversarial steelman of the claim that certifications, SLAs, and vendor accountability assure trustworthiness

**Owner:** Zain Dana Harper (independent researcher, Seattle · ORCID 0009-0001-7175-5393)
**Date:** 2026-06-20
**Stratum:** Proprietary / enterprise systems — the last uncovered rotation stratum. **This run completes the survey.**
**Form:** four-strata survey + adversarial STEELMAN (claim ↔ evidence ↔ verdict).
**Method:** 4 parallel web-grounded scholar agents (≈183 tool-calls combined) → author synthesis + independent spot-verification of the two load-bearing breach-vs-certification claims (both produced corrections, §7). ≈85 sources; every citation retrieval-checked; maturity labeled; UNVERIFIED items flagged and excluded from load-bearing use.
**Part of:** *The Witnessing Spine* corpus · CC-BY-4.0 · companion [*Conferred Existence*](https://doi.org/10.5281/zenodo.20773724).

---

## The claim under test

> **"Third-party certifications (SOC 2 / ISO 27001 / FedRAMP) and contractual SLAs adequately assure the security and reliability of proprietary enterprise software — vendor attestation is sufficient evidence of trustworthiness."**

Decomposed into four sub-claims, one per attestation instrument:

1. **Source secrecy** — closed source is more secure (no roadmap + vendor accountability).
2. **Certification** — SOC 2 / ISO 27001 / FedRAMP attest that a vendor is secure.
3. **SLA** — uptime guarantees assure reliability and hold vendors accountable.
4. **Vendor accountability** — buying from an accountable vendor covers supply-chain risk.

---

## §0 — Executive verdict

**FALSE as stated. True only in a narrow, procurement-hygiene restatement.**

Every instrument in the enterprise-trust stack — the certificate, the SLA, the accountability pledge, the vendor-supplied SBOM — is an **asserted artifact**: a claim made by (or about) the party whose integrity is in question, opined on by an auditor whose inspection perimeter stops at the build-pipeline boundary, over a past window, within a self-selected scope. None is a **witnessed property** the buyer can independently re-derive. The instruments set a floor (they impose baseline controls, create deterrence, and price some failure) — but they do not warrant the property they are sold as warranting (current, complete, continuous security/reliability). The canonical incident record instantiates every gap: certified-then-breached (Okta, Twilio, MOVEit/Progress, LastPass), the certification *scope* diverging from the breached surface (SolarWinds SOC 2 covered DPM not Orion; the BeyondTrust infrastructure breached at Treasury was outside the FedRAMP boundary), the SLA paying cents against million-dollar losses (AWS us-east-1 2017/2021), and the build pipeline — not the source — being the attack surface (SolarWinds SUNSPOT). The narrow truth: *a current attestation is credible evidence that specified controls, as described by management, were tested within a scope over a past window — and nothing more.*

---

## §1 — Open vs. closed-source security (secrecy ≠ assurance)

**Sub-claim:** *closed source is more secure — no public roadmap, single accountable vendor.*

**Steelman (real weight).** Closed binaries deny unsophisticated attackers a free source audit; a single vendor can mandate coordinated disclosure and fund a dedicated security team; "many eyes" is contingent on competent reviewers actually looking — Meneely & Williams (ACM CCS 2009) found diffuse multi-developer ownership correlated with *more* vulnerable files, complicating naive Linus's-Law optimism. [peer-reviewed]

**Key evidence.**
- **Symmetry thesis:** under ideal conditions, openness aids attack and defense equally → source secrecy is *no net security gain* — Anderson, "Security in Open versus Closed Systems" (Toulouse 2002; MIT Press chapter "Open and Closed Systems Are Equivalent"). [peer-reviewed]
- **Open design is a codified principle since 1975:** "the design should not be secret… should not depend on the ignorance of attackers" — Saltzer & Schroeder, *Proc. IEEE* 63(9), 1975; codified in **NIST SP 800-160 v1r1 (2022)** and **NIST SP 800-123** ("security should not depend on the secrecy of the implementation"). [peer-reviewed / standard]
- **No significant open-vs-closed difference** in vulnerability or patch behavior — Schryen, "Is Open Source Security a Myth?", *CACM* 54(5), 2011, DOI:10.1145/1941487.1941516. [peer-reviewed]
- **Closed source blinds defenders/auditors too** — Hoepman & Jacobs, "Increased Security Through Open Source," *CACM* 50(1), 2007. [peer-reviewed]
- **Long dwell times in BOTH models:** Log4Shell lived ~8 years in *open* Log4j (CVE-2021-44228); EternalBlue lived 5+ years stockpiled against *closed* Windows SMBv1; Heartbleed ~2.4 years in *open* OpenSSL. The disclosure model is not the controlling variable. [CVE/gov]
- Obscurity is defeated by fuzzing/reverse-engineering; **CISA Secure by Design (2023)** endorses *radical transparency* — the opposite of obscurity. [gov]

**Verdict:** **FALSE as stated.** True restatement: *closed source denies a casual roadmap and enables single-vendor disclosure control — real second-order benefits — but secrecy is not a warranted security property; it provides no net gain against capable attackers, blinds defenders symmetrically, and is rejected as a primary control by the 50-year standards consensus. Secret ≠ secure.*

---

## §2 — Certification-as-assurance (the artifact ≠ the warrant)

**Sub-claim:** *SOC 2 / ISO 27001 / FedRAMP certification proves the vendor is secure.*

**Steelman (real weight).** These are the most rigorous commercially-available assurances. SOC 2 Type II tests *operating effectiveness* over a 6–12 month window against AICPA Trust Services Criteria; ISO 27001 mandates an ISMS with annual surveillance; **FedRAMP is the strongest — mandatory monthly ConMon, annual 3PAO assessment, agency visibility into residual risk.** A current report is better evidence than none. [standard / gov]

**Key structural facts.**
- SOC 2 **Type I = design at a point in time; Type II = operating effectiveness over a *past* window**; **management selects the scope and control set**; the CPA firm opines on management's description (it is an *attestation*, not a pass/fail certification). [AICPA / standard]
- ISO 27001 certifies an ISMS against a **self-chosen scope statement + Statement of Applicability**; 3-year cycle, annual *subset* surveillance. [standard]
- FedRAMP adds **continuous monitoring** — strongest on the "continuous" axis — but is still a control-baseline (NIST SP 800-53) assessment of a defined boundary. [gov]

**Certified-then-breached (verified).**
- **Okta** — held ISO 27001 (Schellman); support-system breach Oct 2023 exposed all customer-support users. [incident]
- **Twilio** — held ISO 27001 + SOC 2 Type II; "0ktapus" SMS-phishing breach Aug 2022 (part of a 130+ org campaign). [incident]
- **MOVEit / Progress** — held ISO 27001 + SOC 2; CVE-2023-34362 zero-day SQLi → Cl0p, ~2,700 orgs / ~93M individuals. [incident]
- **LastPass** — held SOC 2 Type II (ISO 27001 timing UNVERIFIED, §8); 2022 breach → **ICO £1.2M fine** (UK GDPR Art. 5(1)(f)/32(1)). [primary-legal]
- **Scope-divergence cases (the sharpest):** **SolarWinds** held SOC 2 Type II for **DPM** — a *different product* from the breached **Orion** (that Orion was formally out-of-scope is a reasonable inference, not a public fact — the report scope isn't published; §7). **BeyondTrust** held **FedRAMP Moderate** for Remote Support/PRA (Apr 2024); the infrastructure breached at Treasury (Dec 2024) was **outside the FedRAMP boundary** — "no FedRAMP instances were affected" per BeyondTrust (§7). [incident / gov]

**Authoritative critique.**
- "Being compliant is not necessarily the same as being secure… compliance might not replace an effective cybersecurity program" — Marotta & Madnick, MIT CISL WP 2020-06 (SSRN 3542563). [peer-reviewed wp]
- Control *effectiveness* is driven by *how* a control is implemented, not whether it's checked — Woods & Seymour, *J. Cyber Policy* 8(3), 2024. [peer-reviewed]
- **GAO-23-106428:** only 8 of 23 CFO-Act agencies rated "effective" despite operating under FISMA compliance. [gov]

**Verdict:** **FALSE as stated.** True restatement: *a current certification is credible evidence that an auditor verified specified, management-described controls operated within a defined scope over a past window. It is not evidence of present, complete, or continuous security. Four structural gaps — self-selected scope, backward-looking window, build-pipeline/zero-day vectors outside the tested control set, and implementation-quality variance — are each instantiated in verified breaches. Attestation ≠ assurance.*

---

## §3 — SLA-as-reliability (the threshold ≠ the outcome)

**Sub-claim:** *uptime SLAs guarantee reliability and hold vendors accountable.*

**Steelman (real weight).** SLAs are enforceable contract terms with escalating credits (10% → 25/30% → 100%); the architecture they reward (multi-AZ/region) genuinely drives redundancy investment; professional cloud beats most self-run infra (Uptime Institute). [vendor-SLA / gray-lit]

**Key evidence.**
- **The remedy is a capped, non-cash service credit, customer must claim it, and it is the "sole and exclusive remedy"** — consequential/business damages contractually excluded. AWS S3 SLA verbatim: credits are "your sole and exclusive remedy"; "will not entitle you to any refund." [vendor-SLA]
- **AWS us-east-1 outages:** Feb 28 2017 (4h17m, operator fat-finger collapsed S3 index) and Dec 7 2021 (~7h, control-plane congestion). A 7h outage = ~99.06% monthly uptime — often *below* the credit trigger threshold yet yielding pennies. [incident-RCA]
- **Credit-vs-loss asymmetry:** Uptime Institute — median significant-outage cost ≈ **$973,000** (Rogers, 2022); a 100% credit on a $3/mo instance ≈ $0.30. 54% of 2023 outages cost >$100k; 16% >$1M. [gray-lit]
- **The SLA number is a *credit-activation threshold*, not a witnessed availability** — and the provider self-classifies "unavailable" vs "degraded" (AWS classed Dec 2021 as degradation). [vendor-SLA / legal]
- **An availability SLA cannot address data destruction:** GCP/UniSuper (May 2024) — an entire Private Cloud deleted by an operator blank-field error; uptime math is irrelevant when the object no longer exists. [incident-RCA]

**Verdict:** **FALSE as stated.** True restatement: *an SLA prices a bounded slice of failure; it neither prevents failure nor compensates business loss. The promised "nines" are a credit threshold, not a witnessed outcome; the remedy is a capped non-cash credit, customer-claimed, provider-classified, and the sole remedy. Contractual promise ≠ realized reliability.*

---

## §4 — Transitive supply-chain trust (accountability ≠ verifiability)

**Sub-claim:** *an accountable proprietary vendor covers your supply-chain risk.*

**Steelman (real weight).** Vendors carry legal/regulatory/reputational liability; EO 14028 + OMB M-22-18 require signed SSDF attestations exposing executives to liability for falsity; vendors have threat-intel/patch economies of scale buyers can't match. [gov]

**Key evidence.**
- **The build pipeline — not the source — is the attack surface:** SolarWinds **SUNSPOT** intercepted MsBuild, swapped `InventoryManager.cs` at compile time, restored it after, and MD5-checked to avoid build breakage. **The source repo stayed clean; a buyer auditing source would find nothing.** ~18,000 customers got trojanized Orion; ~9 months undetected. [incident — CrowdStrike SUNSPOT analysis]
- **You can't inventory what you can't see:** Log4Shell (CVE-2021-44228, CVSS 10.0) sat 3–5 layers deep as a transitive dep inside countless proprietary products; many vendors didn't know they shipped it. [CVE/gov]
- **Un-inspectability cuts both ways:** xz-utils backdoor (CVE-2024-3094) — a multi-year maintainer-trust social-engineering campaign hid the payload in *test archives*, not readable code — but was caught in days *because* the pipeline was public (anomalous sshd latency). Closed source removes even that forensic path. [CVE]
- **Double supply-chain compromise:** 3CX (Mar 2023) — a trojanized dependency (X_TRADER) compromised an accountable vendor whose signed installer then hit 600k+ customers. Accountability at each node did not extend to the binaries each node *consumed*. [incident]
- **The policy response is itself an admission accountability was insufficient** — EO 14028, NIST SSDF (SP 800-218), SBOM mandates — yet the CISA attestation form is a CEO "good-faith" declaration with no SBOM requirement and no independent verification, and **OMB rescinded M-22-18 in Jan 2026** without a stronger replacement. [gov / gray-lit]
- **The witnessing counter-architecture exists but isn't mandated:** in-toto (USENIX Security 2019), SLSA build provenance, and **reproducible builds** ("trusting code is not the same as trusting its executable counterparts" — Lamb & Zacchiroli, *IEEE Software* 2021). [peer-reviewed / gray-lit]

**Verdict:** **FALSE as stated.** True restatement: *vendor accountability transfers liability and creates deterrence, but cannot assure supply-chain security because the buyer cannot independently inventory, verify, or re-derive the vendor's build pipeline or transitive dependencies — and the canonical incidents (SUNBURST, Log4Shell, 3CX) are compromises of accountable vendors through exactly those un-inspectable surfaces. A contract about the supply chain is an assertion, not a witnessed warrant.*

---

## §5 — Where enterprise assurance actually resides (the map)

| Asserted artifact | What it claims | The witnessed property it is NOT |
|---|---|---|
| SOC 2 / ISO 27001 / FedRAMP | controls existed & operated over a past window, in scope | real-time build-pipeline integrity; present, complete, continuous security |
| SLA | credits trigger when a defined availability band is missed | witnessed availability; coverage of business loss; data-destruction events |
| Vendor accountability | the vendor is liable and incentivized | the integrity of the vendor's build env + the transitive deps it consumed |
| Vendor-supplied SBOM | a manifest of components, as stated by the vendor | an independently re-derivable inventory of the *delivered binary* |

**Synthesis.** Assurance is sought in the wrong layer. Every instrument is a *claim by, or about, the party whose integrity is in question*, with an inspection perimeter that stops at the pipeline boundary. The witnessed analogs — signed provenance the buyer re-verifies, reproducible builds the buyer re-executes, telemetry the buyer inspects — are nascent and unmandated. **An assertion about the supply chain is not the supply chain.**

---

## §6 — The FIFTH convergence — and the ring closes

Five rotations, five sectors, **one structural gap**: an artifact that is *verified / asserted / documented* mistaken for the *property it warrants*.

| Run | Sector | Verified/asserted artifact | ≠ the warrant |
|---|---|---|---|
| 001 | AI provenance | signed build lineage | **authentication ≠ authorization** |
| 002 | COBOL modernization | a translated program | **translation ≠ equivalence** |
| 003 | Quant/ML | a backtest Sharpe / APR | **backtest ≠ realized alpha** |
| 004 | DeFi | a valid state transition | **verification ≠ economic safety** |
| 005 | Enterprise software | a certificate / SLA / SBOM | **attestation ≠ assurance** |

And the survey is not five isolated points — it is a **ring**: Run 005's §4 supply-chain finding (documented ≠ *witnessed* provenance; in-toto / SLSA / reproducible builds as the fix) is **the same mechanism Run 001 identified** for financial-AI provenance. The last stratum closes the loop back to the first. The closing move is invariant across all five: **re-derive the warrant from primary evidence, account for coverage, and stamp MATCH / DRIFT / UNVERIFIABLE** rather than accept the artifact's self-report. The convergence is now strong, five-deep, and ring-closed — sufficient to promote to a standalone whitepaper (Phase B/C).

---

## §7 — Spot-verification log (independent author checks + corrections)

I independently re-checked the two load-bearing certification-vs-breach claims. **Both produced corrections** — the discipline earning its keep:

1. **BeyondTrust / Treasury (material correction).** The agent framed this as "FedRAMP ConMon failed to prevent a breach of a FedRAMP system." **Corrected:** BeyondTrust states **"no FedRAMP instances were affected"**; the compromised Remote Support infrastructure was *outside* the FedRAMP authorization boundary (the government-contracts bar's analysis is titled "Looking Beyond FedRAMP"). This is **not** a ConMon failure — it is a **scope/boundary-divergence** case (the certificate's boundary ≠ the buyer's actual exposure), which is *more* on-thesis. Reframed accordingly in §2.
2. **SolarWinds SOC 2 scope (softening).** "Orion was explicitly out of scope" is **not publicly confirmable** — the SOC 2 report scope is not published. **Corrected to the verifiable fact:** SolarWinds held SOC 2 Type II for **DPM (Database Performance Monitor)**, a different product from the breached **Orion**; Orion's exclusion is a reasonable *inference*, labeled as such in §2.

(Also carried from the agents' own honesty: the SolarWinds SEC case was *dismissed* Nov 2025 — the complaint's factual record stands but the legal outcome did not; the same verify-the-correction discipline applies here too.)

## §8 — Limits logged

- **Cert-timing UNVERIFIED (excluded from load-bearing claims):** whether LastPass held ISO 27001 *before* the Aug 2022 compromise; whether the specific Twilio/Progress systems breached were *in* their audited SOC 2 scope. The *fact of holding* each cert is verified; precise scope/timing is not, and is not relied upon.
- **SolarWinds Orion FedRAMP status** at Dec 2020: UNVERIFIED → SolarWinds is treated as a SOC 2 *scope-gap* case, not a FedRAMP case.
- **SLA loss ratios:** the "$2.1M loss / $3,200 credit" and "$9,000/min" figures are gray-lit/marketing-sourced → excluded from load-bearing use; the Uptime Institute median ($973k) and AWS credit arithmetic are the anchors.
- **NIST SP 800-123 exact quote** confirmed via consistent secondary corroboration (binary PDF unreadable by fetch) — labeled.
- **Disagreement is real and credited:** the steelman's genuine points (closed-source disclosure control; certification as a real floor; SLA-driven redundancy investment; vendor scale) are represented; the verdict targets the *strong "sufficient/assures"* claim, not the floor.

## §9 — Frontier opening

**The survey is complete (Runs 001–005).** All financial strata covered; the convergence is five-deep and ring-closed.

- The unifying abstraction is **coverage-accounted witnessed evidence** (re-derive the warrant; MATCH/DRIFT/UNVERIFIABLE), now demonstrated across regulation, legacy migration, quant diligence, on-chain economics, and enterprise procurement. The **enterprise §4 → provenance Run-001** ring is the strongest single bridge; in-toto / SLSA / reproducible builds are the shared mechanism. The most concrete instantiation is a verifiable-provenance protocol for regulated AI (Annex IV); the most novel is the abstraction itself.
- A concrete enterprise organ falls out of §5: an **"assertion vs. warrant" attestor** that, given a vendor's certificate/SLA/SBOM, separates what is *attested* from what is *witnessed* and names the un-verified surface.

---

*Run 005 of* The Witnessing Spine *corpus — survey-completing.*
