// Pure FSRS-class memory math for the tutor — per-item difficulty / stability / retrievability.
//
// INTEGRITY: this module is pure and I/O-free. There is NO Date.now() anywhere — every function
// that needs the current instant takes an explicit `now` (ISO string or epoch ms), so a graded
// attempt and its scheduled next review are fully deterministic and testable. Nothing here reads
// or writes a session; it only transforms plain item-state objects into new item-state objects.
//
// Model (FSRS-class, deliberately lightweight and zero-dependency):
//   - stability S (days): the memory strength; the interval at which retrievability decays to the
//     target. Higher S = a longer safe gap. S > 0 always.
//   - difficulty D in [0.2, 1.0]: item hardness, where LOWER = harder (per the learn design spec).
//     D modulates how much a successful review grows stability (a hard item grows slower).
//   - retrievability R in [0,1]: the modelled probability the operator would recall the item right
//     now, R = exp(-elapsedDays / S). It is a MODEL estimate, never a graded fact — grading lives
//     in session.attempts, this only schedules WHEN to re-practice.
//
// Grades (0-4), matching the design spec: 0=fail, 1=slip, 2=lapse, 3=review, 4=easy.

const DIFFICULTY_FLOOR = 0.2;
const DIFFICULTY_CEIL = 1.0;
const STABILITY_FLOOR = 0.1; // days; a just-failed item is still due "soon", never instantly-forever
const DEFAULT_DIFFICULTY = 0.5;
const DEFAULT_STABILITY = 1.0;

function clamp(x, lo, hi) {
  return Math.min(Math.max(x, lo), hi);
}

function toEpochMs(now, who) {
  if (now === undefined || now === null) {
    throw new Error(`${who} requires an explicit \`now\` (ISO string or epoch ms)`);
  }
  const ms = typeof now === "number" ? now : new Date(now).getTime();
  if (!Number.isFinite(ms)) {
    throw new Error(`${who} requires a valid \`now\` (ISO string or epoch ms)`);
  }
  return ms;
}

// initializeItem({difficulty, stability}) -> fresh item state (clamped into valid ranges).
export function initializeItem({ difficulty = DEFAULT_DIFFICULTY, stability = DEFAULT_STABILITY } = {}) {
  const d = Number.isFinite(difficulty) ? clamp(difficulty, DIFFICULTY_FLOOR, DIFFICULTY_CEIL) : DEFAULT_DIFFICULTY;
  const s = Number.isFinite(stability) && stability > 0 ? Math.max(stability, STABILITY_FLOOR) : DEFAULT_STABILITY;
  return {
    difficulty: d,
    stability: s,
    lastReviewAt: null,
    reviewCount: 0,
    lastGrade: null,
  };
}

// retrievability at `now` given an item last reviewed at item.lastReviewAt with stability S.
// A never-reviewed item (lastReviewAt null) is treated as fully retrievable at its own creation
// instant (R = 1) — it has not had time to decay yet.
function retrievabilityAt(item, nowMs) {
  if (item.lastReviewAt === null || item.lastReviewAt === undefined) return 1;
  const lastMs = typeof item.lastReviewAt === "number" ? item.lastReviewAt : new Date(item.lastReviewAt).getTime();
  const elapsedDays = Math.max(0, (nowMs - lastMs) / 86400000);
  return Math.exp(-elapsedDays / item.stability);
}

// gradeAttempt(item, {grade, now}) -> updated item.
//
// A successful review (grade >= 3) grows stability by a factor that is larger when the item was
// harder to recall (low R at review time earns more strength — the "desirable difficulty" effect)
// and larger for an easy grade than a plain review. A failure (grade < 2) contracts stability
// toward the floor. Grade 2 (lapse) is a near-miss: a small contraction. Difficulty drifts down
// (harder) on failure and up (easier) on easy success, staying within [0.2, 1.0].
export function gradeAttempt(item, { grade, now } = {}) {
  const nowMs = toEpochMs(now, "gradeAttempt");
  if (!Number.isInteger(grade) || grade < 0 || grade > 4) {
    throw new Error("gradeAttempt requires an integer `grade` in [0,4] (0=fail,1=slip,2=lapse,3=review,4=easy)");
  }
  const base = initializeItem({ difficulty: item.difficulty, stability: item.stability });
  const R = retrievabilityAt(item, nowMs);
  const D = base.difficulty;

  let stability = base.stability;
  let difficulty = D;

  if (grade >= 3) {
    // Success. Growth factor rises as (a) the item was closer to being forgotten (1-R) and
    // (b) the grade was easier. Difficulty (D in [0.2,1]) scales the growth: easier item -> more.
    const easyBonus = grade === 4 ? 1.4 : 1.0;
    const growth = 1 + (1 + 2 * (1 - R)) * D * easyBonus;
    stability = base.stability * growth;
    if (grade === 4) difficulty = clamp(D + 0.05, DIFFICULTY_FLOOR, DIFFICULTY_CEIL);
  } else if (grade === 2) {
    // Lapse: recalled but shakily. Small contraction, difficulty nudged harder.
    stability = base.stability * 0.7;
    difficulty = clamp(D - 0.05, DIFFICULTY_FLOOR, DIFFICULTY_CEIL);
  } else {
    // Fail (0) or slip (1). Reset stability toward the floor, item gets harder.
    stability = Math.max(STABILITY_FLOOR, base.stability * (grade === 1 ? 0.5 : 0.3));
    difficulty = clamp(D - 0.1, DIFFICULTY_FLOOR, DIFFICULTY_CEIL);
  }

  return {
    difficulty,
    stability: Math.max(stability, STABILITY_FLOOR),
    lastReviewAt: typeof now === "number" ? new Date(nowMs).toISOString() : now,
    reviewCount: (item.reviewCount || 0) + 1,
    lastGrade: grade,
  };
}

// computeNextReview(item, {desiredRetention, now}) -> {retrievability, nextReviewAtMs, daysUntilDue}
//
// The next review is scheduled for the moment retrievability would decay to `desiredRetention`:
//   R(t) = exp(-t / S) = desiredRetention  ->  t = -S * ln(desiredRetention)  days.
// A stricter (higher) desiredRetention yields a SHORTER interval. `retrievability` in the result is
// the modelled recall probability AT `now` (not at the due date), so callers can rank overdue items.
export function computeNextReview(item, { desiredRetention = 0.9, now } = {}) {
  const nowMs = toEpochMs(now, "computeNextReview");
  if (!(item && Number.isFinite(item.stability) && item.stability > 0)) {
    throw new Error("computeNextReview requires a positive `stability`; got a corrupt item state");
  }
  const dr = Number.isFinite(desiredRetention) ? clamp(desiredRetention, 0.5, 0.99) : 0.9;

  const daysUntilDue = -item.stability * Math.log(dr);
  const nextReviewAtMs = nowMs + Math.round(daysUntilDue * 86400000);
  const retrievability = clamp(retrievabilityAt(item, nowMs), 0, 1);

  return { retrievability, nextReviewAtMs, daysUntilDue };
}

// difficultyFromAccuracy(recentAttempts) -> number in [0.2, 1.0].
//
// Rolls a boolean correct/incorrect history into an item-hardness estimate where LOWER = harder.
// All-correct -> near 1.0 (easy); all-wrong -> near the 0.2 floor (hard). Empty history returns a
// neutral mid-range default. Accepts an array of booleans OR of {correct} attempt objects.
export function difficultyFromAccuracy(recentAttempts) {
  const arr = Array.isArray(recentAttempts) ? recentAttempts : [];
  if (arr.length === 0) return DEFAULT_DIFFICULTY;
  const correct = arr.filter((a) => (typeof a === "boolean" ? a : !!(a && a.correct))).length;
  const accuracy = correct / arr.length;
  // Map accuracy [0,1] onto difficulty [0.2,1.0].
  return clamp(DIFFICULTY_FLOOR + accuracy * (DIFFICULTY_CEIL - DIFFICULTY_FLOOR), DIFFICULTY_FLOOR, DIFFICULTY_CEIL);
}
