import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, recordAttempt, mastery, masteryReceipt, recordVisualization } from "../src/tutor/tutor.mjs";

function studied() {
  const s = newSession({ topic: "waves", objectives: ["damping"] });
  recordAttempt(s, { objective: "damping", prompt: "q1", answer: "a", correct: true });
  recordAttempt(s, { objective: "damping", prompt: "q2", answer: "a", correct: true });
  recordAttempt(s, { objective: "damping", prompt: "q3", answer: "a", correct: true });
  return s;
}

test("recordVisualization attaches an aid render without changing mastery (invariant 5)", () => {
  const s = studied();
  const before = mastery(s);
  assert.equal(before.ready, true);

  recordVisualization(s, { objective: "damping", render: { provenance: "aid", verdict: "MATCH", result_hash: "sha256:b" } });
  const after = mastery(s);
  assert.deepEqual(after, before); // renders cannot move the mastery verdict
  assert.equal(s.visualizations.length, 1);
  assert.equal(s.visualizations[0].render.provenance, "aid");
});

test("masteryReceipt surfaces visualizations as aid, separate from practice", () => {
  const s = studied();
  recordVisualization(s, { objective: "damping", render: { provenance: "aid", verdict: "MATCH" } });
  const r = masteryReceipt(s);
  assert.equal(r.visualizations.length, 1);
  assert.equal(r.mastery.ready, true);
  assert.equal(r.totalAttempts, 3); // attempts, not renders, drive mastery
});
