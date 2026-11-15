// Proof-packet -> lesson derivation. The lesson preserves the packet's own evidence surface
// (refs, never bodies; the claim; the verdict; a verifier binding) and scaffolds the learner's
// own reasoning -- it never dumps the packet's answer. Every rejection path here has a negative
// fixture: a verifier that cannot fail on a known-bad input is not a verifier.
import { test } from "node:test";
import assert from "node:assert/strict";
import { proofLesson, misconceptionFromPacket, proofLessonReceipt } from "../src/tutor/prooflesson.mjs";
import { reverifyReceipt, CHAIN_BROKEN, VERDICT_MISMATCH } from "../src/tutor/reverify.mjs";
import { matchPacket, driftPacket, unverifiablePacket, forgedVerdictPacket, hex } from "./fixtures/proof-packets.mjs";

// JSON round-trip mirrors what a consumer reads back from disk.
const roundTrip = (r) => JSON.parse(JSON.stringify(r));

// ---- lesson derivation ----

test("proofLesson: derives a lesson preserving packet_id, claim, scope, and the packet's verdict", () => {
  const l = proofLesson(matchPacket());
  assert.equal(l.kind, "proof-lesson");
  assert.equal(l.packet_id, "pkt-match-1");
  assert.equal(l.claim, matchPacket().claim);
  assert.equal(l.scope, matchPacket().scope);
  assert.equal(l.verdict, "MATCH");
});

test("proofLesson: carries source refs and hashes only, never bodies or extra source fields", () => {
  const l = proofLesson(matchPacket());
  assert.equal(l.sources.length, 2);
  for (const s of l.sources) assert.deepEqual(Object.keys(s).sort(), ["ref", "sha256"]);
  assert.equal(l.sources[0].ref, "notes/identity.md");
  assert.equal(l.sources[0].sha256, hex("a"));
  assert.ok(!JSON.stringify(l).includes("SOURCE BODIES MUST NEVER BE CARRIED"));
});

test("proofLesson: the scaffold is structured prompts, never an answer dump of the packet's reasoning", () => {
  const p = driftPacket();
  const l = proofLesson(p);
  assert.ok(Array.isArray(l.scaffold) && l.scaffold.length >= 3);
  for (const s of l.scaffold) {
    assert.equal(typeof s.step, "number");
    assert.equal(typeof s.prompt, "string");
  }
  // the packet's own decision reasoning is the thing the learner derives; it must not be dumped
  assert.ok(!JSON.stringify(l.scaffold).includes(p.decision_summary));
});

test("proofLesson: retrieval-practice questions derive from the packet's own fields, incl. falsification", () => {
  const l = proofLesson(matchPacket());
  assert.ok(Array.isArray(l.retrievalQuestions) && l.retrievalQuestions.length >= 3);
  for (const q of l.retrievalQuestions) {
    assert.equal(typeof q.question, "string");
    assert.equal(typeof q.derivedFrom, "string");
  }
  assert.ok(l.retrievalQuestions.some((q) => /falsif/i.test(q.question)));
  assert.ok(l.retrievalQuestions.some((q) => q.derivedFrom === "sources"));
});

test("proofLesson: the verifier binding carries the packet verdict, packet_id, and source hashes", () => {
  const l = proofLesson(driftPacket());
  assert.deepEqual(l.verifierBinding, {
    packet_id: "pkt-drift-1",
    verdict: "DRIFT",
    sourceHashes: [hex("a"), hex("b")],
  });
});

test("proofLesson: unknown wedge-specific blocks are opaque -- accepted but never copied into the lesson", () => {
  const l = proofLesson(matchPacket());
  assert.ok(!JSON.stringify(l).includes("wedge_block"));
});

// ---- negative fixtures: rejection paths ----

test("proofLesson: a packet with a forged verdict enum is rejected", () => {
  assert.throws(() => proofLesson(forgedVerdictPacket()), /verdict/i);
});

test("proofLesson: packets missing packet_id, claim, or verdicts are rejected", () => {
  for (const field of ["packet_id", "claim", "verdicts"]) {
    const p = matchPacket();
    delete p[field];
    assert.throws(() => proofLesson(p), new RegExp(field.replace("_", ".")));
  }
});

test("proofLesson: a lesson claiming MATCH from a DRIFT packet is impossible by construction", () => {
  const l = proofLesson(driftPacket(), { verdict: "MATCH" }); // any override attempt is inert
  assert.equal(l.verdict, "DRIFT");
  assert.equal(l.verifierBinding.verdict, "DRIFT");
  // the derived lesson is frozen: mutating the verdict throws (strict mode), it never flips
  assert.throws(() => { l.verdict = "MATCH"; }, TypeError);
  assert.throws(() => { l.verifierBinding.verdict = "MATCH"; }, TypeError);
  assert.equal(l.verdict, "DRIFT");
});

// ---- misconception extraction ----

test("misconceptionFromPacket: a MATCH packet yields no misconception record", () => {
  assert.equal(misconceptionFromPacket(matchPacket()), null);
});

test("misconceptionFromPacket: DRIFT is typed contradicted with a why-prompt, never the answer", () => {
  const p = driftPacket();
  const m = misconceptionFromPacket(p);
  assert.equal(m.packet_id, "pkt-drift-1");
  assert.equal(m.verdict, "DRIFT");
  assert.equal(m.misconception_class, "contradicted");
  assert.match(m.prompt, /why/i);
  assert.ok(!m.prompt.includes(p.decision_summary));
});

test("misconceptionFromPacket: UNVERIFIABLE with recorded sources is typed overclaim", () => {
  const m = misconceptionFromPacket(unverifiablePacket({ withSources: true }));
  assert.equal(m.misconception_class, "overclaim");
  assert.equal(m.verdict, "UNVERIFIABLE");
});

test("misconceptionFromPacket: UNVERIFIABLE with no recorded sources is typed missing_evidence", () => {
  const m = misconceptionFromPacket(unverifiablePacket({ withSources: false }));
  assert.equal(m.misconception_class, "missing_evidence");
});

test("misconceptionFromPacket: a forged verdict enum is rejected here too", () => {
  assert.throws(() => misconceptionFromPacket(forgedVerdictPacket()), /verdict/i);
});

// ---- lesson receipt: chained into the ledger machinery, covered by reverify ----

test("proofLessonReceipt: a clean lesson receipt is hash-chained and re-verifies as VERIFIED", () => {
  const r = reverifyReceipt(roundTrip(proofLessonReceipt(driftPacket())));
  assert.equal(r.verdict, "VERIFIED");
  assert.deepEqual(r.failures, []);
  assert.match(r.witness.digest, /^sha256:[0-9a-f]{64}$/);
  assert.equal(r.summary.rederivedVerdict, "DRIFT");
});

test("proofLessonReceipt: embeds the misconception record for a DRIFT packet, null for MATCH", () => {
  assert.equal(proofLessonReceipt(driftPacket()).misconception.misconception_class, "contradicted");
  assert.equal(proofLessonReceipt(matchPacket()).misconception, null);
});

test("reverify: a tampered chained entry in a lesson receipt fails with CHAIN_BROKEN", () => {
  const receipt = roundTrip(proofLessonReceipt(driftPacket()));
  receipt.entries[1].entry.sha256 = hex("f");
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  const broken = r.failures.find((f) => f.code === CHAIN_BROKEN);
  assert.ok(broken, "expected a CHAIN_BROKEN failure");
  assert.equal(broken.seq, 1);
});

test("reverify: a lesson receipt hand-edited to claim MATCH from a DRIFT packet fails with VERDICT_MISMATCH", () => {
  const receipt = roundTrip(proofLessonReceipt(driftPacket()));
  // a consistent surface edit: verdict flipped everywhere the author controls
  receipt.verdict = "MATCH";
  receipt.lesson.verdict = "MATCH";
  receipt.lesson.verifierBinding.verdict = "MATCH";
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  assert.ok(r.failures.some((f) => f.code === VERDICT_MISMATCH));
});

test("reverify: an edited lesson body (scaffold prompt) with an intact chain fails with VERDICT_MISMATCH", () => {
  const receipt = roundTrip(proofLessonReceipt(driftPacket()));
  receipt.lesson.scaffold[0].prompt = "Here is the answer: it failed at n=7.";
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  assert.ok(r.failures.some((f) => f.code === VERDICT_MISMATCH));
});

test("reverify: a truncated lesson chain (dropped tail entry) fails with CHAIN_BROKEN via accounting", () => {
  const receipt = roundTrip(proofLessonReceipt(driftPacket()));
  receipt.entries.pop(); // hash-consistent truncation
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  assert.ok(r.failures.some((f) => f.code === CHAIN_BROKEN));
});

test("reverify: a chainless lesson receipt is UNVERIFIED, never verified", () => {
  const receipt = roundTrip(proofLessonReceipt(driftPacket()));
  delete receipt.entries;
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "UNVERIFIED");
  assert.ok(r.reasons.length > 0);
});

test("reverify: a lesson receipt carrying a forged verdict enum is UNVERIFIED (structurally invalid)", () => {
  const receipt = roundTrip(proofLessonReceipt(driftPacket()));
  receipt.verdict = "VERIFIED_SUPREME";
  receipt.lesson.verdict = "VERIFIED_SUPREME";
  receipt.lesson.verifierBinding.verdict = "VERIFIED_SUPREME";
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "UNVERIFIED");
});
