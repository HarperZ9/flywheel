import { test } from "node:test";
import assert from "node:assert/strict";
import { newSession, mastery } from "../src/tutor/tutor.mjs";
import { recordPrediction, scorePrediction } from "../src/tutor/predict.mjs";

test("recordPrediction: stores a prediction as a pending attempt with correct:null", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordPrediction(s, { objective: "a", prompt: "What happens if damping increases?", prediction: "it settles faster" });
  assert.equal(s.attempts.length, 1);
  const a = s.attempts[0];
  assert.equal(a.objective, "a");
  assert.equal(a.correct, null);
  assert.match(a.answer, /settles faster/);
  assert.match(a.prompt, /damping/);
});

test("recordPrediction: a pending prediction does not count toward mastery either way", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordPrediction(s, { objective: "a", prompt: "q", prediction: "p" });
  const m = mastery(s, { threshold: 0.8, minAttempts: 1 });
  // 1 attempt exists but it's pending (correct:null) -> must not read as correct, so not ready
  assert.equal(m.perObjective[0].attempts, 1);
  assert.equal(m.perObjective[0].correct, 0);
  assert.equal(m.perObjective[0].ready, false);
});

test("scorePrediction: sets correct on the referenced pending attempt by index", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordPrediction(s, { objective: "a", prompt: "q1", prediction: "p1" });
  recordPrediction(s, { objective: "a", prompt: "q2", prediction: "p2" });
  const idx = s.attempts.length - 1; // score the second prediction
  scorePrediction(s, { index: idx, correct: true, note: "matched the rendered observation" });
  assert.equal(s.attempts[idx].correct, true);
  assert.equal(s.attempts[0].correct, null, "unrelated pending prediction is untouched");
  assert.match(s.attempts[idx].feedback, /matched the rendered observation/);
});

test("scorePrediction: after scoring, the attempt counts toward mastery like any other attempt", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  for (let i = 0; i < 3; i++) recordPrediction(s, { objective: "a", prompt: "q" + i, prediction: "p" + i });
  s.attempts.forEach((_, i) => scorePrediction(s, { index: i, correct: true }));
  const m = mastery(s, { threshold: 0.8, minAttempts: 3 });
  assert.equal(m.ready, true);
  assert.equal(m.perObjective[0].correct, 3);
});

test("scorePrediction: correct:false is recorded faithfully (no silent pass)", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordPrediction(s, { objective: "a", prompt: "q", prediction: "p" });
  scorePrediction(s, { index: 0, correct: false, note: "prediction did not match observation" });
  assert.equal(s.attempts[0].correct, false);
});

test("scorePrediction: throws on an out-of-range index rather than silently no-op-ing", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordPrediction(s, { objective: "a", prompt: "q", prediction: "p" });
  assert.throws(() => scorePrediction(s, { index: 5, correct: true }));
  assert.throws(() => scorePrediction(s, { index: -1, correct: true }));
});

test("scorePrediction: throws when re-scoring an attempt that was not a pending prediction (no accidental overwrite of a real attempt)", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  // A normal (non-prediction) attempt, already scored.
  s.attempts.push({ objective: "a", prompt: "q", answer: "x", correct: true, feedback: "" });
  assert.throws(() => scorePrediction(s, { index: 0, correct: false }), /pending/i);
});

test("integrity: recordPrediction/scorePrediction never fabricate or attach a correct-answer/observation field — only the operator's own prediction text is stored", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  recordPrediction(s, { objective: "a", prompt: "What will the graph look like?", prediction: "it curves upward" });
  scorePrediction(s, { index: 0, correct: true, note: "matched render" });
  const serialized = JSON.stringify(s.attempts[0]);
  assert.equal(Object.prototype.hasOwnProperty.call(s.attempts[0], "observation"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(s.attempts[0], "correctAnswer"), false);
  assert.match(serialized, /curves upward/);
});

test("recordPrediction: returns the session for chaining, matching recordAttempt's convention", () => {
  const s = newSession({ topic: "t", objectives: ["a"] });
  const ret = recordPrediction(s, { objective: "a", prompt: "q", prediction: "p" });
  assert.equal(ret, s);
});
