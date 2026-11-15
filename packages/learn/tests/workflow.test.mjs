import { test } from "node:test";
import assert from "node:assert/strict";
import { loadWorkflow, STEP_KINDS } from "../src/workflow/schema.mjs";

test("valid workflow loads, ids and seal assigned", () => {
  const wf = loadWorkflow({
    adapter: "fake", course: "intro",
    steps: [{ kind: "navigate", target: "course://intro" }, { kind: "assess", label: "quiz 1" }],
  });
  assert.equal(wf.steps.length, 2);
  assert.equal(wf.steps[0].id, 0);
  assert.match(wf.seal, /^sha256:[0-9a-f]{64}$/);
});

test("unknown step kind is rejected", () => {
  assert.throws(() => loadWorkflow({ adapter: "fake", course: "c", steps: [{ kind: "hack" }] }), /unknown step kind/);
});

test("STEP_KINDS includes assess and excludes anything else", () => {
  assert.equal(STEP_KINDS.has("assess"), true);
  assert.equal(STEP_KINDS.has("nope"), false);
});
