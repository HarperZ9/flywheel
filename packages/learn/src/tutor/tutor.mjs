// Tutor layer — the "teach you" engine. Runs the study loop: objectives -> PRACTICE (the operator
// solves) -> self-check -> MASTERY-GATE. It records the operator's own practice attempts in a
// witnessed, hash-chained log and only reports "ready" once mastery is demonstrated.
//
// INTEGRITY: this teaches. It generates/holds PRACTICE and checks the OPERATOR's answers. It does
// NOT supply answers to the real graded credential assessment — that is taken by the operator via
// the run engine, whose `assess` steps always halt. Practice ≠ the certified exam.
import { Ledger } from "../accountability/ledger.mjs";
import { mastery } from "./session.mjs";

// The session primitives live in session.mjs (no Node built-ins, so the browser entry can load them).
export { newSession, newSessionWithFSRS, recordAttempt, recordAttemptWithGrade, recordVisualization, mastery } from "./session.mjs";

// A witnessed mastery record: a hash-chained log of the practice the operator did + the verdict.
// Proves genuine study preceded the real assessment; the tutor never took that assessment.
export function masteryReceipt(session) {
  const m = mastery(session);
  const ledger = new Ledger();
  for (const a of session.attempts) {
    ledger.append({ kind: "practice", objective: a.objective, correct: a.correct, prompt: a.prompt });
  }
  return {
    topic: session.topic,
    objectives: session.objectives,
    totalAttempts: session.attempts.length,
    mastery: m,
    ledgerVerified: ledger.verify().ok,
    boundary: "Practice only — the operator solved these; the real graded assessment is taken by the operator, not the tutor.",
    entries: ledger.entries(),
    visualizations: session.visualizations || [],
  };
}
