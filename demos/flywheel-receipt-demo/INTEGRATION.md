# Flywheel + NEAR AI: native integration

## The two layers
- NEAR AI attests the run. A confidential-inference call executes in a TEE (Intel
  TDX, NVIDIA Confidential Computing, via the Phala Private-ML-SDK) and emits an
  attestation quote over the model image, the code path, and the request, verifiable
  through Intel and NVIDIA attestation services. This proves what ran.
- Flywheel re-derives the answer. An accepted result emits a proof envelope that a
  third party re-runs offline to reach the same verdict, with no learned model on the
  accept path. Only an oracle, a test runner, or a data-only certificate checker
  accepts an answer. This proves the answer holds up to a skeptic's re-check.

Attestation cannot show an output is correct; a genuine enclave can still return a
confident wrong answer. Re-derivation cannot show which physical model produced the
output. Bound together they cover both.

## How Flywheel works: approach, techniques, methodology

Approach. A result counts only when an outside party can re-derive it. The code
enforces one rule: no receipt, no accept, and no learned model on the path that
accepts an answer.

Techniques.
- The accept path is stdlib-only and model-free. Only an oracle, a test runner, or a
  data-only certificate checker that never executes what it checks can accept an
  answer.
- The verdict is four-way: PASS, FAIL, UNDECIDED, UNVERIFIABLE, with attribution that
  separates a wrong answer from a broken environment.
- Every accepted answer emits a proof envelope. An independent witness re-runs the
  recorded check and recomputes the hash to return MATCH, DRIFT, or UNVERIFIABLE.
- Features are lanes that compose through JSON seams. A research-intake lane feeds a
  falsifiable-verification lane, an orchestration lane records the run, and the engine
  binds the result into a receipt a stranger reproduces.

Methodology.
- Honest nulls stay. On the shipped benchmark the verified loop shows no accuracy gain
  over single-shot, and the tool reports it.
- Every claim ships a does-not-prove line, and every number carries its denominator
  and interval.
- An adversarial false-accept corpus is the asset: effort aimed at making the verifier
  wrongly accept, so a passing receipt is hard to fake.
- Public numbers and copy are hash-tracked or gated, kept out of hand transcription.


## Integration points (native, JSON-contract seams)

1. NEAR AI as a Flywheel provider lane. Flywheel already puts about twenty endpoints
   behind one OpenAI-compatible surface. A NEAR AI confidential endpoint slots in as
   one more lane. The lane captures the TEE attestation quote alongside the
   completion, so the run's evidence travels with the result from the first hop.

2. Attestation inside the proof envelope. Flywheel's receipt schema gains an
   `attestation` field carrying the NEAR AI quote plus its verification result
   (issuer, measurement, verdict). The receipt then reads: this answer, from this
   attested run, re-derives to this verdict. Both halves live in one artifact.

3. A combined, four-state verdict. A verifier checks the attestation through
   Intel/NVIDIA services and re-derives the answer through Flywheel. The pair yields
   RUN_ATTESTED plus ANSWER_MATCHES, with attribution that separates a broken run
   (attestation fails) from a wrong answer (re-derivation drifts) from an
   unverifiable case. Failure is attributable to the right half.

4. Flywheel receipt as a NEAR AI provenance-log artifact. NEAR AI's log already
   records the attested run an agent cannot rewrite. Attaching the re-derivable
   correctness receipt to that log entry makes the log carry both what ran and whether the
   answer stood up to a re-check.

5. MCP composition for the agent market. Flywheel exposes verification over MCP.
   An agent on market.near.ai calls it as a step: run confidentially on NEAR AI,
   then bind a Flywheel receipt, and publish both. The seam is a data contract, not
   an internal call, so either side can change without breaking the other.

## What it does not claim
- Attestation proves the run. It does not prove the output is correct.
- A receipt proves a check reproduces. It does not prove the answer is true of the world.
- On the shipped benchmark the verified loop shows no accuracy gain over single-shot
  yet. The value today is the re-derivable receipt and the containment.

## Mission

Get verifiable AI to individuals safely. As models take over more of the work, the
danger is that no one can check what they produce and no one understands it.
Re-derivable verification holds where trust fails: a captured auditor or a
self-interested lab cannot fake a verdict a skeptic re-runs, so it withstands
regulatory capture and conflict of interest across any lab or nation. The aim is a
shared layer for AI-assisted work that is checkable at the seam and understood by the
person who signs their name to it.

## A concrete first step
A small proof of concept: one NEAR AI confidential completion, its attestation quote
captured by a Flywheel lane, bound into a proof envelope, and re-derived by a third
party who never touched either machine. One run, both halves, verified end to end.
That is a day or two of work and it proves the seam.
