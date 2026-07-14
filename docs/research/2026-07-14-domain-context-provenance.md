# Domain dossier: context provenance

Date: 2026-07-14. Scope: what is known, measured, and still open in context
compaction, content provenance, and claim-to-source binding, as it bears on a
verified-inference platform. Every claim carries its source URL and the
source's own date. Numbers carry confidence labels. Nulls are content, not
apologies.

## 1. The frontier in five sentences

Context management and content provenance are converging on the same
question: when an agent's working context is transformed (folded, compacted,
summarized, transferred), what survives, and can anyone check? Compaction now
has a measured cost: constraint violations rise from 0% to 30% on average
after compaction, up to 59% for some models (arXiv:2606.22528, v2 2026-06-27),
while folding agents match full-context baselines at one tenth the active
context (arXiv:2510.11967, 2025-10-13). Provenance standards reached
unstructured text and source code this cycle (C2PA 2.4, April 2026; SLSA v1.2
Source Track, 2025-11-24), but they attest claims about origin, not the truth
of content. Claim-to-source binding exists at character-offset granularity
(Anthropic Citations, launched 2025-01-24) and cryptographic receipts for
agent memory and actions exist as single-paper prototypes (Portable Agent
Memory, Sello), with no cross-vendor convergence. The open slot, held by
nobody found: compaction with byte-exact recall, plus receipts that bind each
generated claim to a hashed source span.

## 2. Confirmed findings

Eight findings survived adversarial checking against their primary sources.

### F1. Folding beats summarization at one tenth the context

**Claim:** Context-Folding agents trained with FoldGRPO match or outperform
ReAct baselines on Deep Research and SWE tasks with a 10x smaller active
context (high, from the abstract), and outperform summarization-based context
management.
**Source:** https://arxiv.org/abs/2510.11967, submitted 2025-10-13.
**Why it matters:** long-horizon work does not require full context, so the
platform can budget context aggressively without a measured task-performance
cost, provided the folded material stays recallable. Folds are outcome
summaries, so recallability is not free (see null N1).
**Pour-back:** target `BATTLE-MAP.md` context-management lane. Shape: a fold
operation in the harness loop that replaces a sub-trajectory with an outcome
summary plus a content hash of the raw folded turns.

### F2. Compaction is a governance hazard with a cheap, training-free fix

**Claim:** across 1,323 episodes (high), compaction raised constraint
violations from 0% to 30% on average, peaking at 59% for DeepSeek-V4 and
Kimi-K2.5 (high, the paper's own numbers); training-free constraint pinning
restored 0% violations across all seven models at under 0.5% token overhead
(high).
**Source:** https://arxiv.org/abs/2606.22528, v2 revised 2026-06-27.
**Why it matters:** a platform that compacts context without pinning its
standing constraints ships a measured defect, and the fix costs almost
nothing. This is the single most directly actionable number in the domain.
**Pour-back:** target `harness/policy.py` and the session compaction path.
Shape: a pinned-constraint region that survives every compaction verbatim,
with a regression test asserting byte-exact survival.

### F3. SLSA v1.1 gives verifier attestations a standard vocabulary

**Claim:** SLSA v1.1 was approved 2025-04-21, adding a verification procedure
and verifier metadata to the Verification Summary Attestation (VSA) format,
backwards compatible with v1.0.
**Source:** https://slsa.dev/blog/2025/04/slsa-v1.1, dated 2025-04-21.
**Why it matters:** the VSA is the industry pattern for "a named verifier
checked artifact X against policy Y on date Z", which is the same shape a
verified-inference receipt needs. Adopting VSA vocabulary buys interop that a
private schema does not.
**Pour-back:** target `harness/envelope.py` (`ProofEnvelope`). Shape: optional
VSA-style verifier metadata fields (verifier id, policy id, verification
date), additive and backwards compatible.

### F4. SLSA v1.2 covers source; environment and dependencies remain open

**Claim:** SLSA v1.2 was published 2025-11-24, adding the Source Track
(threats in authoring, review, and management of source code); the Build
Environment and Dependency tracks are still in development.
**Source:** https://slsa.dev/blog/2025/11/announce-slsa-v1.2, dated
2025-11-24.
**Why it matters:** source provenance is now a checkable level the platform
can record for anything it ingests, and the unreleased tracks bound what any
end-to-end attestation chain can honestly claim today (see null N5).
**Pour-back:** target the intake path (`harness/intake.py`) and receipt
schema. Shape: record the SLSA track and level of any external artifact
ingested, with "unknown" as a first-class value.

### F5. C2PA 2.4 reaches plain text, with a fail-closed hard binding

**Claim:** C2PA Specification 2.4 (April 2026) defines embedding manifests in
unstructured text via Unicode Variation Selectors (Section A.8) and mandates
a data-hash assertion as the hard binding for such text assets (Section
9.2.4).
**Source:**
https://spec.c2pa.org/specifications/specifications/2.4/specs/C2PA_Specification.html,
published April 2026. Sections confirmed by direct fetch 2026-07-14.
**Why it matters:** this is a standardized way to make a receipt travel
inside generated text, and the data-hash binding fails closed on any edit.
The strippability and brittleness caveats are real (see null N2), so it is an
export format, not a trust anchor.
**Pour-back:** target the receipt export path. Shape: an exporter that emits
a C2PA-style data-hash assertion over generated text alongside the native
receipt, round-trip tested.

### F6. Character offsets make citations mechanically checkable

**Claim:** Anthropic Citations chunks documents into sentences or
user-supplied chunks and returns citation blocks with character-level offsets
(`char_location` with `start_char_index` and `end_char_index` for plain text;
custom-content chunks cite by block index via `content_block_location`).
Vendor claims up to 15% higher recall accuracy (low: no published methodology
or intervals, see null N4); the customer Endex reported source hallucinations
dropping from 10% to 0% (low: single customer anecdote).
**Sources:** https://claude.com/blog/introducing-citations-api, page dated
2025-06-23; https://platform.claude.com/docs/en/docs/build-with-claude/citations,
fetched 2026-07-14; launch date 2025-01-24 per
https://simonwillison.net/2025/Jan/24/anthropics-new-citations-api/, dated
2025-01-24.
**Why it matters:** a character offset into a hashed source snapshot is a
claim the harness can check mechanically: re-slice the snapshot, compare the
bytes, emit a verdict. That is the same oracle shape the platform already
runs for code.
**Pour-back:** target `harness/envelope.py` plus `harness/witness.py`. Shape:
optional citation fields `{source_hash, start_char, end_char, quote_hash}`
and a verifier that re-slices the snapshot and compares.

### F7. Memory with its own provenance DAG has a working prototype

**Claim:** Portable Agent Memory (arXiv:2605.11032, submitted 2026-05-10)
specifies a five-component memory model, Merkle-DAG provenance over BLAKE3
and Ed25519, capability-based selective disclosure, injection-resistant
rehydration, a cross-model transfer demonstration, and a Python SDK with 54
passing tests (high, the paper's own count).
**Source:** https://arxiv.org/abs/2605.11032, submitted 2026-05-10.
**Why it matters:** provenance-carrying memory is the complement to
compaction: a rehydrated context that can prove its lineage closes the gap F2
measures. It is a single-paper design with no reported production adoption
(see null N3), so it marks the shape without settling the standard.
**Pour-back:** target the memory substrate (mneme integration). Shape:
content-addressed memory entries whose derivation edges are hashed, so any
rehydrated context can enumerate and verify its ancestors.

### F8. Receiver-attested receipts close the self-logging hole

**Claim:** Notarized Agents / Sello (arXiv:2606.04193, v1 June 2026) has the
receiving service sign a receipt, encrypt it to the owner via HPKE bound in a
JWS, and publish to a witness-cosigned Merkle transparency log, so agents can
neither forge nor omit action records.
**Source:** https://arxiv.org/abs/2606.04193, v1 June 2026.
**Why it matters:** self-logged trails are the weak point of any receipts
system, including this platform's own witness layer. Receiver attestation
plus a transparency log is the known fix pattern; a local append-only Merkle
log is the incremental first step that later admits external cosigners.
**Pour-back:** target `harness/witness.py` and the engine's receipts
endpoint. Shape: an append-only Merkle log over emitted `ProofEnvelope`
hashes with a recomputable root.

## 3. Honest nulls

- **N1.** No published compaction mechanism achieves both large context
  reduction and lossless verbatim recall: Context-Folding's folds are outcome
  summaries (lossy by design), and Governance Decay quantifies the cost of
  that loss (up to 59% constraint-violation rates). "Compression with
  byte-exact recall" remains an open slot, not a solved result.
- **N2.** C2PA still attests claim provenance, not content truth. The
  first-mile gap (a signed manifest proves a device or software made a claim,
  not that the content is authentic) is acknowledged across critiques, and
  the new text hard binding breaks on any single-byte edit while the embedded
  variation-selector metadata is trivially strippable.
- **N3.** No cross-vendor standard for agent-memory cryptographic receipts
  has converged. Microsoft's verifiable compliance receipts is a proposal
  page; Portable Agent Memory and Sello are single-paper prototypes with no
  reported production adoption. Flywheel would be an early implementer, not a
  late adopter.
- **N4.** Anthropic's "up to 15%" recall-accuracy uplift for Citations is a
  vendor claim without published methodology or intervals. Character offsets
  guarantee where the quote is, not that the surrounding generated claim is
  faithful to it.
- **N5.** SLSA's Build Environment and Dependency tracks remain unreleased as
  of v1.2 (November 2025), so end-to-end attestation chains covering runtime
  environment and dependencies are specification futures, not checkable
  levels.
- **N6.** C2PA adoption in production text and document pipelines is not
  demonstrated anywhere found. The adoption evidence (Adobe, OpenAI, camera
  makers, the CISA advisory of January 2025, the Library of Congress
  community of practice of July 2025) is image and video centric, and at
  least one major image generator (Midjourney, per early-2026 reporting)
  still embeds no credentials at all.

## 4. Dropped in verification

Eight findings failed adversarial checking and were dropped; their text is
not reproduced here, and the count is reported as received from the
verification pass.

## 5. Build candidates

### B1. Constraint pinning across compaction

Directly implements the F2 fix. Pour-back: `harness/policy.py` plus the
session compaction path.
**Smallest committable first slice:** add a `pinned_constraints` field to the
compaction record and one regression test that runs a compaction cycle and
asserts the pinned text survives byte-exact. Schema plus test, one commit.

### B2. Fold-with-receipt context ledger

Fills the N1 open slot at local scale: folds stay lossy in the active
context, the ledger keeps recall byte-exact. Pour-back: new
`harness/context_ledger.py`, roadmap entry in `BATTLE-MAP.md`.
**Smallest committable first slice:** a content-addressed store where
`fold(segment)` returns `{summary, sha256, byte_len}` and `unfold(sha256)`
returns the exact bytes, with a round-trip test.

### B3. Offset-bound citation verifier

Turns F6 into a checkable receipt field and answers N4's faithfulness gap
with a mechanical check. Pour-back: `harness/envelope.py` and
`harness/witness.py`.
**Smallest committable first slice:** extend `ProofEnvelope` with optional
`citations: [{source_hash, start_char, end_char, quote_hash}]` and a verifier
that re-slices a provided snapshot and returns verified or drift, one test
for each verdict.

### B4. Receipt transparency log

First step on the F8 pattern; local now, external cosigners later.
Pour-back: `harness/witness.py` and the engine's receipts endpoint.
**Smallest committable first slice:** an append-only Merkle log module that
chains envelope hashes and recomputes the root, tested over a fixture set of
envelopes.
