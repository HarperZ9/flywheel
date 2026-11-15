// Misconception tracking over the tutor's own witnessed practice log (session.attempts).
//
// INTEGRITY: this module only aggregates the operator's OWN wrong attempts and the feedback they
// were given for them. It never fabricates a "correct answer" or a "solution" field — it surfaces
// nothing more than what the operator already saw during practice, ranked so the next study
// session can prioritize the objective the operator struggles with most.

import { diagnose } from "./diagnose.mjs";

// misconceptions(session) -> [{objective, count, notes:[feedback...], diagnoses?}]
// Aggregates WRONG attempts (correct === false) per objective, in recorded order, ranked by
// count descending (most-misunderstood objective first). Objectives with zero wrong attempts do
// not appear at all. When a wrong attempt is an arithmetic question the diagnosis tree covers
// (docs/MISCONCEPTION-DIAGNOSIS.md), `diagnoses` counts the causes, e.g. {"slip.one_digit": 2}.
// The field is absent when no attempt for that objective could be diagnosed.
export function misconceptions(session) {
  const byObjective = new Map();

  for (const a of session.attempts) {
    if (a.correct) continue; // only wrong attempts feed misconceptions
    const entry = byObjective.get(a.objective) || { objective: a.objective, count: 0, notes: [] };
    entry.count += 1;
    entry.notes.push(a.feedback || "");
    // A choice item records its diagnosis leaf on the attempt (choice.mjs); an arithmetic prompt
    // is diagnosed here from the prompt and answer.
    const leaf = a.misconception || diagnose({ prompt: a.prompt, answer: a.answer }).leaf;
    if (leaf) {
      entry.diagnoses = entry.diagnoses || {};
      entry.diagnoses[leaf] = (entry.diagnoses[leaf] || 0) + 1;
    }
    byObjective.set(a.objective, entry);
  }

  return [...byObjective.values()].sort((x, y) => y.count - x.count);
}
