import { test } from "node:test";
import assert from "node:assert/strict";
import { run } from "../src/runtime/runner.mjs";
import { loadWorkflow } from "../src/workflow/schema.mjs";
import { FakeDriver } from "../src/actuation/driver.mjs";
import { buildReceipt } from "../src/receipt/receipt.mjs";
import "../src/adapters/fake.mjs";

const submitWf = loadWorkflow({
  adapter: "fake", course: "c",
  steps: [{ kind: "navigate", target: "x" }, { kind: "submit", target: "#submit" }, { kind: "complete" }],
});

test("manual mode: a submit step HALTS for the operator", async () => {
  const d = new FakeDriver();
  const r = await run(submitWf, { driver: d, submissionMode: "manual" });
  assert.equal(r.status, "halted-needs-human");
  assert.equal(r.haltedAt, 1);
  assert.deepEqual(d.actions, ["navigate:x"]); // submit NOT performed
});

test("witnessed-auto mode: the engine performs the submit, witnessed with a submitted-state digest", async () => {
  const d = new FakeDriver();
  const r = await run(submitWf, { driver: d, submissionMode: "witnessed-auto" });
  assert.equal(r.status, "completed");
  assert.ok(d.actions.some((a) => /click:#submit/.test(a))); // submit performed via actuation
  const submitEntry = r.ledger.entries().map((e) => e.entry).find((e) => e.stepKind === "submit");
  assert.equal(submitEntry.submission, "witnessed-auto");
  assert.match(submitEntry.submittedStateDigest, /^sha256:[0-9a-f]{64}$/);
  const { json } = buildReceipt({ workflow: submitWf, ledger: r.ledger, completion: r.completion });
  assert.equal(json.witnessedAutoSubmissions.length, 1);
});

test("INVARIANT: assess still halts even in witnessed-auto mode (graded work never auto-submitted)", async () => {
  const wf = loadWorkflow({ adapter: "fake", course: "c", steps: [{ kind: "assess", label: "exam" }, { kind: "submit", target: "#s" }] });
  const d = new FakeDriver();
  const r = await run(wf, { driver: d, submissionMode: "witnessed-auto" });
  assert.equal(r.status, "halted-assess");
  assert.equal(d.actions.length, 0); // nothing actuated; the engine did not touch the graded step
});

test("manual submissions are recorded in the receipt as human-gated", async () => {
  const d = new FakeDriver();
  const r = await run(submitWf, { driver: d, submissionMode: "manual" });
  const { json } = buildReceipt({ workflow: submitWf, ledger: r.ledger, completion: r.completion });
  assert.equal(json.manualSubmissions.length, 1);
  assert.equal(json.witnessedAutoSubmissions.length, 0);
});
