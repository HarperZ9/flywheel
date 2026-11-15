import { test } from "node:test";
import assert from "node:assert/strict";
import {
  initializeItem,
  gradeAttempt,
  computeNextReview,
  difficultyFromAccuracy,
} from "../src/tutor/fsrs.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const DAY_MS = 86400000;

test("initializeItem: returns a well-formed item with defaults in range", () => {
  const item = initializeItem();
  assert.ok(item.difficulty >= 0.2 && item.difficulty <= 1.0, "difficulty in [0.2,1.0]");
  assert.ok(item.stability > 0, "stability positive");
  assert.equal(item.reviewCount, 0);
  assert.equal(item.lastReviewAt, null);
  assert.equal(item.lastGrade, null);
});

test("initializeItem: clamps out-of-range difficulty/stability to safe bounds", () => {
  const tooHard = initializeItem({ difficulty: -5, stability: -10 });
  assert.ok(tooHard.difficulty >= 0.2, "negative difficulty clamped up to floor");
  assert.ok(tooHard.stability > 0, "negative stability clamped to a positive floor");
  const tooEasy = initializeItem({ difficulty: 99 });
  assert.ok(tooEasy.difficulty <= 1.0, "huge difficulty clamped down to ceiling");
});

test("gradeAttempt: requires an explicit `now` (no Date.now() inside)", () => {
  const item = initializeItem();
  assert.throws(() => gradeAttempt(item, { grade: 3 }), /now/i);
  assert.throws(() => gradeAttempt(item, { grade: 3, now: undefined }), /now/i);
});

test("gradeAttempt: a good review (grade 3) grows stability; a fail (grade 0) shrinks it", () => {
  const item = initializeItem({ stability: 2 });
  // Two reviews spaced a day apart so retrievability is meaningfully below 1.
  const reviewed = gradeAttempt({ ...item, lastReviewAt: NOW }, { grade: 3, now: new Date(new Date(NOW).getTime() + 2 * DAY_MS).toISOString() });
  assert.ok(reviewed.stability > item.stability, "successful review must increase stability");
  const failed = gradeAttempt({ ...item, lastReviewAt: NOW }, { grade: 0, now: new Date(new Date(NOW).getTime() + 2 * DAY_MS).toISOString() });
  assert.ok(failed.stability < item.stability, "a failure must decrease stability");
  assert.ok(failed.stability > 0, "stability stays positive even after failure");
});

test("gradeAttempt: an easy grade (4) grows stability more than a plain review (3)", () => {
  const base = { ...initializeItem({ stability: 3 }), lastReviewAt: NOW };
  const later = new Date(new Date(NOW).getTime() + 3 * DAY_MS).toISOString();
  const review = gradeAttempt(base, { grade: 3, now: later });
  const easy = gradeAttempt(base, { grade: 4, now: later });
  assert.ok(easy.stability > review.stability, "easy recall must earn a longer interval than a plain review");
});

test("gradeAttempt: records lastGrade, lastReviewAt=now, and increments reviewCount", () => {
  const item = initializeItem();
  const g = gradeAttempt(item, { grade: 2, now: NOW });
  assert.equal(g.lastGrade, 2);
  assert.equal(g.lastReviewAt, NOW);
  assert.equal(g.reviewCount, 1);
});

test("gradeAttempt: rejects out-of-range grades", () => {
  const item = initializeItem();
  assert.throws(() => gradeAttempt(item, { grade: 5, now: NOW }), /grade/i);
  assert.throws(() => gradeAttempt(item, { grade: -1, now: NOW }), /grade/i);
});

test("computeNextReview: retrievability decays with elapsed time and never leaves [0,1]", () => {
  const item = { ...initializeItem({ stability: 5 }), lastReviewAt: NOW };
  const rAtReview = computeNextReview(item, { desiredRetention: 0.9, now: NOW }).retrievability;
  const later = new Date(new Date(NOW).getTime() + 5 * DAY_MS).toISOString();
  const rLater = computeNextReview(item, { desiredRetention: 0.9, now: later }).retrievability;
  assert.ok(rAtReview <= 1 && rAtReview >= 0);
  assert.ok(rLater >= 0 && rLater <= 1);
  assert.ok(rLater < rAtReview, "retrievability must decay as time passes");
});

test("computeNextReview: higher desiredRetention yields a shorter interval (due sooner)", () => {
  const item = { ...initializeItem({ stability: 10 }), lastReviewAt: NOW };
  const strict = computeNextReview(item, { desiredRetention: 0.95, now: NOW });
  const loose = computeNextReview(item, { desiredRetention: 0.8, now: NOW });
  assert.ok(strict.daysUntilDue < loose.daysUntilDue, "a stricter retention target must review sooner");
  assert.ok(strict.daysUntilDue > 0 && Number.isFinite(strict.daysUntilDue));
  assert.equal(strict.nextReviewAtMs, new Date(NOW).getTime() + Math.round(strict.daysUntilDue * DAY_MS));
});

test("computeNextReview: requires `now`, and rejects a corrupt (non-positive) stability", () => {
  const item = { ...initializeItem({ stability: 5 }), lastReviewAt: NOW };
  assert.throws(() => computeNextReview(item, { desiredRetention: 0.9 }), /now/i);
  const corrupt = { ...item, stability: -999 };
  assert.throws(() => computeNextReview(corrupt, { desiredRetention: 0.9, now: NOW }), /stability/i);
});

test("difficultyFromAccuracy: all-correct history is easy (near 1.0); all-wrong is hard (near 0.2)", () => {
  const easy = difficultyFromAccuracy([true, true, true, true]);
  const hard = difficultyFromAccuracy([false, false, false, false]);
  assert.ok(easy > hard, "more correct history -> easier item");
  assert.ok(easy <= 1.0 && easy >= 0.2);
  assert.ok(hard <= 1.0 && hard >= 0.2);
});

test("difficultyFromAccuracy: empty history returns a mid-range default (no NaN)", () => {
  const d = difficultyFromAccuracy([]);
  assert.ok(Number.isFinite(d));
  assert.ok(d >= 0.2 && d <= 1.0);
});
