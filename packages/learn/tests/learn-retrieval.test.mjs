import { test } from "node:test";
import assert from "node:assert/strict";
import { assist } from "../src/assist/assist.mjs";
import { clozePrompts, interleave } from "../src/tutor/retrieval.mjs";

test("clozePrompts: turns the operator's OWN assist claims into cloze/recall prompts, each carrying its source", () => {
  const draft = "My compiler reduces build time by 40%. See https://github.com/HarperZ9/buildlang for the code.";
  const a = assist(draft);
  const prompts = clozePrompts(a, { objective: "compilers" });
  assert.ok(prompts.length >= 1);
  for (const p of prompts) {
    assert.equal(p.objective, "compilers");
    assert.match(p.prompt, /___/); // a blank must be present
    assert.ok(typeof p.source === "string");
  }
});

test("clozePrompts: blanks a number when the claim contains one (salient-term heuristic)", () => {
  const a = assist("My compiler reduces build time by 40%.");
  const [p] = clozePrompts(a);
  assert.match(p.prompt, /40%/.test(p.prompt) ? /___/ : /___/); // sanity: blank exists
  assert.ok(!p.prompt.includes("40%"), "the numeric term itself must be blanked out, not left in the prompt");
});

test("clozePrompts: never includes an 'answer' field — it is a recall PROMPT, not a graded answer key", () => {
  const a = assist("The compiler reduces build time by 40%. It is fast.");
  const prompts = clozePrompts(a);
  for (const p of prompts) {
    assert.equal(Object.prototype.hasOwnProperty.call(p, "answer"), false);
    assert.equal(Object.prototype.hasOwnProperty.call(p, "solution"), false);
  }
});

test("clozePrompts: default objective is null when none is given", () => {
  const a = assist("The engine handles 12 requests per second.");
  const [p] = clozePrompts(a);
  assert.equal(p.objective, null);
});

test("clozePrompts: source is the assistResult's own inputSha256 when no URL sources exist", () => {
  const a = assist("The engine handles 12 requests per second.");
  const [p] = clozePrompts(a);
  assert.match(p.source, /^sha256:[0-9a-f]{64}$/);
});

test("clozePrompts: source prefers a cited URL when the assist result has sources", () => {
  const draft = "The engine handles 12 requests per second. See https://example.com/docs for details.";
  const a = assist(draft);
  const prompts = clozePrompts(a);
  assert.ok(prompts.some((p) => p.source === "https://example.com/docs"));
});

test("clozePrompts: empty claims -> empty array, never throws", () => {
  const a = assist("No checkable claims here at all just prose.");
  assert.deepEqual(clozePrompts(a), []);
});

test("interleave: deterministic — same seed always produces the same order", () => {
  const objectives = ["a", "b", "c", "d", "e"];
  const first = interleave(objectives, { seed: 42 });
  const second = interleave(objectives, { seed: 42 });
  assert.deepEqual(first, second);
});

test("interleave: different seeds can produce different orders (no Math.random — must still vary by seed)", () => {
  const objectives = ["a", "b", "c", "d", "e", "f", "g", "h"];
  const byOne = interleave(objectives, { seed: 1 });
  const byTwo = interleave(objectives, { seed: 2 });
  assert.notDeepEqual(byOne, byTwo);
});

test("interleave: output is a permutation of the input (same elements, mixed order)", () => {
  const objectives = ["x", "y", "z"];
  const result = interleave(objectives, { seed: 7 });
  assert.deepEqual([...result].sort(), [...objectives].sort());
  assert.equal(result.length, objectives.length);
});

test("interleave: mixes objectives rather than preserving contiguous runs (interleaved, not grouped)", () => {
  // Feed a list already grouped in runs by objective identity via repeated entries and check
  // that a large-enough shuffle does not just return the identity order.
  const objectives = ["a", "a", "b", "b", "c", "c"];
  const result = interleave(objectives, { seed: 99 });
  assert.notDeepEqual(result, objectives);
});

test("interleave: default seed is deterministic too (no seed provided still reproducible)", () => {
  const objectives = ["a", "b", "c"];
  assert.deepEqual(interleave(objectives), interleave(objectives));
});

test("interleave: empty input -> empty output", () => {
  assert.deepEqual(interleave([]), []);
});

test("interleave: single element -> unchanged", () => {
  assert.deepEqual(interleave(["only"], { seed: 5 }), ["only"]);
});
