// Misconception diagnosis: each leaf is reached by its own answer and a one-change mutation of
// that answer leaves the leaf, so a rule that matches everything cannot pass.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { diagnose, parsePrompt, parseAnswer } from "../src/tutor/diagnose.mjs";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { misconceptions } from "../src/tutor/misconception.mjs";
import { run, derange } from "../scripts/diagnosis-bench.mjs";

const leaf = (prompt, answer) => diagnose({ prompt, answer }).leaf;

test("no attempt: blank and 'idk' are missing, a number is not", () => {
  assert.equal(leaf("47 + 38", "idk"), "missing.no_attempt");
  assert.equal(leaf("47 + 38", ""), "missing.no_attempt");
  assert.notEqual(leaf("47 + 38", "50"), "missing.no_attempt");
});

test("fraction add-across: (a+c)/(b+d) is caught, a different fraction is not", () => {
  assert.equal(leaf("1/3 + 1/4 = ?", "2/7"), "misrecruited.fraction_add_across");
  assert.notEqual(leaf("1/3 + 1/4 = ?", "2/9"), "misrecruited.fraction_add_across");
});

test("smaller from larger: column-wise absolute difference, and not when it is right", () => {
  assert.equal(leaf("What is 507 - 248?", "341"), "misrecruited.smaller_from_larger");
  assert.equal(leaf("What is 507 - 248?", "259"), null);
  assert.notEqual(leaf("What is 507 - 248?", "351"), "misrecruited.smaller_from_larger");
});

test("no carry: dropped carries are caught, a correct carry is not wrong", () => {
  assert.equal(leaf("47 + 38", "75"), "misrecruited.no_carry");
  assert.equal(leaf("47 + 38", "85"), null);
});

test("wrong operation: adding on a multiplication question, and not for a random number", () => {
  assert.equal(leaf("Compute 36 x 7", "43"), "misrecruited.wrong_operation");
  assert.equal(leaf("1/2 + 1/3", "1/6"), "misrecruited.wrong_operation");
  assert.equal(leaf("12 + 30", "18"), "misrecruited.wrong_operation");   // subtracted b - a
  assert.equal(leaf("Compute 36 x 7", "41"), "missing.unexplained");
});

test("slip: one digit off or adjacent swap, but two digits off is unexplained", () => {
  assert.equal(leaf("36 * 7", "262"), "slip.one_digit");
  assert.equal(leaf("36 * 7", "225"), "slip.one_digit");
  assert.equal(leaf("36 * 7", "263"), "missing.unexplained");
});

test("path records every question asked, in order, ending at the hit", () => {
  const d = diagnose({ prompt: "36 * 7", answer: "262" });
  assert.deepEqual(d.path.map((s) => s.answer), [false, false, false, false, false, true]);
  assert.equal(d.top, "slip");
  assert.equal(diagnose({ prompt: "36 * 7", answer: "43" }).path.at(-1).question,
    "Is it what another operation gives on the same numbers?");
});

test("diagnosis never carries the correct answer", () => {
  const d = diagnose({ prompt: "36 * 7", answer: "262" });
  assert.ok(!JSON.stringify(d).includes("252"));
});

test("parsers: prompt kinds, answer kinds, and non-arithmetic prompts", () => {
  assert.deepEqual(parsePrompt("12 x 3"), { kind: "whole", op: "*", a: 12, b: 3 });
  assert.equal(parsePrompt("explain recursion"), null);
  assert.deepEqual(parseAnswer("1,204"), { kind: "whole", v: 1204 });
  assert.equal(parseAnswer("about ten"), null);
  assert.equal(leaf("explain recursion", "a function"), null);
});

test("misconceptions(): diagnoses counted per objective, absent when nothing is diagnosable", () => {
  const s = newSession({ topic: "t", objectives: ["add", "words"] });
  recordAttempt(s, { objective: "add", prompt: "47 + 38", answer: "75", correct: false });
  recordAttempt(s, { objective: "add", prompt: "26 + 19", answer: "35", correct: false });
  recordAttempt(s, { objective: "words", prompt: "define lemma", answer: "a word", correct: false });
  const out = Object.fromEntries(misconceptions(s).map((m) => [m.objective, m]));
  assert.deepEqual(out.add.diagnoses, { "misrecruited.no_carry": 2 });
  assert.equal(out.words.diagnoses, undefined);
});

test("bench reproduces the reported result and the control collapses", () => {
  const items = JSON.parse(readFileSync(new URL("./fixtures/learn_diagnosis_labels.json", import.meta.url), "utf8")).items;
  const r = run(items);
  assert.deepEqual(r.bar, { D1: true, D2: true, control: true });
  assert.equal(r.test.n, 50);
  assert.ok(r.control.leaf_agreement < 0.5);
  assert.deepEqual(run(items), r);
});

test("derangement moves every index", () => {
  const p = derange(50, 7);
  assert.ok(p.every((v, i) => v !== i));
  assert.deepEqual([...p].sort((a, b) => a - b), [...Array(50).keys()]);
});
