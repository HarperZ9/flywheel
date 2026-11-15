import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { misconceptions } from "../src/tutor/misconception.mjs";

test("misconceptions: aggregates only WRONG attempts, correct attempts are excluded", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true, feedback: "nice" });
  recordAttempt(s, { objective: "a", prompt: "q2", answer: "y", correct: false, feedback: "confused sign convention" });
  const result = misconceptions(s);
  assert.equal(result.length, 1);
  assert.equal(result[0].objective, "a");
  assert.equal(result[0].count, 1);
  assert.deepEqual(result[0].notes, ["confused sign convention"]);
});

test("misconceptions: objective with zero wrong attempts does not appear at all", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  recordAttempt(s, { objective: "b", prompt: "q1", answer: "y", correct: false, feedback: "off by one" });
  const result = misconceptions(s);
  assert.equal(result.length, 1);
  assert.equal(result[0].objective, "b");
});

test("misconceptions: multiple wrong attempts on the same objective aggregate count + collect all feedback notes in order", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: false, feedback: "note one" });
  recordAttempt(s, { objective: "a", prompt: "q2", answer: "x", correct: true, feedback: "ignored, was correct" });
  recordAttempt(s, { objective: "a", prompt: "q3", answer: "x", correct: false, feedback: "note two" });
  const result = misconceptions(s);
  assert.equal(result.length, 1);
  assert.equal(result[0].count, 2);
  assert.deepEqual(result[0].notes, ["note one", "note two"]);
});

test("misconceptions: ranked by count, descending — most-misunderstood objective first", () => {
  const s = newSession({ topic: "t", objectives: ["low", "high", "mid"] });
  recordAttempt(s, { objective: "low", prompt: "q", answer: "x", correct: false, feedback: "n" });
  recordAttempt(s, { objective: "high", prompt: "q", answer: "x", correct: false, feedback: "n1" });
  recordAttempt(s, { objective: "high", prompt: "q2", answer: "x", correct: false, feedback: "n2" });
  recordAttempt(s, { objective: "high", prompt: "q3", answer: "x", correct: false, feedback: "n3" });
  recordAttempt(s, { objective: "mid", prompt: "q", answer: "x", correct: false, feedback: "n1" });
  recordAttempt(s, { objective: "mid", prompt: "q2", answer: "x", correct: false, feedback: "n2" });
  const result = misconceptions(s);
  assert.deepEqual(result.map((r) => r.objective), ["high", "mid", "low"]);
  assert.deepEqual(result.map((r) => r.count), [3, 2, 1]);
});

test("misconceptions: empty feedback string is still recorded as a note (not dropped)", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: false }); // no feedback given
  const result = misconceptions(s);
  assert.equal(result[0].count, 1);
  assert.deepEqual(result[0].notes, [""]);
});

test("misconceptions: no attempts at all -> empty array", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  assert.deepEqual(misconceptions(s), []);
});

test("misconceptions: all attempts correct -> empty array", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true });
  assert.deepEqual(misconceptions(s), []);
});

test("misconceptions: only reads session.attempts — never surfaces the correct answer, only the operator's own past feedback", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "What is 2+2?", answer: "5", correct: false, feedback: "arithmetic slip" });
  const result = misconceptions(s);
  const serialized = JSON.stringify(result);
  // The record must not fabricate or attach any "correctAnswer"/"solution" field.
  assert.equal(Object.prototype.hasOwnProperty.call(result[0], "correctAnswer"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(result[0], "solution"), false);
  assert.match(serialized, /arithmetic slip/);
});
