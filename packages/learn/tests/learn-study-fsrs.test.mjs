import { test } from "node:test";
import assert from "node:assert/strict";
import { newSessionWithFSRS, recordAttemptWithGrade } from "../src/tutor/tutor.mjs";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { studyPlan, studyReceipt } from "../src/tutor/study.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const DAY_MS = 86400000;
const later = (days) => new Date(new Date(NOW).getTime() + days * DAY_MS).toISOString();

test("studyPlan useFSRS=true: order is retrievability-ranked (most-at-risk first), not interleave", () => {
  const s = newSessionWithFSRS({ topic: "t", objectives: ["strong", "weak"] });
  // strong: three easy successes -> high stability. weak: a fail -> low stability.
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: NOW });
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: later(1) });
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: later(2) });
  recordAttemptWithGrade(s, { objective: "weak", grade: 0, now: later(2) });

  const plan = studyPlan(s, { now: later(3), useFSRS: true });
  assert.equal(plan.order[0], "weak", "FSRS order surfaces the most-at-risk item first");
  assert.deepEqual([...plan.order].sort(), ["strong", "weak"], "order is a permutation of the objectives");
});

test("studyPlan useFSRS=false (default): order still comes from the deterministic interleave", () => {
  const s = newSessionWithFSRS({ topic: "t", objectives: ["a", "b", "c"] });
  const p1 = studyPlan(s, { now: NOW, seed: "fixed" });
  const p2 = studyPlan(s, { now: NOW, seed: "fixed", useFSRS: false });
  assert.deepEqual(p1.order, p2.order, "default path unchanged");
  assert.deepEqual([...p1.order].sort(), ["a", "b", "c"]);
});

test("studyPlan useFSRS=true: readiness + misconceptions + mastery still compose correctly", () => {
  const s = newSessionWithFSRS({ topic: "t", objectives: ["a"] });
  recordAttemptWithGrade(s, { objective: "a", grade: 1, now: NOW }); // a slip -> incorrect attempt
  const plan = studyPlan(s, { now: later(1), useFSRS: true });
  // mastery reads attempts only; one incorrect attempt -> not ready.
  assert.equal(plan.mastery.ready, false);
  // the wrong attempt surfaces as a misconception.
  assert.ok(plan.misconceptions.some((m) => m.objective === "a"));
  // readiness present for the objective.
  assert.ok(plan.readiness.some((r) => r.objective === "a"));
});

test("studyReceipt useFSRS=true: witnessed record still verifies, mastery untouched by scheduling", () => {
  const s = newSessionWithFSRS({ topic: "t", objectives: ["a"] });
  recordAttemptWithGrade(s, { objective: "a", grade: 3, now: NOW });
  recordAttemptWithGrade(s, { objective: "a", grade: 4, now: later(1) });
  recordAttemptWithGrade(s, { objective: "a", grade: 3, now: later(2) });

  const receipt = studyReceipt(s, { now: later(3), useFSRS: true });
  assert.equal(receipt.verified, true, "ledger over session.attempts still verifies");
  assert.equal(receipt.mastery.ready, true);
  // Corrupt itemState -> receipt mastery must be identical (scheduling never leaks into the verdict).
  s.itemState.a.stability = -999;
  const receipt2 = studyReceipt(s, { now: later(3), useFSRS: true });
  assert.equal(receipt2.mastery.ready, receipt.mastery.ready);
});

test("studyReceipt/studyPlan useFSRS=true but no itemState: gracefully falls back (no throw)", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true });
  const plan = studyPlan(s, { now: NOW, useFSRS: true });
  assert.deepEqual([...plan.order].sort(), ["a"]);
  const receipt = studyReceipt(s, { now: NOW, useFSRS: true });
  assert.equal(receipt.verified, true);
});
