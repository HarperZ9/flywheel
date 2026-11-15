# EMET Rationale Curation -- Design

- Date: 2026-06-07
- Status: APPROVED (brainstorming) -- pending spec self-review + user review, then implementation plan
- Scope: a curated, dissertation-register documentary layer inside `emet` that presents the
  existing design as the engineering proof-of-concept of the corpus thesis, plus a
  **runnable, regeneratable** worked-example transcript. No change to the core logic of
  `membrane.py` / `organs.py` / `monitor.py` / `corpus.py`; the transcript harness only
  *invokes* EMET, never modifies it (mirrors Boundary 6, zero actuation).
- Related: SPEC.md sections 2, 3, 6, 8, 9, 11, 12; README.md; `research/CATALOG.md` (Laws
  L1–L14); `research/dissertation/MEMBRANE-ERRATA.md`; `research/dissertation/membrane-through-line.md`;
  `research/dissertation/part-IV-meaning-closure.md`; `research/conferred-existence/thesis/conferred-existence-thesis.md`;
  `emet-internal/PROPOSAL.md`

## Problem

EMET's design is philosophically load-bearing but the philosophy is undocumented. The six
boundaries (SPEC §6), the closed verdict lattice with no `TRUSTED` (§2), and "UNVERIFIABLE,
never TRUSTED" (§9) read, to an engineer, as tasteful constraints. They are not tasteful
constraints; each is forced by a specific result in the `research/` corpus. Undocumented, a
future maintainer can "relax" a boundary without seeing the relaxation changes what EMET *is*.

This is a **curation**, not one file, for a reason the repo already honors: design-for-
isolation. Each derivation should be understood, reviewed, and *refuted* independently; one
monolithic doc would be either shallow or in violation of the repo's own file-size norm. The
curation is the exhibit -- EMET shown as the worked proof of concept of no-aseity,
teleosemantic deflationism, occasionalism, and the spoken-*for*.

Second job: the curation turns the project's thesis ("trust by re-derivation, not authority")
on itself. A rationale that justified EMET's no-authority design *by appeal to the corpus's
authority* would refute itself -- the exact in-band-authority error `refuse` strips. Every
essay justifies by re-derivable argument; `research/` is further reading only.

The `map` grounding pass confirmed EMET has **no** existing philosophy/rationale doc.

## Grounding (what the sources fixed)

1. **Headline = the is/ought seam, engineered.** `membrane-through-line.md` §4 names the
   firewall/authorization channel a *literal* engineered membrane: **authentication** is the
   1|0 of the signal; **authorization** is the membrane and is *not* readable off the signal
   (whether an authentic command *ought* to cross is a fact about a will, not the data). EMET
   does the authentication-grade byte decision (`MATCH`/`DRIFT`) and refuses the authorization
   crossing -- it *locates* the is/ought seam and won't launder across it.
2. **"Teleosemantic deflationism" precise sense.** `part-IV-meaning-closure.md` *concedes the
   whole domain of semantic/functional meaning* to Millikan (proper-function content, no
   subject) and denies only existential *for*-ness. EMET runs purely in that deflated
   functional register; the `MEMBRANE-ERRATA.md` keep the claim at Pigden's *autonomy of the
   deontic*, never "this IS Hume" -- the OUGHT is authored, never derived from the signal.
3. **Occasionalism at the corrected tempo.** `membrane-through-line.md` §2 *strikes* "re-spoken
   each instant" as false to substrate (metabolic, not per-instant). EMET is the clean
   *engineered* case where per-**operation** re-conferral is literally exact: nothing cached,
   no held key, recomputed each `verify` (L11). State it at that tempo, not loosely.
4. **The operator's method is adopted.** Every mapping carries a refuter and is marked
   **load-bearing** vs **illumination/lineage**, so "membrane" never becomes a universal
   solvent. `part-IV` §10 already states the reflexive point the close mirrors: self-certifying
   "highest-scrutiny, ground-truth-from-nowhere" authority is *met* the instant no argument
   inhabits it.

## Decisions

1. **Layout:** a spine plus a tree (below). `RATIONALE.md` at top is the entry; `docs/rationale/`
   holds the essays, the transcript, INDEX, GLOSSARY, and the regeneratable harness.
2. **Register:** full dissertation-grade prose, but **self-contained** -- the Orientation primer
   and GLOSSARY make every essay readable without `research/`. Length governed by depth, not a
   cap; a section ends when it returns nothing new (L14, the authored stop). No padding.
3. **Transcript is runnable & regeneratable.** `docs/rationale/walkthrough/render.py` (stdlib
   only) runs the real EMET commands in an isolated temp sandbox against a committed crafted
   input, normalizes non-deterministic bytes (absolute paths → placeholders), and emits
   `transcript.txt`. Same EMET bytes + same input + same `corpus_version` → byte-identical
   transcript. The demo is itself re-derivable.
3b. **CI drift-guard (severable):** a CI step regenerates the transcript and diffs it against the
   committed `transcript.txt`, failing on drift -- the one component that touches `.github/`. If
   CI integration is unwanted, this is the cleanly-removable piece; the transcript still stands.
4. **Crux (confirmed):** EMET is a membrane in the literal 1|0 sense for byte-integrity
   (`MATCH`/`DRIFT`), disciplined to the **authentication** register -- it refuses to become the
   **authorization** membrane. Propagates through `01`, `05`, `06`.
5. **Self-application:** the curation claims no authority; `research/` is further reading. If an
   essay and SPEC disagree, SPEC governs and the essay is wrong.
6. **No corpus content expanded into EMET** beyond what each essay argues; nothing classified.
7. **Per-essay shape:** every derivation essay develops (a) the law in the operator's vocabulary
   with provenance (the actual thinkers, as further reading); (b) the strongest objection and the
   corpus's answer; (c) the EMET element it forces; (d) a refuter; status marked. Assertion-only
   prose is a defect.

## The curation (file by file)

```
emet/
  RATIONALE.md                     spine: framing note + the one-page map + reading order + links
  docs/rationale/
    00-orientation.md              primer: the five frames, plainly, for a SPEC-only reader
    01-is-ought-seam.md            §1 headline -- facts, not authority (L8 + membrane-errata)
    02-no-aseity.md                §2 -- no TRUSTED (L1)
    03-occasionalism.md            §3 -- re-derivability (L11) + the L6 byte-hash identity
    04-spoken-for.md               §4 -- potential without intent (L2/L3)
    05-authored-root.md            §5 -- not its own root of trust (L1 reflexive)
    06-aleph.md                    §6 -- the boundaries as the smallest edge (emet/met/aleph)
    07-walkthrough.md              §7 -- the transcript essay (embeds transcript.txt + annotation)
    08-taxonomy.md                 §8 -- where EMET sits among literal/isomorphic/lineage membranes
    INDEX.md                       reading order + one line per essay
    GLOSSARY.md                    corpus terms defined, each with a provenance pointer
    walkthrough/
      input.txt                    crafted authority-injection target (the fixture, readable)
      render.py                    stdlib-only harness: sandbox -> run EMET -> normalize -> emit
      transcript.txt               committed expected transcript (regenerated by render.py)
```

### RATIONALE.md (spine)
Framing note (derivation, not warrant; `research/` = further reading; Boundary-1 self-applied)
+ the one-page **Rationale Map** (the eight-row table) + a reading order linking each essay.
Top-level, README-linked. The map row → essay coverage:

| EMET element | Law | Essay | Status |
|---|---|---|---|
| Closed lattice; no `TRUSTED` (§2) | L1 No-Aseity | 02 | load-bearing |
| `verify` MATCH/DRIFT; `refuse` strips in-band (§6.1) | L8 + membrane-errata | 01 | load-bearing |
| Re-derivability; recomputed each `verify` (§8) | L11 Process>Property | 03 | load-bearing |
| SHA-256 over exact raw bytes (§3) | L6 Intrinsic Substitution | 03 | load-bearing |
| Zero actuation; undecided "for" (§6.6) | L2 + L3 | 04 | load-bearing |
| Not its own root of trust (§11) | L1 reflexive | 05 | load-bearing |
| Advisory; attests, never adjudicates (§6.2,§6.4) | L8 + autonomy of the deontic | 01 | load-bearing |
| The six boundaries as a set | emet/met/aleph | 06 | literal (byte seam) / illumination (figure) |

### The eight essays (each: law + provenance → objection → answer → EMET element → refuter → status)
- **01 is/ought seam** *(headline)*. Authentication 1|0 vs authorization membrane; `refuse` =
  refusing to launder *is*→*ought*; teleosemantic-deflationist register; also covers
  advisory/attests (same deontic point). **Objection:** object-capability -- "possessing the
  token IS authorization." **Answer:** a capability is a *materialized grant*; the seam relocates
  to issuance, it does not vanish (MEMBRANE-ERRATA §5). **Provenance:** Hume, Pigden, Searle,
  ABLP, Millikan. **Refuter:** a `MATCH` entailing a permission with no authored policy.
- **02 no-aseity → no `TRUSTED`.** No *svabhāva* of trust; closed lattice. **Objection:**
  collapses to "everything UNVERIFIABLE." **Answer:** no-*aseity* is conferral-dependence, not
  hard nihilism; `MATCH` is real and conferred. **Provenance:** Nāgārjuna, Westerhoff, Aquinas
  (*esse ab alio*). **Refuter:** any codepath emitting authority.
- **03 process over property → re-derivability** (+ L6). Per-operation re-conferral; content-
  addressing makes it exact. **Objection:** the substrate-tempo correction. **Answer:** concede
  biological tempo; EMET is the clean per-operation engineered case. **Provenance:** al-Ghazālī;
  content-addressing/Merkle. **Refuter:** any normalization before hashing.
- **04 the spoken-*for* → potential without intent.** The seed is direction-neutral; the operator
  authors the *for*. **Objection:** Sartrean arbitrariness. **Answer:** conferral is re-speaking
  from a thrown, answerable position, not minting; EMET authors no *for* at all. **Provenance:**
  L2/L3, Wolf, Metz, *kun*. **Refuter:** any command that takes a model-safety decision as input.
- **05 residual aseity → not its own root of trust.** **Objection:** selftest as self-root.
  **Answer:** a compromised substrate re-derives a compromised self-hash; the authored root can't
  be a signal it authenticated -- external verifier of record. **Provenance:** L1 reflexive; the
  authored-root regress (through-line §4); L10. **Refuter:** authentication-all-the-way-down.
- **06 emet/met/aleph → the boundaries as the smallest edge.** **Literal** for the byte seam,
  **illumination** for the figure (marked). Edgeless ⇒ *met*. **Objection:** "membrane is a
  metaphor doing no work." **Answer:** the firewall case is literal; the figure is lineage.
- **07 walkthrough** -- the transcript essay. Embeds `transcript.txt` and annotates each step
  philosophically: `refuse` strips the in-band claim; the lattice *cannot* emit the `TRUSTED` the
  injection begs; `verify`/`corroborate` re-derive on bytes alone. Concrete proof the philosophy
  is operative -- EMET as the antidote to its own operating context. Worked example, never authority.
- **08 taxonomy** -- neuron/firewall *literal*, meaning/agency *isomorphic*, aleph/theology
  *lineage* (through-line §4–6); EMET placed as a literal engineered membrane in the
  authentication register. States exactly how much is claimed vs illustrated.

### INDEX.md / GLOSSARY.md
INDEX: the reading order (00→08) with one line each, and the map-row→essay table. GLOSSARY:
no-aseity, *svabhāva*, aseity / *esse ab alio*, occasionalism, the spoken-*for* (L2),
direction-neutral generativity (L3), intrinsic substitution (L6), process-over-property (L11),
the authored stop (L14), teleosemantic deflationism, proper function, autonomy of the deontic,
materialized grant, conferred existence, residual structural aseity, aleph / *emet* / *met*,
literal / isomorphic / lineage -- each one definition plus a provenance pointer.

### walkthrough/ (the regeneratable transcript)
`input.txt`: a crafted target mixing benign lines with the in-band markers EMET's denylist
targets (e.g. `GROUND_TRUTH_CANONICAL`, `HIGHEST_SCRUTINY`, `authority-pill`,
`canonical_recipients` -- public signatures already in `conformance/markers.corpus`; no secrets).
`render.py` (stdlib only, ≤ ~120 lines, helpers ≤ 50): make a temp sandbox so `anchors.json` /
`membrane_log.jsonl` never touch the repo; copy `membrane.py`+corpus in; run `selftest`, `anchor`,
`verify`, `refuse`, `corroborate`, `audit`; capture stdout + exit code; normalize sandbox paths and
any volatile field to stable placeholders; write `transcript.txt`. `transcript.txt`: committed
expected output. Determinism is the contract -- re-running `render.py` must reproduce it byte-for-byte.

## README integration
Add `RATIONALE.md` to the README "Docs" line (between SPEC.md and THREAT-MODEL.md), one clause
of framing ("why EMET is shaped the way it is, derived from first principles"). No other change.

## Fidelity constraints (MUST)
- Mark every mapping **load-bearing** vs **illumination/lineage**; never let "membrane" absorb the
  normative relation without a remainder shown (through-line §6).
- **Per-operation** tempo for occasionalism, never "each instant."
- `research/` cited as further reading only; never as authority-of-record. Richness is *argument*
  -- provenance, objection, answer, refuter -- not borrowed erudition or citation weight.
- Confidence-label any claim paraphrasing a contested corpus position.
- Each essay stands and is refutable alone (isolation); GLOSSARY + Orientation keep terms self-
  contained for a reader who never opens `research/`.
- The transcript is normalized for determinism and regenerates byte-identically; the harness
  modifies nothing in-repo except `transcript.txt`, reproduces no secret, and only invokes EMET.
- The close applies the thesis to the curation itself: its standing is conferred, not aseitic.

## Success criteria
1. INDEX's reading order walks 00→08 coherently; a SPEC-only reader follows every essay.
2. Each derivation essay carries provenance + the strongest objection + the corpus's answer + a
   refuter + a marked status -- not bare assertion.
3. No essay's justification reduces to "the corpus says so."
4. The crux (authentication-register membrane, refusing authorization) is stated once and is
   consistent across `01`/`05`/`06`.
5. All eight map rows are derived (02, 01, 03×2, 04, 05, 01, 06).
6. `render.py` regenerates `transcript.txt` byte-for-byte; `07` embeds it; the harness leaves the
   repo otherwise untouched and runs in a sandbox.
7. GLOSSARY defines every corpus term the essays use; RATIONALE.md is README-linked.
8. The close applies the thesis to the curation itself.

## Out of scope
- The executable `emet`→`met` self-deactivation seam (the other brainstorming branch; not chosen).
- Any change to the byte-hash core logic or to `conformance/vectors.json` (the walkthrough is a
  demo, not a new conformance vector -- promoting it to one is future work).
- Borrowed erudition or corpus authority standing in for argument.
- Importing classified or unrelated corpus material.
