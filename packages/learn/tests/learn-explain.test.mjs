import { test } from "node:test";
import assert from "node:assert/strict";
import { explanationThesis, gradeExplanation } from "../src/tutor/explain.mjs";

test("explanationThesis: builds a crucible thesis from the operator's OWN explanation text", () => {
  const explanation = "A hash chain detects tampering because each entry embeds the previous entry's digest. This holds for 100% of single-entry edits.";
  const thesis = explanationThesis(explanation);
  assert.equal(thesis.disposition, "publishable");
  assert.ok(Array.isArray(thesis.claims));
  assert.ok(thesis.claims.length >= 1);
  assert.ok(thesis.claims.every((c) => typeof c.text === "string" && "falsification" in c));
});

test("explanationThesis: title reflects that this is a self-explanation, not assisted authorship", () => {
  const thesis = explanationThesis("The engine reduces build time by 40% because of caching.");
  assert.match(thesis.title, /explanation/i);
});

test("explanationThesis: supplies nothing — claims carry no fabricated falsification/evidence", () => {
  const thesis = explanationThesis("The engine reduces build time by 40%.");
  for (const c of thesis.claims) {
    assert.equal(c.falsification, "");
  }
});

test("gradeExplanation: buckets MATCH claims as grounded", () => {
  const verdicts = [
    { text: "claim one", verdict: "MATCH" },
    { text: "claim two", verdict: "MATCH" },
  ];
  const result = gradeExplanation(verdicts);
  assert.equal(result.grounded.length, 2);
  assert.equal(result.shaky.length, 0);
  assert.equal(result.unverifiable.length, 0);
});

test("gradeExplanation: buckets DRIFT claims as shaky", () => {
  const verdicts = [{ text: "claim one", verdict: "DRIFT" }];
  const result = gradeExplanation(verdicts);
  assert.equal(result.shaky.length, 1);
  assert.equal(result.grounded.length, 0);
});

test("gradeExplanation: buckets UNVERIFIABLE claims as unverifiable", () => {
  const verdicts = [{ text: "claim one", verdict: "UNVERIFIABLE" }];
  const result = gradeExplanation(verdicts);
  assert.equal(result.unverifiable.length, 1);
});

test("gradeExplanation: mixed verdicts bucket correctly and summary reports counts", () => {
  const verdicts = [
    { text: "a", verdict: "MATCH" },
    { text: "b", verdict: "DRIFT" },
    { text: "c", verdict: "UNVERIFIABLE" },
    { text: "d", verdict: "MATCH" },
  ];
  const result = gradeExplanation(verdicts);
  assert.equal(result.grounded.length, 2);
  assert.equal(result.shaky.length, 1);
  assert.equal(result.unverifiable.length, 1);
  assert.match(result.summary, /2/);
  assert.match(result.summary, /1/);
});

test("gradeExplanation: empty verdicts -> all-empty buckets, no throw", () => {
  const result = gradeExplanation([]);
  assert.deepEqual(result.grounded, []);
  assert.deepEqual(result.shaky, []);
  assert.deepEqual(result.unverifiable, []);
  assert.equal(typeof result.summary, "string");
});

test("gradeExplanation: an unrecognized verdict string is treated as unverifiable (fail-closed, never silently dropped)", () => {
  const verdicts = [{ text: "weird", verdict: "SOMETHING_ELSE" }];
  const result = gradeExplanation(verdicts);
  assert.equal(result.unverifiable.length, 1);
  assert.equal(result.grounded.length, 0);
  assert.equal(result.shaky.length, 0);
});

test("gradeExplanation: checks the OPERATOR's own explanation vs THEIR OWN sources — supplies no correct answer or fix-it text", () => {
  const verdicts = [{ text: "The engine reduces build time by 40%.", verdict: "DRIFT" }];
  const result = gradeExplanation(verdicts);
  const serialized = JSON.stringify(result);
  assert.equal(Object.prototype.hasOwnProperty.call(result.shaky[0], "correctAnswer"), false);
  assert.equal(Object.prototype.hasOwnProperty.call(result.shaky[0], "fix"), false);
  assert.match(serialized, /40%/); // the operator's own claim text is preserved, not replaced
});

test("gradeExplanation: is a pure function of the verdicts array — never reaches into a render/visualization", () => {
  const verdicts = [{ text: "a", verdict: "MATCH" }];
  const before = JSON.stringify(verdicts);
  gradeExplanation(verdicts);
  assert.equal(JSON.stringify(verdicts), before, "must not mutate its input");
});
