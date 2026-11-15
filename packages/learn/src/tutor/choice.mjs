// Choice items: short recall questions with a keyed answer and a named misconception per wrong
// choice. A page shows publicItem(item) before the attempt, then diagnoseChoice(item, choiceId)
// says whether the attempt was right and, when it was not, which misconception the choice matches.
//
// Item format "learn-choice/1" (docs/CHOICE-ITEMS.md):
//   { id, objective?, prompt, choices: [{ id, text }], answer: "<choice id>",
//     misconceptions: { "<wrong choice id>": { leaf: "misrecruited.<name>", note } },
//     source?: { ref, quote } }
// A set is { schema: "learn-items/1", topic, items: [...] }.
//
// INTEGRITY: diagnoseChoice() names a cause and never carries the keyed choice, its id or its
// text, so a wrong attempt learns why it was wrong without being handed the answer. Leaves use
// the same top levels as the arithmetic tree (diagnose.mjs): missing, misrecruited, slip.
// This is practice the operator answers; it never answers a graded assessment.

export const ITEM_SCHEMA = "learn-choice/1";
export const SET_SCHEMA = "learn-items/1";
export const TOP_LEVELS = Object.freeze(["missing", "misrecruited", "slip"]);
const LEAF = /^(missing|misrecruited|slip)\.[a-z0-9_]{1,48}$/;
const ID = /^[A-Za-z0-9._-]{1,64}$/;
const NO_ATTEMPT = new Set(["", null, undefined]);

function fail(item, why) {
  throw new Error(`choice item ${item && item.id ? item.id : "(no id)"}: ${why}`);
}

function checkChoices(item) {
  if (!Array.isArray(item.choices) || item.choices.length < 2 || item.choices.length > 6) {
    fail(item, "needs 2 to 6 choices");
  }
  const ids = new Set();
  for (const c of item.choices) {
    if (!c || !ID.test(String(c.id || ""))) fail(item, "every choice needs an id of letters, digits, dot, dash or underscore");
    if (typeof c.text !== "string" || !c.text.trim()) fail(item, `choice ${c.id} has no text`);
    if (ids.has(c.id)) fail(item, `choice id ${c.id} is used twice`);
    ids.add(c.id);
  }
  return ids;
}

function checkMisconceptions(item, ids) {
  const map = item.misconceptions || {};
  if (typeof map !== "object" || Array.isArray(map)) fail(item, "misconceptions must be an object keyed by choice id");
  for (const [choiceId, m] of Object.entries(map)) {
    if (!ids.has(choiceId)) fail(item, `misconception keyed on unknown choice ${choiceId}`);
    if (choiceId === item.answer) fail(item, "the keyed answer cannot carry a misconception");
    if (!m || !LEAF.test(String(m.leaf || ""))) fail(item, `misconception for ${choiceId} needs a leaf like misrecruited.name`);
    if (typeof m.note !== "string" || !m.note.trim()) fail(item, `misconception for ${choiceId} needs a note`);
  }
}

// validateItem(item) -> item, or throws naming the first problem.
export function validateItem(item) {
  if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error("choice item: not an object");
  if (!ID.test(String(item.id || ""))) fail(item, "needs an id of letters, digits, dot, dash or underscore");
  if (typeof item.prompt !== "string" || !item.prompt.trim()) fail(item, "has no prompt");
  const ids = checkChoices(item);
  if (!ids.has(item.answer)) fail(item, "answer must be the id of one of its choices");
  checkMisconceptions(item, ids);
  if (item.source !== undefined && (typeof item.source !== "object" || typeof item.source.ref !== "string")) {
    fail(item, "source must be { ref, quote }");
  }
  return item;
}

// validateItemSet(set) -> set, or throws. Item ids must be unique across the set.
export function validateItemSet(set) {
  if (!set || set.schema !== SET_SCHEMA) throw new Error(`item set: schema must be ${SET_SCHEMA}`);
  if (!Array.isArray(set.items) || !set.items.length) throw new Error("item set: no items");
  const seen = new Set();
  for (const item of set.items) {
    validateItem(item);
    if (seen.has(item.id)) throw new Error(`item set: item id ${item.id} is used twice`);
    seen.add(item.id);
  }
  return set;
}

// What a page may show before the attempt: the prompt and the choices, no key, no diagnosis map.
export function publicItem(item) {
  validateItem(item);
  return {
    id: item.id,
    objective: item.objective || item.id,
    prompt: item.prompt,
    choices: item.choices.map((c) => ({ id: c.id, text: c.text })),
  };
}

// diagnoseChoice(item, choiceId) -> { correct, leaf, top, note, path }
// correct is true only for the keyed choice. A wrong choice gets the leaf its author named, or
// missing.unexplained; no choice gets missing.no_attempt. The result never names the key.
export function diagnoseChoice(item, choiceId) {
  validateItem(item);
  const blank = NO_ATTEMPT.has(choiceId) || !item.choices.some((c) => c.id === choiceId);
  const path = [{ question: "Was no answer given?", answer: blank }];
  if (blank) return { correct: false, leaf: "missing.no_attempt", top: "missing", note: "", path };
  const keyed = choiceId === item.answer;
  path.push({ question: "Is it the keyed choice?", answer: keyed });
  if (keyed) return { correct: true, leaf: null, top: null, note: "", path };
  const m = (item.misconceptions || {})[choiceId];
  path.push({ question: "Does the choice match a named misconception?", answer: Boolean(m) });
  if (!m) return { correct: false, leaf: "missing.unexplained", top: "missing", note: "", path };
  return { correct: false, leaf: m.leaf, top: m.leaf.split(".")[0], note: m.note, path };
}

// The doctor's falsifiable check: a clean item diagnoses every wrong choice without leaking the
// key, and a known-bad item (a misconception keyed on the answer) is rejected.
export function choiceSelfCheck() {
  const item = {
    id: "probe", prompt: "A rerun gives the same hash. What does that show?", answer: "same",
    choices: [{ id: "same", text: "The same bytes came out" }, { id: "right", text: "The output is right" }],
    misconceptions: { right: { leaf: "misrecruited.receipt_as_verdict", note: "A hash shows sameness, not correctness." } },
  };
  const wrong = diagnoseChoice(item, "right");
  const text = JSON.stringify(wrong);
  const clean = wrong.correct === false && wrong.leaf === "misrecruited.receipt_as_verdict"
    && !text.includes("\"same\"") && !text.includes("The same bytes came out");
  let rejected = false;
  try { validateItem({ ...item, misconceptions: { same: { leaf: "slip.x", note: "n" } } }); } catch { rejected = true; }
  return clean && rejected && !("answer" in publicItem(item));
}
