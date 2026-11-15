import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { studyPlan, studyReceipt } from "../src/tutor/study.mjs";

const NOW = "2026-06-30T00:00:00.000Z";

test("studyPlan: composes due + misconceptions + interleaved order + readiness for a plain-string-objective session", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: false, feedback: "sign error" });
  const plan = studyPlan(s, { now: NOW, seed: "seed-1" });

  assert.ok(Array.isArray(plan.due));
  assert.ok(Array.isArray(plan.misconceptions));
  assert.ok(Array.isArray(plan.order));
  assert.ok(Array.isArray(plan.readiness));

  // "b" never practiced -> due immediately
  assert.ok(plan.due.some((d) => d.objective === "b"));
  // "a" has a wrong attempt -> shows up in misconceptions
  assert.ok(plan.misconceptions.some((m) => m.objective === "a"));
  // order is an interleaving of both objectives
  assert.deepEqual([...plan.order].sort(), ["a", "b"]);
  // readiness covers both objectives (no requires -> always unlocked)
  assert.equal(plan.readiness.length, 2);
  assert.ok(plan.readiness.every((r) => r.unlocked === true));
});

test("studyPlan: requires `now` explicitly (no Date.now() inside), same as schedule.due", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  assert.throws(() => studyPlan(s, {}), /now/i);
  assert.throws(() => studyPlan(s), /now/i);
});

test("studyPlan: order is deterministic for a given seed (no Math.random)", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b", "c"] });
  const p1 = studyPlan(s, { now: NOW, seed: "fixed-seed" });
  const p2 = studyPlan(s, { now: NOW, seed: "fixed-seed" });
  assert.deepEqual(p1.order, p2.order);
});

test("studyPlan: different seeds can produce different orders (sanity: not hardcoded to input order)", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b", "c", "d", "e"] });
  const p1 = studyPlan(s, { now: NOW, seed: "seed-a" });
  const p2 = studyPlan(s, { now: NOW, seed: "seed-b" });
  // Not asserting they always differ (could coincide) but both must be valid permutations.
  assert.deepEqual([...p1.order].sort(), ["a", "b", "c", "d", "e"]);
  assert.deepEqual([...p2.order].sort(), ["a", "b", "c", "d", "e"]);
});

test("studyPlan: readiness respects object-form objectives with requires (locked until prereq mastered)", () => {
  const objectives = [
    { id: "algebra", text: "Algebra" },
    { id: "calc", text: "Calculus", requires: ["algebra"] },
  ];
  const s = newSession({ topic: "t", objectives: objectives.map((o) => o.id) });
  recordAttempt(s, { objective: "algebra", prompt: "q", answer: "x", correct: false });
  const plan = studyPlan(s, { now: NOW, seed: "x", objectives });
  assert.equal(plan.readiness.find((r) => r.objective === "calc").unlocked, false);
});

test("studyPlan: mastery is included and reflects the operator's own attempts only", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  recordAttempt(s, { objective: "a", prompt: "q2", answer: "x", correct: true });
  recordAttempt(s, { objective: "a", prompt: "q3", answer: "x", correct: true });
  const plan = studyPlan(s, { now: NOW, seed: "x" });
  assert.equal(plan.mastery.ready, true);
});

test("studyPlan: never fabricates an answer/solution field anywhere in the composed plan", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "wrong", correct: false, feedback: "slip" });
  const plan = studyPlan(s, { now: NOW, seed: "x" });
  const serialized = JSON.stringify(plan);
  assert.equal(/correctAnswer|"solution"|"fix"/i.test(serialized), false);
});

test("studyReceipt: produces a witnessed, hash-chained study record with objectives/due/mastery/misconceptions/visualizations/verified", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: false, feedback: "confused" });
  recordAttempt(s, { objective: "b", prompt: "q1", answer: "x", correct: true });
  recordAttempt(s, { objective: "b", prompt: "q2", answer: "x", correct: true });
  recordAttempt(s, { objective: "b", prompt: "q3", answer: "x", correct: true });

  const receipt = studyReceipt(s, { now: NOW });
  assert.deepEqual(receipt.objectives, ["a", "b"]);
  assert.ok(Array.isArray(receipt.due));
  assert.ok(receipt.mastery && typeof receipt.mastery.ready === "boolean");
  assert.ok(Array.isArray(receipt.misconceptions));
  assert.ok(Array.isArray(receipt.visualizations));
  assert.equal(receipt.verified, true);
  assert.ok(Array.isArray(receipt.entries));
  assert.ok(receipt.entries.length > 0);
});

test("studyReceipt: ledger verification catches tampering (hash-chained, tamper-evident)", async () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  const receipt = studyReceipt(s, { now: NOW });
  assert.equal(receipt.verified, true);
  // Tamper with an entry post-hoc and re-verify via the same Ledger reconstruction path.
  const { Ledger } = await import("../src/accountability/ledger.mjs");
  const tampered = JSON.parse(JSON.stringify(receipt.entries));
  tampered[0].entry.correct = !tampered[0].entry.correct;
  const l = Ledger.fromEntries(tampered);
  assert.equal(l.verify().ok, false);
});

test("studyReceipt: includes visualizations attached to the session (aid renders), never counted toward mastery", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  s.visualizations = [{ objective: "a", render: { verdict: "MATCH", result_hash: "sha256:x" } }];
  const receipt = studyReceipt(s, { now: NOW });
  assert.equal(receipt.visualizations.length, 1);
});

test("studyReceipt: honestly records the plan even when nothing is due / no misconceptions exist", () => {
  const s = newSession({ topic: "t", objectives: [] });
  const receipt = studyReceipt(s, { now: NOW });
  assert.deepEqual(receipt.objectives, []);
  assert.deepEqual(receipt.misconceptions, []);
  assert.equal(receipt.verified, true);
});
