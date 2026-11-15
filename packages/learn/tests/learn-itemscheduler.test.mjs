import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import {
  initializeItems,
  recordAttemptWithGrade,
  selectNextItem,
  sortByRetrievability,
} from "../src/tutor/itemscheduler.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const DAY_MS = 86400000;
const later = (days) => new Date(new Date(NOW).getTime() + days * DAY_MS).toISOString();

test("initializeItems: populates session.itemState for every objective, once, idempotently", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  initializeItems(s, s.objectives);
  assert.ok(s.itemState.a && s.itemState.b, "both objectives get item state");
  assert.equal(s.itemState.a.reviewCount, 0);
  const createdA = s.itemState.a.createdAt;
  // Re-initializing must not wipe existing state.
  s.itemState.a.stability = 42;
  initializeItems(s, s.objectives);
  assert.equal(s.itemState.a.stability, 42, "existing item state preserved");
  assert.equal(s.itemState.a.createdAt, createdA, "createdAt stable across re-init");
});

test("initializeItems: handles object-form objectives ({id,text}) too", () => {
  const s = newSession({ topic: "t", objectives: ["x"] });
  initializeItems(s, [{ id: "x", text: "X" }, { id: "y", text: "Y" }]);
  assert.ok(s.itemState.x && s.itemState.y);
});

test("recordAttemptWithGrade: mutates session.itemState ONLY, never session.attempts", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  initializeItems(s, s.objectives);
  const attemptsBefore = s.attempts.length;
  recordAttemptWithGrade(s, { objective: "a", grade: 3, now: NOW });
  assert.equal(s.attempts.length, attemptsBefore, "recordAttemptWithGrade must NOT touch session.attempts");
  assert.equal(s.itemState.a.reviewCount, 1);
  assert.equal(s.itemState.a.lastGrade, 3);
  assert.equal(s.itemState.a.lastReviewAt, NOW);
});

test("recordAttemptWithGrade: a success grows stability, a fail shrinks it", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  initializeItems(s, s.objectives);
  recordAttemptWithGrade(s, { objective: "a", grade: 3, now: NOW });
  const afterGood = s.itemState.a.stability;
  recordAttemptWithGrade(s, { objective: "a", grade: 3, now: later(3) });
  assert.ok(s.itemState.a.stability > afterGood, "consecutive successes keep growing stability");
  recordAttemptWithGrade(s, { objective: "a", grade: 0, now: later(4) });
  assert.ok(s.itemState.a.stability < afterGood, "a failure contracts stability");
});

test("recordAttemptWithGrade: auto-initializes item state for an objective that has none yet", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  // No initializeItems for "b" — it is missing from itemState.
  initializeItems(s, ["a"]);
  assert.equal(s.itemState.b, undefined);
  recordAttemptWithGrade(s, { objective: "b", grade: 3, now: NOW });
  assert.ok(s.itemState.b, "missing item must be auto-initialized, not silently dropped");
  assert.equal(s.itemState.b.reviewCount, 1);
});

test("recordAttemptWithGrade: requires objective, grade, and now", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  initializeItems(s, s.objectives);
  assert.throws(() => recordAttemptWithGrade(s, { objective: "a", grade: 3 }), /now/i);
  assert.throws(() => recordAttemptWithGrade(s, { objective: "a", now: NOW }), /grade/i);
  assert.throws(() => recordAttemptWithGrade(s, { grade: 3, now: NOW }), /objective/i);
});

test("sortByRetrievability: ranks items by modelled recall, lowest (most-at-risk) first", () => {
  const s = newSession({ topic: "t", objectives: ["strong", "weak"] });
  initializeItems(s, s.objectives);
  // strong: a long successful streak -> high stability -> slow decay.
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: NOW });
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: later(1) });
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: later(2) });
  // weak: a fail -> low stability -> fast decay.
  recordAttemptWithGrade(s, { objective: "weak", grade: 0, now: later(2) });

  const ranked = sortByRetrievability(s, { now: later(3) });
  assert.equal(ranked[0].objective, "weak", "most-at-risk (lowest retrievability) ranks first");
  assert.ok(ranked[0].retrievability <= ranked[1].retrievability);
  for (const r of ranked) {
    assert.ok(r.retrievability >= 0 && r.retrievability <= 1);
    assert.ok(Number.isFinite(r.daysUntilDue));
  }
});

test("sortByRetrievability: deterministic + reproducible for a fixed now (stable tie handling)", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b", "c"] });
  initializeItems(s, s.objectives);
  const r1 = sortByRetrievability(s, { now: NOW });
  const r2 = sortByRetrievability(s, { now: NOW });
  assert.deepEqual(r1.map((x) => x.objective), r2.map((x) => x.objective));
});

test("selectNextItem: returns the single most-at-risk item (lowest retrievability)", () => {
  const s = newSession({ topic: "t", objectives: ["strong", "weak"] });
  initializeItems(s, s.objectives);
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: NOW });
  recordAttemptWithGrade(s, { objective: "strong", grade: 4, now: later(1) });
  recordAttemptWithGrade(s, { objective: "weak", grade: 0, now: later(1) });
  const next = selectNextItem(s, { now: later(2) });
  assert.equal(next.objective, "weak");
  assert.ok(next.retrievability >= 0 && next.retrievability <= 1);
});

test("selectNextItem: returns null for a session with no items", () => {
  const s = newSession({ topic: "t", objectives: [] });
  initializeItems(s, s.objectives);
  assert.equal(selectNextItem(s, { now: NOW }), null);
});

test("selectNextItem/sortByRetrievability: require an explicit now", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  initializeItems(s, s.objectives);
  assert.throws(() => selectNextItem(s, {}), /now/i);
  assert.throws(() => sortByRetrievability(s, {}), /now/i);
});

test("sortByRetrievability: heals a corrupt (negative-stability) item instead of crashing", () => {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  initializeItems(s, s.objectives);
  s.itemState.a.stability = -999; // corruption
  const ranked = sortByRetrievability(s, { now: NOW, desiredRetention: 0.9 });
  const a = ranked.find((r) => r.objective === "a");
  assert.ok(a, "corrupt item still ranked, not dropped");
  assert.ok(Number.isFinite(a.daysUntilDue) && a.daysUntilDue > 0, "no nonsensical interval from corrupt state");
  assert.ok(s.itemState.a.stability > 0, "corrupt stability healed back to a positive value");
});
