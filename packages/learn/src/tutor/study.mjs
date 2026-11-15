// Study orchestrator — composes the 6 learning-loop modules (schedule, misconception, retrieval,
// map) plus the existing mastery-gate into ONE study plan, and witnesses an honest study record.
//
// INTEGRITY: this module only COMPOSES read-only views over the operator's own session.attempts —
// it never grades, fabricates an answer, or hints at a certified/graded assessment. studyReceipt
// hash-chains exactly what was true of the session at `now` (objectives, due list, mastery,
// misconceptions, visualizations) so the record itself is tamper-evident, not just descriptive.
import { Ledger } from "../accountability/ledger.mjs";
import { mastery } from "./tutor.mjs";
import { due } from "./schedule.mjs";
import { misconceptions } from "./misconception.mjs";
import { interleave } from "./retrieval.mjs";
import { normalizeObjectives, readiness } from "./map.mjs";
import { sortByRetrievability } from "./itemscheduler.mjs";

function hasItemState(session) {
  return !!(session && session.itemState && Object.keys(session.itemState).length > 0);
}

function toEpochMsOrThrow(now) {
  if (now === undefined || now === null) {
    throw new Error("studyPlan/studyReceipt require an explicit `now` (ISO string or epoch ms)");
  }
  const ms = typeof now === "number" ? now : new Date(now).getTime();
  if (!Number.isFinite(ms)) {
    throw new Error("studyPlan/studyReceipt require a valid `now` (ISO string or epoch ms)");
  }
  return ms;
}

// studyPlan(session, {now, seed, objectives}) -> {due, misconceptions, order, readiness, mastery}
//
// - due: schedule.due(session, {now}) — objectives due for review, most-overdue first.
// - misconceptions: misconception.misconceptions(session) — ranked wrong-attempt aggregation.
// - order: retrieval.interleave(...) over the session's own objective ids, deterministically
//   shuffled by `seed` (defaults to the session topic so a plan is stable per-topic by default).
// - readiness: map.readiness(session, objectives, masteryResult) — per-objective unlock state.
//   `objectives` defaults to session.objectives (plain strings) but may be passed as the richer
//   {id,text,requires} form to express prerequisites.
// - mastery: tutor.mastery(session) — the existing mastery-gate, untouched.
export function studyPlan(session, { now, seed, objectives, useFSRS = false, desiredRetention = 0.9 } = {}) {
  toEpochMsOrThrow(now); // fail fast, same contract as schedule.due

  const objs = objectives || session.objectives || [];
  const norm = normalizeObjectives(objs);
  const ids = norm.map((o) => o.id);

  const fsrsActive = useFSRS && hasItemState(session);

  const m = mastery(session);
  const dueList = due(session, { now, useFSRS, desiredRetention });
  const miscon = misconceptions(session);
  // FSRS: study order is retrievability-ranked (most-at-risk first) over the same objective ids;
  // otherwise the deterministic seeded interleave is used, unchanged.
  let order;
  if (fsrsActive) {
    const ranked = sortByRetrievability(session, { now, desiredRetention })
      .map((r) => r.objective)
      .filter((id) => ids.includes(id));
    // Any objective without item state yet is appended (in declared order) so `order` always
    // covers the full objective set, never silently dropping an item.
    const seen = new Set(ranked);
    order = [...ranked, ...ids.filter((id) => !seen.has(id))];
  } else {
    order = interleave(ids, { seed: seed ?? session.topic ?? "learn-interleave" });
  }
  const ready = readiness(session, objs, m);

  return { due: dueList, misconceptions: miscon, order, readiness: ready, mastery: m };
}

// studyReceipt(session, {now, seed, objectives}) -> a witnessed (hash-chained) study record.
//
// Records the composed plan honestly: what objectives exist, what's due, the mastery verdict, the
// misconceptions surfaced, and any aid visualizations already attached to the session — then
// hash-chains one ledger entry per practice attempt (mirroring masteryReceipt's own pattern) so the
// record is tamper-evident. The spine here is a quiet floor: it proves the study happened as
// recorded, it does not itself grade or unlock anything beyond what studyPlan already computed.
export function studyReceipt(session, { now, seed, objectives, useFSRS = false, desiredRetention = 0.9 } = {}) {
  const plan = studyPlan(session, { now, seed, objectives, useFSRS, desiredRetention });

  const ledger = new Ledger();
  for (const a of session.attempts) {
    ledger.append({ kind: "practice", objective: a.objective, correct: a.correct, prompt: a.prompt });
  }

  return {
    topic: session.topic,
    objectives: [...session.objectives],
    due: plan.due,
    mastery: plan.mastery,
    misconceptions: plan.misconceptions,
    order: plan.order,
    readiness: plan.readiness,
    visualizations: session.visualizations || [],
    verified: ledger.verify().ok,
    entries: ledger.entries(),
    boundary: "Study record only — reflects the operator's own practice; never a graded-assessment answer.",
  };
}
