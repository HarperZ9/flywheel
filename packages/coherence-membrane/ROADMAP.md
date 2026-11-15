# Roadmap

Where coherence-membrane (and the read-gate's place in the wider accountability
estate) goes next. This is a **plan**, not a promise: items are sequenced by
value and by what can be honestly built *and verified* from a Windows-only
workstation. Anything that needs hardware or platforms the author cannot validate
is flagged `[unvalidatable-here]` and will ship implemented-to-API, never claimed
green.

Status today: increments 1--10 shipped (perception + native capture + continuity +
consequence-scope + living loop + raw fast path + audio + structured-data +
3-rung baseline + the agent loop + region perception + signed receipts +
conformance/wire-spec + a JS reference core + temporal EventTrace + multimodal
CompositeObservation + ascii-view + caption). 278 tests; every organ self-proves;
re-derivability is
demonstrated (Python + JS agree on the corpus).

> The README's *Roadmap* section is the authoritative shipped sequence (by ship
> order). The per-item "shipped" markers below are thematic, grouped by track --
> not a second numbering scheme.

---

## North stars

1. **One grounding, two payoffs.** The same witnessed, re-derivable perception
   that stops a model acting on a hallucination (*safety*) is what lets it close
   make → look → compare → adjust (*capability*). Every item should serve at
   least one; the best serve both.
2. **Re-derivable by someone else.** A witness only one implementation can produce
   is a claim, not a proof. The read-gate becomes trustworthy when an independent
   implementation re-derives the same digests from the same bytes.
3. **Accountable autonomy substrate.** Read-gate + write-gate joined by a
   tamper-evident, externally-anchored provenance chain -- so "what was perceived,
   in what order, authorising what action" is auditable end to end.
4. **Honest by construction.** Discipline stays encoded, not asserted: stdlib-only
   trust path, inert witness, fail-closed, advisory-not-authority,
   selftest-or-net-negative, and no green that can't be reproduced.

---

## The three gaps this roadmap is built to close

From an estate survey (the read-gate, the write-gate `proof-surface`, and the
accountability-adjacent repos):

- **The read→write seam is lossy.** Everything the membrane witnesses --
  perceptual distances, dimensions, canonical hashes, multi-organ observations --
  collapses to a single `witness_verdict` enum (plus an optional digest pair) when
  it crosses into the gate. The gate can't reason over the evidence the membrane
  produces. *Widen the channel without widening authority.*
- **Re-derivability is asserted, not demonstrated.** Only one implementation
  exists. *Prove it with conformance vectors and a second-language core.*
- **The family is aligned but disconnected.** Most accountability-adjacent repos
  share the doctrine (sensors → observations → receipts → human gates) but emit no
  shared packet and define duplicate `Observation`/receipt types. *Give them one
  contract to compose through.*

---

## Track A -- Perception depth (capability)

Turn "did it change?" into "*where*, *when*, and *across which senses* did it
change?" -- the grounding a real agent loop needs.

- **the agent loop.** ✅ **shipped.** `AgentLoop` / `Goal` /
  `AdjustmentProposal`: the agent makes, the membrane looks and compares to the
  intended goal (advisory iteration), and the one consequential commit routes
  through the write-gate against the *authorized* baseline (allow / deny /
  needs-human). make → look → compare → adjust, made real and auditable, with the
  goal-tolerance and the commit-integrity kept deliberately separate so nothing is
  laundered. *(both · near)*
- **region/element perception.** ✅ **shipped.** `RegionArtifactOrgan`:
  a tiled dHash grid with per-region drift (`compare_region_drift`), so the
  membrane reports *which part* of a frame changed, not just that it did. The
  selftest proves a one-tile change is isolated to that tile. *(capability · near)*
- **temporal perception.** ✅ **shipped.** `EventTrace` over the
  continuity stream: drift episodes, dwell, settle-detection -- "it changed, then
  settled at T+3" instead of a flat event list (`trace_events`). *(capability · mid)*
- **Multimodal composition.** ✅ **shipped.** `CompositeObservation` +
  `compare_composite`: frame + audio + data witnessed as one instant, drift judged
  per-modality and overall (fail-closed; a missing/duplicate/extra modality is
  UNVERIFIABLE). *(capability · mid)*
- **semantic-equivalence rung.** A 4th baseline rung using only
  *deterministic* normalizers (numeric normal form so `1 == 1.0`, Unicode NFC,
  RFC-3339 time) -- equal normalized forms are genuinely equivalent. Hard line:
  anything needing a *learned* judgment stays an advisory organ, never an
  in-lattice MATCH. *(capability · near--mid)*

---

## Track B -- The seam & accountable autonomy (safety **and** capability)

Make the read→write boundary carry evidence and history, with an external anchor.

- **Signed observation receipts.** ✅ **shipped.** `emit_receipt` →
  `WitnessReceipt.anchor()` → `verify_receipt(pinned_anchor=… / signature_verifier=…)`:
  the external anchor the keyless hashes keep pointing at, applied across the seam,
  as a closed VALID/DRIFT/UNVERIFIABLE lattice. The inert read-gate stays keyless;
  signing lives at the seam (operator-supplied verifier; a raising verifier is
  DRIFT, fail-closed). *(both · near)*
- **Causal/temporal provenance DAG.** ✅ **shipped.** `ProvenanceGraph`: a
  hash-chained, tamper-evident DAG of observations/actions/gate-decisions whose
  per-node binding chains over parents (verify() -> VALID/BROKEN/UNVERIFIABLE);
  `has_confirming_look_ancestor()` shows a consequential action has a confirming look as an ancestor.
  `caused-by` edges are attested claims, not adjudicated facts; keyless binding is
  self-consistency (external anchor for real anti-forgery). *(both · mid)*
- **Scope/delegation binding.** Bind the consequence-scope gate to a verified
  delegation chain's `effective_scope`, so *what may be acted on* is the monotonic
  intersection of granted authority, not a static set. *(both · mid)*
- **Multi-agent membrane.** Bridge observations into the write-gate's claim-ledger:
  each agent's Observation is a confidence-bearing claim, inter-agent DRIFT is a
  logged conflict that contaminates only its downstream claims. A distributed
  read-gate with no trusted coordinator. Byzantine resistance explicitly deferred
  to the signature/anchor path. *(both · mid)*

---

## Track C -- Trust & verifiability (safety)

Harden the witness against malformed input, single-point error, and silent
regression.

- **Tamper-evident baseline ledger.** Append-only baseline pins with a
  re-derivable chain-binding, so the history of "what the operator authorised" is
  itself auditable and truncation/extension is caught. *(safety · near)*
- **Multi-witness corroboration.** An organ that requires ≥2 independent read
  paths to agree before a digest is load-bearing -- defends against a single faulty
  decode/capture path. *(both · mid)*
- **hardened ingestion.** Bounded, fail-closed perception of
  *untrusted* artifacts across all organs (size/decode/recursion caps + a fuzz
  selftest). Generalises the structured-organ size-cap lesson estate-wide. *(both ·
  mid)*
- **Machine-checked lattice proofs.** ✅ **shipped.** `lattice.py` makes the
  affirmation order of the three core algebras (MATCH/DRIFT/UNVERIFIABLE and the
  VALID/…/UNVERIFIABLE receipt & VALID/BROKEN/UNVERIFIABLE graph lattices)
  explicit and proves, by exhaustive enumeration, that each is a bounded lattice;
  the binding tests prove every adjudicator is **closed** under its set, reaches
  its affirmative top only on positive evidence (**fail-closed reachability**), and
  that drift composition is exactly the lattice **meet** (**monotonic attenuation**
  -- composition never amplifies trust). The carriers are finite, so the
  enumeration is a *complete* decision procedure -- for these finite, non-temporal
  laws, exactly what the explicit-state TLA+/TLC check originally scoped here would
  compute, but run on every `pytest` rather than build-time only, so there is no
  separate spec to rot. A Lean development and proof-extracted conformance vectors
  remain a possible future hardening. *(both · mid)*

---

## Track D -- Re-derivability & adoption

Make the trust claim demonstrable and the tool credible -- without touching the
trust path.

- **conformance + wire spec.** ✅ **shipped.** A frozen,
  hash-pinned vector corpus (`conformance/vectors.json`) + a `conformance/run.py`
  harness that re-derives every case through this implementation, plus
  `Observation`/`DriftVerdict` JSON Schemas (`schemas/`). The single normative
  artifact a second implementer conforms to -- re-derivability demonstrated, not
  asserted. *(adoption · near)*
- **A second-language (JS) reference core.** ✅ **shipped.** `impl/js/membrane.js`
  + `impl/js/run.js` port the inert compute -- SHA-256, PNG-decode + dHash, the
  drift lattice, canonical-JSON, region drift, receipt anchor (Node built-ins
  only, 64-bit hashes as BigInt) -- and re-derive the same `conformance/vectors.json`
  value-for-value. Re-derivability **demonstrated**, not asserted; the Python
  suite runs the JS harness and checks agreement. Native capture deliberately not
  ported (OS-specific, unvalidatable off-Windows). *(both · mid)*
- **SPEC.md + THREAT-MODEL.md + SECURITY.md.** Promote the already-honest "what it
  does and does not defend against" prose to normative docs; centralise the
  Windows-only validation caveat once. Most of the hard thinking is done. *(adoption ·
  near)*
- **Out-of-trust-path adapters.** A CI gate (`selftest` exit code as a build gate)
  and an observation→receipt bridge, modelled on the estate's adapter pattern --
  thin shells over `python -m`, never on the import path, refusing any authority
  token they might see. *(adoption · mid)*
- **Tool self-provenance.** Version the perceptual-hash algorithm
  (`dhash-8x8-rec601-v1`) in provenance so cross-version drift is *detected, not
  silent*, and ship a selftest-derived self-hash so a receipt can name the tool
  that produced it. Keyless self-hash documented with the same honest limit as
  artifact hashes. *(both · mid)*

---

## Track E -- Estate cohesion (cross-repo)

The vision's breadth outruns its wiring; this track closes that.

- **One shared contract library.** Extract the `Observation`/`Provenance`/receipt
  shapes into a single tiny stdlib-only package the family imports, replacing
  duplicated types and the untested "wire-compatible" claim with an enforced one.
- **Wire the family to the write-gate.** Have the doctrinally-aligned-but-silent
  repos emit the shared `proof-surface` packet, so perceived/audited state
  actually flows into one ledger.
- **Bridge the latent math.** `signal-kernels` / `anomaly-kernels` (mature C++
  change-point, divergence, baseline engines) are purpose-built for the drift
  problem and sit unused. A bounded bridge would make drift verdicts far smarter --
  as *advisory* evidence, never replacing the keyless witness.

---

## Long-horizon / partly unvalidatable

- **Attested capture provenance** `[unvalidatable-here]`. Bind a witnessed frame
  to OS/hardware capture facts (backend identity, geometry, timestamps, and on
  capable platforms a TPM/Secure-Enclave quote) as an unsigned in-toto predicate
  the *operator* signs. The inert predicate layer is buildable now; the
  hardware-quote binding needs a TPM/enclave the author can't fully validate.
- **Learned-but-verified perceptual hash** `[high-risk]`. A trained robust
  fingerprint admissible *only* as a frozen pure-Python integer kernel whose
  selftest reproduces it bit-for-bit on a pinned corpus. Survives the discipline
  only if the forward pass stays stdlib; most likely lands as an advisory organ,
  never in-lattice.
- **macOS / Linux / Wayland capture validation** `[unvalidatable-here]`. The
  backends are implemented to the OS APIs; they need someone on those platforms to
  turn the labels green. This is the single biggest *capability* gap and it cannot
  be closed from a Windows-only box.

---

## Goals to aim for (how we'll know it's working)

- **Cross-implementation parity:** ≥2 independent implementations pass the same
  conformance vectors, including the float/canonical edge cases.
- **A seam that carries evidence:** the gate can reason over structured perceived
  evidence, not a single enum -- without gaining authority.
- **An auditable loop:** any consequential action can be traced back through a
  hash-chained DAG to the look that justified it.
- **Estate cohesion:** the accountability-adjacent repos emit one shared packet
  into one ledger.
- **A second validated platform:** at least one non-Windows capture backend turned
  green by someone who can run it.

---

## Considered and rejected

- *Adversarial perceptual-collision detection in the read-gate* -- rejected: the
  premise was false. The perceptual rung never returns MATCH (only DRIFT with a
  distance), so there is no "forged near-match passes as MATCH" hole to close.
  Anti-forgery belongs at the write-gate / signed anchor, preserving the two-gate
  separation.
