// Re-derivability + per-learner-fit tests for fsrsderive.mjs.
//
// The load-bearing claim: the FSRS schedule is a DETERMINISTIC, RE-DERIVABLE function of the recorded
// scored attempts. These tests replay the witnessed log and assert (a) the replay reproduces the live
// itemState bit-for-bit, (b) it is stable across repetitions, (c) intervals lengthen on successful
// recall and shorten on lapses, and (d) the receipt catches a tampered cache as DRIFT.
import { test } from "node:test";
import assert from "node:assert/strict";
import { newSessionWithFSRS, recordAttemptWithGrade } from "../src/tutor/tutor.mjs";
import { computeNextReview } from "../src/tutor/fsrs.mjs";
import {
  deriveItemStates,
  optimizeParameters,
  deriveScheduleReceipt,
} from "../src/tutor/fsrsderive.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const DAY_MS = 86400000;
const later = (days) => new Date(new Date(NOW).getTime() + days * DAY_MS).toISOString();

// Build a session with a graded review log for two objectives.
function studiedSession() {
  const s = newSessionWithFSRS({ topic: "derive", objectives: ["A", "B"] });
  // A: mostly successful recalls spaced out. B: a lapse then a fail.
  recordAttemptWithGrade(s, { objective: "A", grade: 3, now: later(0) });
  recordAttemptWithGrade(s, { objective: "A", grade: 3, now: later(2) });
  recordAttemptWithGrade(s, { objective: "A", grade: 4, now: later(6) });
  recordAttemptWithGrade(s, { objective: "B", grade: 3, now: later(0) });
  recordAttemptWithGrade(s, { objective: "B", grade: 2, now: later(1) });
  recordAttemptWithGrade(s, { objective: "B", grade: 0, now: later(2) });
  return s;
}

test("deriveItemStates: replaying the attempt log reproduces the live itemState bit-for-bit", () => {
  const s = studiedSession();
  const derived = deriveItemStates(s.attempts);
  // The live itemState was accumulated by the item scheduler; the replay must match it exactly.
  for (const id of ["A", "B"]) {
    assert.equal(derived[id].difficulty, s.itemState[id].difficulty, `${id} difficulty must re-derive exactly`);
    assert.equal(derived[id].stability, s.itemState[id].stability, `${id} stability must re-derive exactly`);
    assert.equal(derived[id].reviewCount, s.itemState[id].reviewCount, `${id} reviewCount must re-derive exactly`);
    assert.equal(derived[id].lastReviewAt, s.itemState[id].lastReviewAt, `${id} lastReviewAt must re-derive exactly`);
    assert.equal(derived[id].lastGrade, s.itemState[id].lastGrade, `${id} lastGrade must re-derive exactly`);
  }
});

test("deriveItemStates: derivation is deterministic (two replays are identical)", () => {
  const s = studiedSession();
  const one = deriveItemStates(s.attempts);
  const two = deriveItemStates(s.attempts);
  assert.deepEqual(one, two, "the same attempt log must always derive the same state");
});

test("deriveItemStates: intervals lengthen with successful recalls, shorten on a lapse/fail", () => {
  const s = studiedSession();
  const derived = deriveItemStates(s.attempts);
  // A had successful recalls; B ended on a fail. A's stability (hence its interval) must exceed B's.
  const aDue = computeNextReview(derived.A, { desiredRetention: 0.9, now: later(6) }).daysUntilDue;
  const bDue = computeNextReview(derived.B, { desiredRetention: 0.9, now: later(2) }).daysUntilDue;
  assert.ok(derived.A.stability > derived.B.stability, "successful-recall item must be more stable than the lapsed one");
  assert.ok(aDue > bDue, "the well-recalled item must be scheduled further out than the failed one");
});

test("deriveItemStates: a longer success streak yields a monotonically longer interval", () => {
  const s = newSessionWithFSRS({ topic: "streak", objectives: ["S"] });
  const stabilities = [];
  for (let i = 0; i < 4; i++) {
    recordAttemptWithGrade(s, { objective: "S", grade: 3, now: later(i * 3) });
    const d = deriveItemStates(s.attempts);
    stabilities.push(d.S.stability);
  }
  for (let i = 1; i < stabilities.length; i++) {
    assert.ok(stabilities[i] > stabilities[i - 1], "each successful recall must lengthen the interval");
  }
});

test("optimizeParameters: fits a per-learner difficulty prior from that learner's own accuracy", () => {
  const s = studiedSession();
  const { priors, perObjective, method } = optimizeParameters(s.attempts);
  // A was recalled correctly every time (grades 3,3,4 all count correct); B failed twice of three.
  assert.ok(priors.A > priors.B, "the all-correct objective must get an easier (higher) difficulty prior");
  assert.ok(priors.A >= 0.2 && priors.A <= 1.0 && priors.B >= 0.2 && priors.B <= 1.0, "priors stay in range");
  assert.equal(method, "difficulty-from-accuracy-prior");
  const a = perObjective.find((p) => p.objective === "A");
  assert.equal(a.attempts, 3);
  assert.equal(a.correct, 3);
});

test("optimizeParameters: priors seed the derivation without breaking re-derivability", () => {
  const s = studiedSession();
  const { priors } = optimizeParameters(s.attempts);
  const withPrior = deriveItemStates(s.attempts, { priors });
  const again = deriveItemStates(s.attempts, { priors });
  assert.deepEqual(withPrior, again, "prior-seeded derivation is still deterministic");
  // The prior only shifts the STARTING difficulty; the objective ids and review counts are unchanged.
  assert.equal(withPrior.A.reviewCount, s.itemState.A.reviewCount);
});

test("deriveScheduleReceipt: reports MATCH for an untampered session and verifies its ledger", () => {
  const s = studiedSession();
  const r = deriveScheduleReceipt(s);
  assert.equal(r.verdict, "MATCH", "an untampered cache must re-derive to MATCH");
  assert.equal(r.ledgerVerified, true, "the receipt's attempt ledger must verify");
  assert.equal(r.fsrsAttempts, 6);
  assert.ok(r.perObjective.every((p) => p.match), "every objective matches its re-derivation");
});

test("deriveScheduleReceipt: a tampered cached itemState is caught as DRIFT with a field diff", () => {
  const s = studiedSession();
  // Tamper with the cached hint so it no longer matches the witnessed log.
  s.itemState.A.stability = 9999;
  const r = deriveScheduleReceipt(s);
  assert.equal(r.verdict, "DRIFT", "a cache that disagrees with the log must be flagged, not trusted");
  const a = r.perObjective.find((p) => p.objective === "A");
  assert.equal(a.match, false);
  assert.ok(a.diffs.some((d) => d.field === "stability" && d.stored === 9999), "the diff names the tampered field");
});

test("deriveScheduleReceipt: NO_FSRS_LOG when there are no FSRS-graded attempts", () => {
  const s = newSessionWithFSRS({ topic: "empty", objectives: ["Z"] });
  const r = deriveScheduleReceipt(s);
  assert.equal(r.verdict, "NO_FSRS_LOG", "nothing to derive => explicit no-log verdict, not a false MATCH");
  assert.equal(r.fsrsAttempts, 0);
});

test("deriveItemStates: attempts without grade/timestamp (legacy Leitner) are ignored", () => {
  const s = newSessionWithFSRS({ topic: "legacy", objectives: ["L"] });
  // A plain correct/incorrect attempt with no FSRS metadata must not participate in replay.
  s.attempts.push({ objective: "L", prompt: "p", answer: "a", correct: true, feedback: "" });
  const derived = deriveItemStates(s.attempts);
  assert.equal(Object.keys(derived).length, 0, "non-FSRS attempts contribute nothing to the derived schedule");
});
