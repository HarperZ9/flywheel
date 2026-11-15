// Per-item scheduling state manager — owns session.itemState, the FSRS-class scheduling hint.
//
// INTEGRITY (the load-bearing boundary):
//   - session.attempts is the GRADED, witnessed source of truth (the ledger hash-chains it).
//   - session.itemState is a DERIVED scheduling hint. It is NOT authoritative and NEVER feeds the
//     mastery verdict. recordAttemptWithGrade() here mutates itemState ONLY; it deliberately does
//     not touch session.attempts (the tutor layer's recordAttemptWithGrade does both, in order).
//   - If itemState corrupts or is deleted, scheduling self-heals: initializeItem() clamps invalid
//     values and a missing entry is re-created on demand from sensible defaults. A corrupt hint can
//     therefore never ship a nonsensical interval (negative days / infinities) to a learner.
//   - No Date.now(): `now` is always passed in explicitly, so rankings are deterministic in tests.
//
// itemState shape (mirrors the session.visualizations "side-channel" pattern):
//   { "objective-id": { difficulty, stability, lastReviewAt, reviewCount, lastGrade, createdAt } }
import { initializeItem, gradeAttempt, computeNextReview } from "./fsrs.mjs";

function idOf(objective) {
  return typeof objective === "string" ? objective : (objective && objective.id);
}

function ensureItemState(session) {
  if (!session.itemState) session.itemState = {};
  return session.itemState;
}

// createdAt is derived from the first-seen instant. Since this module never calls Date.now(), the
// createdAt for an item first touched via recordAttemptWithGrade is anchored to that graded `now`;
// items created up-front by initializeItems (which has no `now`) get a null createdAt until first
// graded, keeping the module wall-clock-free.
function freshItem(now = null) {
  return { ...initializeItem(), createdAt: now };
}

// initializeItems(session, objectives) -> session (populates session.itemState for each objective).
// Idempotent: an objective that already has item state is left untouched.
export function initializeItems(session, objectives = []) {
  const state = ensureItemState(session);
  for (const o of objectives) {
    const id = idOf(o);
    if (!id) continue;
    if (!state[id]) state[id] = freshItem(null);
  }
  return session;
}

// recordAttemptWithGrade(session, {objective, grade, now}) -> session.
// Updates session.itemState[objective] via the FSRS grade step. Mutates itemState ONLY — it does
// NOT append to session.attempts (that stays the witnessed graded log, updated by the tutor layer).
// A missing item is auto-initialized rather than silently dropped.
export function recordAttemptWithGrade(session, { objective, grade, now } = {}) {
  const id = idOf(objective);
  if (!id) throw new Error("recordAttemptWithGrade requires an `objective`");
  if (grade === undefined || grade === null) {
    throw new Error("recordAttemptWithGrade requires a `grade` in [0,4]");
  }
  const state = ensureItemState(session);
  if (!state[id]) state[id] = freshItem(typeof now === "number" ? new Date(now).toISOString() : now || null);

  // Heal-before-grade: the write path gets the SAME self-heal guarantee as the read/ranking path.
  // gradeAttempt divides by item.stability when modelling retrievability, so a corrupt stored value
  // (NaN / Infinity / negative / out-of-range difficulty) must be clamped BEFORE it feeds the grade
  // math — otherwise a nonsensical (e.g. NaN) stability would be persisted and later ship a bad
  // interval to the learner. healItem() clamps in place and returns the sanitized entry.
  const prev = healItem(session, id);
  const updated = gradeAttempt(prev, { grade, now });
  state[id] = { ...prev, ...updated, createdAt: prev.createdAt ?? (typeof now === "number" ? new Date(now).toISOString() : now) };
  return session;
}

// healItem(session, id) -> a valid item-state object for `id`, re-initializing/clamping if the
// stored state is missing or corrupt. Writes the healed state back so corruption is fixed in place.
function isCorrupt(cur) {
  return (
    !cur ||
    !Number.isFinite(cur.stability) || cur.stability <= 0 ||
    !Number.isFinite(cur.difficulty) || cur.difficulty < 0.2 || cur.difficulty > 1.0
  );
}

function healItem(session, id) {
  const state = ensureItemState(session);
  const cur = state[id];
  if (isCorrupt(cur)) {
    const healed = { ...freshItem(cur && cur.createdAt ? cur.createdAt : null), ...(cur || {}) };
    // initializeItem clamps difficulty into [0.2,1.0] and stability to a positive floor.
    const norm = initializeItem({ difficulty: healed.difficulty, stability: healed.stability });
    state[id] = { ...healed, difficulty: norm.difficulty, stability: norm.stability };
  }
  return state[id];
}

function itemIds(session) {
  const state = ensureItemState(session);
  const fromState = Object.keys(state);
  if (fromState.length) return fromState;
  // Fall back to the session's declared objectives so a fresh (ungraded) session still ranks.
  return (session.objectives || []).map(idOf).filter(Boolean);
}

// sortByRetrievability(session, {now, desiredRetention}) -> items ranked most-at-risk first.
// Each entry: {objective, retrievability, daysUntilDue}. Lowest retrievability (most likely to be
// forgotten) comes first. Ties break by objective id for a stable, reproducible order.
export function sortByRetrievability(session, { now, desiredRetention = 0.9 } = {}) {
  const ids = itemIds(session);
  const rows = ids.map((id) => {
    const item = healItem(session, id);
    const { retrievability, daysUntilDue } = computeNextReview(item, { desiredRetention, now });
    return { objective: id, retrievability, daysUntilDue };
  });
  rows.sort((a, b) => {
    if (a.retrievability !== b.retrievability) return a.retrievability - b.retrievability;
    return a.objective < b.objective ? -1 : a.objective > b.objective ? 1 : 0;
  });
  return rows;
}

// selectNextItem(session, {now, desiredRetention}) -> the single most-at-risk item, or null if none.
export function selectNextItem(session, { now, desiredRetention = 0.9 } = {}) {
  const ranked = sortByRetrievability(session, { now, desiredRetention });
  return ranked.length ? ranked[0] : null;
}
