import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { reviewState, due } from "../src/tutor/schedule.mjs";
import { initializeItems, recordAttemptWithGrade } from "../src/tutor/itemscheduler.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const DAY_MS = 86400000;
const later = (days) => new Date(new Date(NOW).getTime() + days * DAY_MS).toISOString();

test("reviewState: useFSRS=false (default) is the untouched Leitner path", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true });
  const leitner = reviewState(s, { now: NOW });
  const explicitDefault = reviewState(s, { now: NOW, useFSRS: false });
  assert.deepEqual(leitner, explicitDefault);
  // Leitner shape carries streak + intervalDays from the fixed ladder.
  assert.ok(Object.prototype.hasOwnProperty.call(leitner[0], "streak"));
  assert.ok(Object.prototype.hasOwnProperty.call(leitner[0], "intervalDays"));
});

test("reviewState: useFSRS=true with itemState delegates to retrievability-based scheduling", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  initializeItems(s, s.objectives);
  recordAttemptWithGrade(s, { objective: "a", grade: 3, now: NOW });
  const fsrs = reviewState(s, { now: later(1), useFSRS: true, desiredRetention: 0.9 });
  assert.equal(fsrs.length, 1);
  const a = fsrs[0];
  assert.equal(a.objective, "a");
  assert.ok(a.retrievability >= 0 && a.retrievability <= 1, "FSRS state exposes retrievability");
  assert.ok(Number.isFinite(a.intervalDays) && a.intervalDays > 0, "FSRS produces a positive interval");
  assert.ok(typeof a.dueAt === "string");
});

test("reviewState: useFSRS=true but NO itemState gracefully falls back to Leitner", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: true });
  // No itemState on the session -> flag is advisory, must not throw, must equal Leitner output.
  const fallback = reviewState(s, { now: NOW, useFSRS: true });
  const leitner = reviewState(s, { now: NOW, useFSRS: false });
  assert.deepEqual(fallback, leitner);
});

test("due: useFSRS=true surfaces FSRS-overdue items; Leitner path unchanged when flag off", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  initializeItems(s, s.objectives);
  // Grade a fail so stability is tiny -> becomes overdue quickly under FSRS.
  recordAttemptWithGrade(s, { objective: "a", grade: 0, now: NOW });
  const overdue = due(s, { now: later(30), useFSRS: true });
  assert.ok(overdue.some((d) => d.objective === "a"), "a low-stability item is overdue 30 days later under FSRS");

  // With the flag off, no itemState is consulted; the Leitner contract still holds (no throw).
  const leitner = due(s, { now: NOW, useFSRS: false });
  assert.ok(Array.isArray(leitner));
});
