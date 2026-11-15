// FSRS ISOLATION — the load-bearing negative test.
//
// The integrity rule: "scheduling is a hint, grading is audited fact." session.itemState (the FSRS
// scheduling state) must NEVER influence the mastery verdict, which is derived from session.attempts
// alone. If a future change accidentally couples scheduling to grading, THIS test must fail loudly.
//
// It also proves the enforced boundary: a corrupt item state cannot ship a nonsensical interval to a
// learner, and recording a graded attempt for an item that has no state yet auto-initializes it
// rather than silently creating an ungraded scheduling hole.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  newSessionWithFSRS,
  recordAttemptWithGrade,
  mastery,
} from "../src/tutor/tutor.mjs";
import { studyReceipt } from "../src/tutor/study.mjs";
import { sortByRetrievability } from "../src/tutor/itemscheduler.mjs";
import { computeNextReview, initializeItem } from "../src/tutor/fsrs.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const DAY_MS = 86400000;
const later = (days) => new Date(new Date(NOW).getTime() + days * DAY_MS).toISOString();

test("FSRS item-state must NOT influence the mastery verdict (corrupt/delete/receipt-parity)", () => {
  // 1. Create a session with FSRS.
  const s = newSessionWithFSRS({ topic: "iso", objectives: ["X"] });

  // 2. Record graded attempts with mixed outcomes: grades 1,3,2,4,4 (+one more so we have 6 total).
  //    Grade->correct mapping: grade >= 3 counts as correct. So of [1,3,2,4,4,0]:
  //    correct = {3,4,4} = 3, incorrect = {1,2,0} = 3 -> 3/6 = 50%, below the 80% threshold.
  const grades = [1, 3, 2, 4, 4, 0];
  grades.forEach((g, i) => recordAttemptWithGrade(s, { objective: "X", grade: g, now: later(i) }));

  // 3-4. Mastery computed from session.attempts must be ready=false (3 correct / 6 = 50% < 80%).
  const correctCount = s.attempts.filter((a) => a.correct).length;
  assert.equal(s.attempts.length, 6);
  assert.equal(correctCount, 3, "grades 3,4,4 correct; 1,2,0 incorrect => 3/6");
  const baseline = mastery(s);
  assert.equal(baseline.ready, false, "50% is below the 80% mastery threshold");

  // 5-6. Deliberately corrupt itemState.X.stability, then re-check mastery: MUST be unchanged.
  s.itemState.X.stability = -999;
  assert.deepEqual(mastery(s), baseline, "corrupting itemState must not move the mastery verdict");

  // 7-8. Delete itemState.X entirely, then re-check mastery: MUST still be unchanged.
  delete s.itemState.X;
  assert.deepEqual(mastery(s), baseline, "deleting itemState must not move the mastery verdict");

  // 9. studyReceipt with useFSRS=true must report the SAME mastery.ready as the direct mastery()
  //    call, proving scheduling state never leaked into the verdict — even after corruption/deletion.
  const receipt = studyReceipt(s, { now: later(6), useFSRS: true });
  assert.equal(receipt.mastery.ready, baseline.ready, "receipt mastery must equal direct mastery()");
  assert.equal(receipt.verified, true, "the witnessed ledger over session.attempts still verifies");

  // 10. Second negative: recordAttemptWithGrade for an objective with NO itemState entry yet must
  //     auto-initialize the item (not silently create attempts without scheduling state).
  assert.equal(s.itemState["missing-item"], undefined);
  const attemptsBefore = s.attempts.length;
  recordAttemptWithGrade(s, { objective: "missing-item", grade: 3, now: later(7) });
  assert.ok(s.itemState["missing-item"], "missing item must be auto-initialized, not dropped");
  assert.equal(s.itemState["missing-item"].reviewCount, 1);
  assert.equal(s.attempts.length, attemptsBefore + 1, "the graded attempt is still witnessed");
});

test("CAN-IT-FAIL: invalid item state cannot ship a nonsensical interval to a learner", () => {
  // Directly feeding a corrupt (negative) stability to computeNextReview MUST throw, not silently
  // return a negative/infinite interval.
  const corrupt = { ...initializeItem({ stability: 5 }), stability: -999, lastReviewAt: NOW };
  assert.throws(() => computeNextReview(corrupt, { desiredRetention: 0.9, now: NOW }), /stability/i);

  // But the scheduler layer (sortByRetrievability) HEALS a corrupt item and yields a sane interval,
  // so an operator study session can never surface a negative-days / infinite-loop schedule.
  const s = newSessionWithFSRS({ topic: "iso", objectives: ["a", "b"] });
  recordAttemptWithGrade(s, { objective: "a", grade: 3, now: NOW });
  s.itemState.a.stability = -999; // corrupt after the fact
  s.itemState.b.difficulty = 42;  // out-of-range corruption
  const ranked = sortByRetrievability(s, { now: later(1), desiredRetention: 0.9 });
  for (const r of ranked) {
    assert.ok(Number.isFinite(r.daysUntilDue) && r.daysUntilDue > 0, `sane interval for ${r.objective}`);
    assert.ok(r.retrievability >= 0 && r.retrievability <= 1, `retrievability in range for ${r.objective}`);
  }
  // And the corruption is healed in place.
  assert.ok(s.itemState.a.stability > 0, "negative stability healed");
  assert.ok(s.itemState.b.difficulty >= 0.2 && s.itemState.b.difficulty <= 1.0, "out-of-range difficulty healed");

  // Conversely, once state is valid, scheduling succeeds cleanly (the boundary lets good state through).
  const good = computeNextReview(initializeItem({ stability: 5 }), { desiredRetention: 0.9, now: NOW });
  assert.ok(good.daysUntilDue > 0 && Number.isFinite(good.nextReviewAtMs));
});

test("CAN-IT-FAIL (write path): grading a corrupt item heals before grading, never emitting NaN/inf state", () => {
  // The self-heal guarantee must also cover the GRADING/WRITE path, not only the ranking/READ path.
  // gradeAttempt divides by item.stability when computing retrievability; a corrupt stored stability
  // (NaN / Infinity / negative) must be healed BEFORE grading, or the write silently persists a
  // nonsensical item-state that then ships a bad interval to the learner.
  for (const badStability of [NaN, Infinity, -Infinity, -999, 0]) {
    const s = newSessionWithFSRS({ topic: "iso", objectives: ["X"] });
    recordAttemptWithGrade(s, { objective: "X", grade: 3, now: NOW });
    s.itemState.X.stability = badStability; // corrupt AFTER a clean grade
    // Grade the already-corrupt entry again. This is the write path the read-path heal never covers.
    recordAttemptWithGrade(s, { objective: "X", grade: 3, now: later(1) });
    const after = s.itemState.X;
    assert.ok(
      Number.isFinite(after.stability) && after.stability > 0,
      `write-path grade over corrupt stability=${badStability} must yield finite positive stability, got ${after.stability}`,
    );
    assert.ok(
      after.difficulty >= 0.2 && after.difficulty <= 1.0,
      `difficulty stays in range after grading a corrupt item (${after.difficulty})`,
    );
    // And the healed, graded state must schedule a sane interval (no throw, positive days).
    const { daysUntilDue } = computeNextReview(after, { desiredRetention: 0.9, now: later(2) });
    assert.ok(Number.isFinite(daysUntilDue) && daysUntilDue > 0, `sane interval after write-path heal (${badStability})`);
  }

  // Corrupt difficulty on the write path must likewise heal, not propagate out of range.
  const s2 = newSessionWithFSRS({ topic: "iso", objectives: ["Y"] });
  recordAttemptWithGrade(s2, { objective: "Y", grade: 3, now: NOW });
  s2.itemState.Y.difficulty = 42; // out of range
  recordAttemptWithGrade(s2, { objective: "Y", grade: 4, now: later(1) });
  assert.ok(
    s2.itemState.Y.difficulty >= 0.2 && s2.itemState.Y.difficulty <= 1.0,
    `out-of-range difficulty healed on the write path (${s2.itemState.Y.difficulty})`,
  );
});
