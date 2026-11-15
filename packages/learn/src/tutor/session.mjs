// Practice-session primitives with no Node built-ins, so a browser page can load them
// (src/browser.mjs). tutor.mjs re-exports every function here and adds the hash-chained receipt.
//
// INTEGRITY: unchanged from tutor.mjs. The session holds the operator's OWN practice attempts;
// mastery() reads session.attempts only, never a render, a prediction verdict or a scheduling hint.
import { initializeItems, recordAttemptWithGrade as recordItemGrade } from "./itemscheduler.mjs";

export function newSession({ topic, objectives = [] }) {
  return { topic, objectives: [...objectives], attempts: [] };
}

// newSessionWithFSRS({topic, objectives}) -> a session with per-item FSRS scheduling state seeded.
// Same shape as newSession() plus session.itemState pre-populated for each objective. The mastery
// path is unchanged: mastery()/masteryReceipt() still read session.attempts ONLY.
export function newSessionWithFSRS({ topic, objectives = [] }) {
  const s = newSession({ topic, objectives });
  initializeItems(s, objectives);
  return s;
}

// Record the operator's OWN answer to a PRACTICE question, and whether it was correct.
// `grade` (0-4) and `timestamp` (ISO) are OPTIONAL scheduling metadata for the FSRS path; they are
// only written to the attempt when provided, so the existing attempt shape is unchanged by default.
// `misconception` (optional) is a diagnosis leaf such as "misrecruited.receipt_as_verdict", from
// diagnoseChoice() in choice.mjs; misconceptions() counts it like an arithmetic diagnosis.
export function recordAttempt(session, { objective, prompt, answer, correct, feedback = "", grade, timestamp, misconception }) {
  const attempt = {
    objective,
    prompt: String(prompt).slice(0, 500),
    answer: String(answer).slice(0, 2000),
    correct: !!correct,
    feedback: String(feedback).slice(0, 800),
  };
  if (grade !== undefined && grade !== null) attempt.grade = grade;
  if (timestamp !== undefined && timestamp !== null) attempt.timestamp = timestamp;
  if (typeof misconception === "string" && misconception) attempt.misconception = misconception.slice(0, 120);
  session.attempts.push(attempt);
  return session;
}

// Map a coarse correct/incorrect into an FSRS grade when no explicit grade is given:
// false -> 1 (slip), true -> 3 (review). Explicit grades (0-4) override.
function gradeFromCorrect(correct) {
  return correct ? 3 : 1;
}

// recordAttemptWithGrade(session, {objective, grade, correct, now, ...}) -> session.
//
// The FSRS-aware recording path. It does BOTH, in order:
//   1) logs the attempt to session.attempts (the witnessed graded truth) via recordAttempt(), with
//      the grade + `now` timestamp attached for the audit trail; and
//   2) updates session.itemState[objective] via the item scheduler (the derived scheduling hint).
//
// INTEGRITY: the witnessed log is written first and is authoritative; itemState is a hint layered
// on top. `correct` for the mastery gate is derived from the grade when not passed explicitly
// (grade >= 3 counts as correct), so the two stay consistent. `now` is required (no Date.now()).
export function recordAttemptWithGrade(session, { objective, prompt = "", answer = "", feedback = "", grade, correct, now, misconception } = {}) {
  if (!objective) throw new Error("recordAttemptWithGrade requires an `objective`");
  if (now === undefined || now === null) {
    throw new Error("recordAttemptWithGrade requires an explicit `now` (ISO string or epoch ms)");
  }
  const g = grade === undefined || grade === null ? gradeFromCorrect(correct) : grade;
  const isCorrect = correct === undefined || correct === null ? g >= 3 : !!correct;
  const timestamp = typeof now === "number" ? new Date(now).toISOString() : now;

  recordAttempt(session, { objective, prompt, answer, correct: isCorrect, feedback, grade: g, timestamp, misconception });
  recordItemGrade(session, { objective, grade: g, now });
  return session;
}

// Attach an AID render (from telosRender) to the study log. Renders help the operator SEE the
// concept; they NEVER count toward mastery — mastery() reads only session.attempts.
export function recordVisualization(session, { objective, render }) {
  if (!session.visualizations) session.visualizations = [];
  session.visualizations.push({ objective, render });
  return session;
}

// Mastery-gate: ready only when EVERY objective has >= minAttempts and >= threshold accuracy.
export function mastery(session, { threshold = 0.8, minAttempts = 3 } = {}) {
  const perObjective = (session.objectives.length ? session.objectives : [...new Set(session.attempts.map((a) => a.objective))])
    .map((o) => {
      const at = session.attempts.filter((a) => a.objective === o);
      const correct = at.filter((a) => a.correct).length;
      const accuracy = at.length ? correct / at.length : 0;
      const ready = at.length >= minAttempts && accuracy >= threshold;
      return { objective: o, attempts: at.length, correct, accuracy: Math.round(accuracy * 100) / 100, ready };
    });
  const ready = perObjective.length > 0 && perObjective.every((p) => p.ready);
  return { ready, threshold, minAttempts, perObjective, weakest: perObjective.filter((p) => !p.ready).map((p) => p.objective) };
}
