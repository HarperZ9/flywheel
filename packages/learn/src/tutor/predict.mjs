// Predict-then-observe module — the operator commits to their OWN prediction BEFORE seeing an aid
// render (telosRender), then compares that render against their prediction and scores themselves.
//
// INTEGRITY: recordPrediction stores only the operator's OWN prediction text, as a pending attempt
// (correct: null) — never a fabricated "expected observation" field. scorePrediction never derives
// a verdict on its own; it only records the correctness the OPERATOR determined by comparing their
// prediction to the rendered observation (an aid, per src/interop/telos.mjs). A pending prediction
// (correct: null) must never be misread as a correct attempt by mastery() — recordAttempt's own
// `!!correct` coercion already handles this (null -> false), so pending predictions are counted as
// "not yet correct" rather than silently passing.
import { recordAttempt } from "./tutor.mjs";

// recordPrediction(session, {objective, prompt, prediction}) -> session
// Stores the operator's prediction as a pending attempt: answer = the prediction text,
// correct = null (pending — neither right nor wrong until scored against the observation).
export function recordPrediction(session, { objective, prompt, prediction }) {
  session.attempts.push({
    objective,
    prompt: String(prompt).slice(0, 500),
    answer: String(prediction).slice(0, 2000),
    correct: null,
    feedback: "",
  });
  return session;
}

// scorePrediction(session, {index, correct, note}) -> session
// Sets a PENDING prediction's correct verdict once the operator has compared their prediction to
// the rendered observation. Throws (rather than silently no-op-ing) on an out-of-range index or on
// an attempt that was not a pending prediction, so a real attempt can never be accidentally
// overwritten and a typo'd index can never be silently swallowed.
export function scorePrediction(session, { index, correct, note = "" } = {}) {
  const attempts = session.attempts || [];
  if (!Number.isInteger(index) || index < 0 || index >= attempts.length) {
    throw new Error(`scorePrediction: index ${index} is out of range (0..${attempts.length - 1})`);
  }
  const attempt = attempts[index];
  if (attempt.correct !== null) {
    throw new Error(`scorePrediction: attempt at index ${index} is not a pending prediction (already scored or not a prediction)`);
  }
  attempt.correct = !!correct;
  attempt.feedback = String(note).slice(0, 800);
  return session;
}
