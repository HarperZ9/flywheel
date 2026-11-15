import { test } from "node:test";
import assert from "node:assert/strict";
import { run, resume } from "../src/runtime/runner.mjs";
import { loadWorkflow } from "../src/workflow/schema.mjs";
import { FakeDriver } from "../src/actuation/driver.mjs";
import { buildReceipt } from "../src/receipt/receipt.mjs";
import "../src/adapters/fake.mjs";

test("receipt separates automated logistics from human assessment", async () => {
  const wf = loadWorkflow({ adapter: "fake", course: "intro",
    steps: [{ kind: "navigate", target: "x" }, { kind: "assess", label: "quiz" }, { kind: "complete" }] });
  const driver = new FakeDriver();
  const first = await run(wf, { driver });
  const done = await resume(wf, { driver, ledger: first.ledger, haltedAt: first.haltedAt, allowIrreversible: true,
    humanAttest: { seq: 1, note: "did quiz", at: "2026-06-30T00:00:00Z" } });
  const { json, markdown } = buildReceipt({ workflow: wf, ledger: done.ledger, completion: done.completion });
  assert.equal(json.verified, true);
  assert.equal(json.automatedLogistics, 2);          // navigate + complete
  assert.equal(json.humanAssessments.length, 1);     // the quiz
  assert.equal(json.certId, "cert-fake-1");
  assert.match(markdown, /Human assessment/i);
  assert.match(markdown, /quiz/);
});
