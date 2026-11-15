import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { reviewState, due } from "../src/tutor/schedule.mjs";

const NOW = "2026-06-30T00:00:00.000Z";

test("reviewState: unseen objective (no attempts) is due immediately, streak 0, interval 1", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  const states = reviewState(s, { now: NOW });
  const b = states.find((x) => x.objective === "b");
  assert.equal(b.seen, 0);
  assert.equal(b.streak, 0);
  assert.equal(b.intervalDays, 1);
  assert.equal(b.due, true);
  assert.equal(b.dueAt, NOW); // never practiced -> due right now, not pushed into the future
});

test("reviewState: requires a `now` argument (ISO string or epoch ms)", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  assert.throws(() => reviewState(s, {}), /now/i);
  assert.throws(() => reviewState(s), /now/i);
});

test("reviewState: consecutive-correct streak grows the interval (SM-2-lite/Leitner ladder)", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  recordAttempt(s, { objective: "a", prompt: "q2", answer: "x", correct: true });
  recordAttempt(s, { objective: "a", prompt: "q3", answer: "x", correct: true });
  const [state] = reviewState(s, { now: NOW });
  assert.equal(state.seen, 3);
  assert.equal(state.streak, 3);
  // interval must grow monotonically with streak, and be strictly greater than the seed of 1
  assert.ok(state.intervalDays > 1);
});

test("reviewState: longer streaks never produce a shorter (or equal, once distinct) interval", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  const seen = [];
  for (let i = 0; i < 6; i++) {
    recordAttempt(s, { objective: "a", prompt: "q" + i, answer: "x", correct: true });
    seen.push(reviewState(s, { now: NOW })[0].intervalDays);
  }
  for (let i = 1; i < seen.length; i++) {
    assert.ok(seen[i] >= seen[i - 1], `interval must be monotonically non-decreasing with streak (${seen})`);
  }
  assert.ok(seen[seen.length - 1] > seen[0], "interval must eventually grow past the seed value");
});

test("reviewState: a wrong attempt resets streak to 0 and interval to 1 day", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  recordAttempt(s, { objective: "a", prompt: "q2", answer: "x", correct: true });
  recordAttempt(s, { objective: "a", prompt: "q3", answer: "x", correct: false }); // wrong resets
  const [state] = reviewState(s, { now: NOW });
  assert.equal(state.streak, 0);
  assert.equal(state.intervalDays, 1);
});

test("reviewState: a seen objective's dueAt is `now` + intervalDays, and is not due at that same `now`", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q1", answer: "x", correct: true });
  recordAttempt(s, { objective: "a", prompt: "q2", answer: "x", correct: true });
  const [state] = reviewState(s, { now: NOW });
  const expectedDueAt = new Date(new Date(NOW).getTime() + state.intervalDays * 86400000).toISOString();
  assert.equal(state.dueAt, expectedDueAt);
  // Just reviewed as of `now` (2 correct attempts already logged) -> not due again until dueAt.
  assert.equal(state.due, false);
});

test("reviewState accepts epoch ms for `now` as well as ISO string", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true });
  const nowMs = new Date(NOW).getTime();
  const viaMs = reviewState(s, { now: nowMs });
  const viaIso = reviewState(s, { now: NOW });
  assert.deepEqual(viaMs, viaIso);
});

test("due(): with only `now`, only never-practiced objectives are due (freshly anchored clocks can't already be overdue)", () => {
  const s = newSession({ topic: "t", objectives: ["fresh", "practiced"] });
  recordAttempt(s, { objective: "practiced", prompt: "q", answer: "x", correct: true });
  const list = due(s, { now: NOW });
  const objectives = list.map((d) => d.objective);
  assert.deepEqual(objectives, ["fresh"]);
});

test("due(): with `asOf` (the instant the review clock was last anchored), checks a later `now` against that schedule", () => {
  const s = newSession({ topic: "t", objectives: ["fresh", "short-interval", "long-interval"] });

  // short-interval: single correct attempt -> smallest non-zero interval (1 day).
  recordAttempt(s, { objective: "short-interval", prompt: "q", answer: "x", correct: true });
  // long-interval: long correct streak -> a large interval (well beyond 5 days).
  recordAttempt(s, { objective: "long-interval", prompt: "q", answer: "x", correct: true });
  recordAttempt(s, { objective: "long-interval", prompt: "q2", answer: "x", correct: true });
  recordAttempt(s, { objective: "long-interval", prompt: "q3", answer: "x", correct: true });
  recordAttempt(s, { objective: "long-interval", prompt: "q4", answer: "x", correct: true });
  recordAttempt(s, { objective: "long-interval", prompt: "q5", answer: "x", correct: true });

  const longIv = reviewState(s, { now: NOW }).find((r) => r.objective === "long-interval").intervalDays;
  assert.ok(longIv > 5, "test fixture assumption: long streak must produce interval > 5 days");

  const laterNow = new Date(new Date(NOW).getTime() + 5 * 86400000).toISOString(); // 5 days later
  const list = due(s, { now: laterNow, asOf: NOW });
  const objectives = list.map((d) => d.objective);

  assert.ok(objectives.includes("fresh"));
  assert.ok(objectives.includes("short-interval"));
  assert.ok(!objectives.includes("long-interval"));
});

test("due(): most-overdue first", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true }); // interval 1 day
  recordAttempt(s, { objective: "b", prompt: "q", answer: "x", correct: true });
  recordAttempt(s, { objective: "b", prompt: "q2", answer: "x", correct: true }); // interval 2 days

  // 10 days later: both "a" (due after 1 day) and "b" (due after 2 days) are overdue; "a" longer.
  const laterNow = new Date(new Date(NOW).getTime() + 10 * 86400000).toISOString();
  const list = due(s, { now: laterNow, asOf: NOW });
  assert.deepEqual(list.map((d) => d.objective), ["a", "b"]);
});

test("due(): boundary is inclusive — objective due exactly at `now` counts as due", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true });
  const [state] = reviewState(s, { now: NOW });
  const list = due(s, { now: state.dueAt, asOf: NOW });
  assert.ok(list.some((d) => d.objective === "a"));
});
