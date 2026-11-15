import { test } from "node:test";
import assert from "node:assert/strict";
import {
  validateItem, validateItemSet, publicItem, diagnoseChoice, choiceSelfCheck, SET_SCHEMA,
} from "../src/tutor/choice.mjs";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { misconceptions } from "../src/tutor/misconception.mjs";

const item = () => ({
  id: "rinv-1", objective: "receipt-vs-verdict",
  prompt: "A rerun gives the same hash. What does that show?",
  choices: [
    { id: "same", text: "The same bytes came out" },
    { id: "right", text: "The output is right" },
    { id: "honest", text: "The author is honest" },
  ],
  answer: "same",
  misconceptions: { right: { leaf: "misrecruited.receipt_as_verdict", note: "A matching hash shows sameness. Rightness needs a criterion." } },
  source: { ref: "no-receipt-no-accept.html#4", quote: "Same bytes. Not yet right bytes." },
});

test("a well-formed item validates and its public form carries no key and no diagnosis map", () => {
  assert.equal(validateItem(item()).id, "rinv-1");
  const pub = publicItem(item());
  assert.deepEqual(Object.keys(pub).sort(), ["choices", "id", "objective", "prompt"]);
  assert.ok(!JSON.stringify(pub).includes("receipt_as_verdict"));
});

test("the keyed choice is correct and carries no leaf", () => {
  const d = diagnoseChoice(item(), "same");
  assert.equal(d.correct, true);
  assert.equal(d.leaf, null);
});

test("a wrong choice names its misconception and never names the key", () => {
  for (const choice of ["right", "honest"]) {
    const d = diagnoseChoice(item(), choice);
    const text = JSON.stringify(d);
    assert.equal(d.correct, false);
    assert.ok(!text.includes('"same"') && !text.includes("The same bytes came out"), text);
  }
  assert.equal(diagnoseChoice(item(), "right").leaf, "misrecruited.receipt_as_verdict");
  assert.equal(diagnoseChoice(item(), "right").top, "misrecruited");
  assert.equal(diagnoseChoice(item(), "honest").leaf, "missing.unexplained");
});

test("no choice, or a choice that is not on the item, reads as no attempt", () => {
  assert.equal(diagnoseChoice(item(), undefined).leaf, "missing.no_attempt");
  assert.equal(diagnoseChoice(item(), "made-up").leaf, "missing.no_attempt");
});

test("bad items are rejected with the reason", () => {
  const cases = [
    [{ answer: "nope" }, /answer must be/],
    [{ choices: [{ id: "same", text: "x" }] }, /2 to 6 choices/],
    [{ misconceptions: { same: { leaf: "misrecruited.x", note: "n" } } }, /keyed answer/],
    [{ misconceptions: { right: { leaf: "confused", note: "n" } } }, /leaf like/],
    [{ misconceptions: { right: { leaf: "slip.x", note: "" } } }, /needs a note/],
    [{ prompt: "" }, /no prompt/],
    [{ id: "has space" }, /needs an id/],
  ];
  for (const [patch, why] of cases) assert.throws(() => validateItem({ ...item(), ...patch }), why);
});

test("an item set needs its schema and unique ids", () => {
  assert.ok(validateItemSet({ schema: SET_SCHEMA, topic: "t", items: [item()] }));
  assert.throws(() => validateItemSet({ schema: "x", items: [item()] }), /schema/);
  assert.throws(() => validateItemSet({ schema: SET_SCHEMA, items: [item(), item()] }), /used twice/);
});

test("a recorded choice misconception is counted by misconceptions()", () => {
  const s = newSession({ topic: "t", objectives: ["receipt-vs-verdict"] });
  const d = diagnoseChoice(item(), "right");
  recordAttempt(s, { objective: "receipt-vs-verdict", prompt: item().prompt, answer: "right", correct: d.correct, misconception: d.leaf });
  recordAttempt(s, { objective: "receipt-vs-verdict", prompt: item().prompt, answer: "same", correct: true });
  const [row] = misconceptions(s);
  assert.deepEqual(row.diagnoses, { "misrecruited.receipt_as_verdict": 1 });
});

test("the doctor self-check passes on the clean probe", () => {
  assert.equal(choiceSelfCheck(), true);
});
