// Concept-map module — normalizes objectives so they may be a plain string (backward compatible
// with every existing tutor session/test) OR a richer {id, text, requires:[id]} descriptor, orders
// objectives into a valid learning path (topological sort over `requires`), and reports readiness
// (an objective unlocks only once every objective it requires is itself mastered).
//
// INTEGRITY: this module only ORDERS and GATES study objectives; it never grades or supplies an
// answer. readiness() reads mastery()'s own per-objective `ready` verdict (produced entirely from
// the operator's own attempts) — it adds no new judgment about correctness, only sequencing.

// normalizeObjectives(objectives) -> [{id, text, requires:[]}]
// A string objective `"foo"` normalizes to {id:"foo", text:"foo", requires:[]} — this is exactly
// the identity mastery()/schedule()/misconceptions() already read (session.attempts[].objective),
// so existing string-objective sessions are completely unaffected.
export function normalizeObjectives(objectives = []) {
  return objectives.map((o) => {
    if (typeof o === "string") {
      return { id: o, text: o, requires: [] };
    }
    return { id: o.id, text: o.text ?? o.id, requires: [...(o.requires || [])] };
  });
}

// learningPath(objectives) -> topologically ordered array of ids (a prerequisite always precedes
// every objective that requires it). Throws on a cycle (including a 1-node self-reference) rather
// than silently returning a partial or incorrect order.
export function learningPath(objectives) {
  const norm = normalizeObjectives(objectives);
  const byId = new Map(norm.map((o) => [o.id, o]));

  const VISITING = 1;
  const DONE = 2;
  const state = new Map();
  const order = [];

  function visit(id, chain) {
    const st = state.get(id);
    if (st === DONE) return;
    if (st === VISITING) {
      throw new Error(`learningPath: cycle detected in objective prerequisites: ${[...chain, id].join(" -> ")}`);
    }
    state.set(id, VISITING);
    const node = byId.get(id);
    const requires = node ? node.requires : [];
    for (const dep of requires) {
      visit(dep, [...chain, id]);
    }
    state.set(id, DONE);
    order.push(id);
  }

  for (const o of norm) {
    visit(o.id, []);
  }

  return order;
}

// readiness(session, objectives, masteryResult) -> [{objective, unlocked}]
// unlocked = true iff every id in that objective's `requires` is itself mastered, per
// masteryResult.perObjective[].ready (an objective with no requires is always unlocked).
export function readiness(session, objectives, masteryResult) {
  const norm = normalizeObjectives(objectives);
  const readyById = new Map((masteryResult?.perObjective || []).map((p) => [p.objective, !!p.ready]));

  return norm.map((o) => {
    const unlocked = o.requires.every((dep) => readyById.get(dep) === true);
    return { objective: o.id, unlocked };
  });
}
