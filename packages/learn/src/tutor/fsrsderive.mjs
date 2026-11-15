// Re-derive the FSRS schedule PURELY from the witnessed graded attempt log, and fit a small
// per-learner parameter from that same log. This is the accountability spine applied to scheduling:
// session.itemState is only a cached HINT, and this module proves that hint is exactly what replaying
// session.attempts (the tamper-evident, hash-chained truth) produces, or reports the DRIFT.
//
// INTEGRITY (the load-bearing boundary this module defends):
//   - session.attempts is the GRADED, witnessed source of truth. Each FSRS-graded attempt carries a
//     `grade` (0-4) and an ISO `timestamp` (written by tutor.recordAttemptWithGrade). That is exactly
//     the information gradeAttempt() needs, so the ENTIRE itemState is a deterministic function of the
//     recorded attempts. Nothing here reads Date.now(); replay is anchored to each attempt's own
//     recorded timestamp, so a derivation is bit-for-bit reproducible.
//   - This module NEVER grades, never appends to session.attempts, and never feeds the mastery gate.
//     It only reconstructs / audits the scheduling hint. If itemState and the replay disagree, the
//     replay is authoritative (it comes from the witnessed log); the receipt reports DRIFT so a
//     tampered or stale cached hint is caught rather than trusted.
//
// The per-learner fit is deliberately honest and lightweight: it estimates a single initial-difficulty
// prior per objective from THAT learner's own accuracy on the objective (via difficultyFromAccuracy),
// not a full gradient-descent FSRS optimizer. It is a documented heuristic, not a claim of optimality.
import { initializeItem, gradeAttempt, difficultyFromAccuracy } from "./fsrs.mjs";
import { Ledger } from "../accountability/ledger.mjs";

function idOf(objective) {
  return typeof objective === "string" ? objective : (objective && objective.id);
}

// An attempt participates in FSRS replay only if it carries the scheduling metadata the model needs:
// an integer grade in [0,4] and a usable timestamp. Coarse correct/incorrect-only attempts (the
// legacy Leitner path) are intentionally skipped here; they never wrote itemState either.
function isFsrsAttempt(a) {
  if (!a || typeof a !== "object") return false;
  if (!Number.isInteger(a.grade) || a.grade < 0 || a.grade > 4) return false;
  if (a.timestamp === undefined || a.timestamp === null) return false;
  const ms = new Date(a.timestamp).getTime();
  return Number.isFinite(ms);
}

// deriveItemStates(attempts, {priors}) -> { objectiveId: itemState } reconstructed from the log.
//
// Replays the FSRS-graded attempts for each objective, in RECORDED ORDER, from a fresh initial state
// (optionally seeded with a per-objective difficulty prior from `priors`). The result mirrors exactly
// what itemscheduler.recordAttemptWithGrade would have accumulated, because both call the same pure
// gradeAttempt() with the same {grade, now}. `priors` is an optional { objectiveId: difficulty } map
// (e.g. the output of optimizeParameters) used only to seed the FIRST state; every subsequent step is
// driven by the recorded grades, so priors shift the starting point without breaking re-derivability.
export function deriveItemStates(attempts, { priors = {} } = {}) {
  const byObjective = new Map();
  const list = Array.isArray(attempts) ? attempts : [];

  for (const a of list) {
    if (!isFsrsAttempt(a)) continue;
    const id = idOf(a.objective);
    if (!id) continue;
    if (!byObjective.has(id)) {
      const priorD = priors && Number.isFinite(priors[id]) ? priors[id] : undefined;
      byObjective.set(id, initializeItem(priorD === undefined ? {} : { difficulty: priorD }));
    }
    const prev = byObjective.get(id);
    const updated = gradeAttempt(prev, { grade: a.grade, now: a.timestamp });
    // Preserve createdAt = the first graded instant for this objective, matching the itemscheduler.
    byObjective.set(id, { ...updated, createdAt: prev.createdAt ?? a.timestamp });
  }

  const out = {};
  for (const [id, state] of byObjective) out[id] = state;
  return out;
}

// optimizeParameters(attempts) -> { priors: {objectiveId: difficulty}, perObjective: [...] }
//
// The per-learner fit. For each objective, roll THIS learner's own correct/incorrect history into an
// initial-difficulty prior via difficultyFromAccuracy (all-correct => easy, all-wrong => hard). This
// personalizes where each item's stability growth starts from, using only the witnessed attempts, so
// the fit is itself re-derivable. Honest scope: this fits ONE parameter (initial difficulty) per item
// from accuracy; it is a documented heuristic prior, NOT a full FSRS weight optimization.
export function optimizeParameters(attempts) {
  const list = Array.isArray(attempts) ? attempts : [];
  const byObjective = new Map();
  for (const a of list) {
    const id = idOf(a && a.objective);
    if (!id) continue;
    if (!byObjective.has(id)) byObjective.set(id, []);
    byObjective.get(id).push(!!(a && a.correct));
  }

  const priors = {};
  const perObjective = [];
  for (const [id, history] of byObjective) {
    const difficulty = difficultyFromAccuracy(history);
    const correct = history.filter(Boolean).length;
    priors[id] = difficulty;
    perObjective.push({
      objective: id,
      attempts: history.length,
      correct,
      accuracy: history.length ? Math.round((correct / history.length) * 100) / 100 : 0,
      difficultyPrior: difficulty,
    });
  }
  perObjective.sort((a, b) => (a.objective < b.objective ? -1 : a.objective > b.objective ? 1 : 0));
  return { priors, perObjective, method: "difficulty-from-accuracy-prior", note: "heuristic per-item initial-difficulty prior fitted from this learner's own accuracy; not a full FSRS weight optimization." };
}

// Deep, order-independent-per-field comparison of two derived item states. Numbers are compared
// exactly (the math is deterministic, so a re-derivation must reproduce them exactly). Returns a list
// of human-readable field diffs (empty => identical).
function diffItem(a, b) {
  const fields = ["difficulty", "stability", "lastReviewAt", "reviewCount", "lastGrade"];
  const diffs = [];
  for (const f of fields) {
    const av = a ? a[f] : undefined;
    const bv = b ? b[f] : undefined;
    if (av !== bv) diffs.push({ field: f, stored: av, derived: bv });
  }
  return diffs;
}

// deriveScheduleReceipt(session, {optimize}) -> a witnessed re-derivation record.
//
// The verdict re-derives itemState from session.attempts ALONE (no priors) and compares it, field by
// field, to the cached session.itemState. That is the audit: the cache is trustworthy iff it equals a
// clean replay of the witnessed log. It emits a MATCH / DRIFT verdict and a hash-chained ledger over
// the graded attempts, so the receipt is itself tamper-evident (same posture as masteryReceipt).
//
//   verdict = "MATCH"      cached hint == replay of the witnessed log (schedule is provably re-derived)
//   verdict = "DRIFT"      cached hint differs from the log-derived state (stale or tampered cache)
//   verdict = "NO_FSRS_LOG" no FSRS-graded attempts exist to derive from (nothing to witness)
//
// The derived state is always authoritative; DRIFT surfaces the diff rather than hiding it.
//
// `optimize` (optional) is ADVISORY and does NOT move the verdict. When set, the receipt additionally
// carries the per-learner fit (`optimization`) and a `optimizedDerived` state seeded with the fitted
// difficulty priors, a suggestion for how a fresh session could START, computed from this learner's
// own accuracy. It is reported alongside the un-primed audit, never substituted for it.
export function deriveScheduleReceipt(session, { optimize = false } = {}) {
  const attempts = (session && session.attempts) || [];
  const fsrsAttempts = attempts.filter(isFsrsAttempt);
  // The audit derivation is ALWAYS un-primed: the cache must equal a clean replay of the log.
  const derived = deriveItemStates(attempts, {});
  const stored = (session && session.itemState) || {};

  const objectives = [...new Set([...Object.keys(derived), ...Object.keys(stored)])].sort();
  const perObjective = objectives.map((id) => {
    const diffs = diffItem(stored[id], derived[id]);
    return { objective: id, match: diffs.length === 0, diffs };
  });

  const ledger = new Ledger();
  for (const a of fsrsAttempts) {
    ledger.append({ kind: "fsrs-grade", objective: idOf(a.objective), grade: a.grade, timestamp: a.timestamp, correct: !!a.correct });
  }

  let verdict;
  if (fsrsAttempts.length === 0) verdict = "NO_FSRS_LOG";
  else verdict = perObjective.every((p) => p.match) ? "MATCH" : "DRIFT";

  const receipt = {
    verdict,
    topic: session && session.topic,
    fsrsAttempts: fsrsAttempts.length,
    derived,
    perObjective,
    ledgerVerified: ledger.verify().ok,
    entries: ledger.entries(),
    boundary: "Scheduling audit: re-derives the FSRS hint from the recorded graded log. It reads the log only; grades, attempts and the mastery gate stay as they are.",
  };

  if (optimize) {
    const optimization = optimizeParameters(attempts);
    receipt.optimization = optimization;
    receipt.priors = optimization.priors; // advisory: the fitted per-learner starting difficulty
    receipt.optimizedDerived = deriveItemStates(attempts, { priors: optimization.priors });
  }

  return receipt;
}
