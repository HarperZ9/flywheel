import { test } from "node:test";
import assert from "node:assert/strict";
import { run, resume } from "../src/runtime/runner.mjs";
import { loadWorkflow } from "../src/workflow/schema.mjs";
import { FakeDriver } from "../src/actuation/driver.mjs";
import "../src/adapters/fake.mjs";

const wf = loadWorkflow({
  adapter: "fake", course: "intro",
  steps: [
    { kind: "navigate", target: "course://intro" },
    { kind: "assess", label: "quiz 1" },
    { kind: "complete" },
  ],
});

test("run halts at the assess step and ledger is intact", async () => {
  const r = await run(wf, { driver: new FakeDriver() });
  assert.equal(r.status, "halted-assess");
  assert.equal(r.haltedAt, 1);
  assert.equal(r.ledger.verify().ok, true);
  const kinds = r.ledger.entries().map((e) => e.entry.kind);
  assert.deepEqual(kinds, ["step", "human-gate"]);
});

test("resume after the human does the assessment finishes the run", async () => {
  const driver = new FakeDriver();
  const first = await run(wf, { driver });
  const r = await resume(wf, { driver, ledger: first.ledger, haltedAt: first.haltedAt, allowIrreversible: true,
    humanAttest: { seq: 1, note: "operator completed quiz 1", at: "2026-06-30T00:00:00Z" } });
  assert.equal(r.status, "completed");
  assert.equal(r.completion.certId, "cert-fake-1");
  assert.equal(r.ledger.verify().ok, true);
  const kinds = r.ledger.entries().map((e) => e.entry.kind);
  assert.deepEqual(kinds, ["step", "human-gate", "human-assessment", "step", "completion"]);
});

test("an undeclared kind injected at runtime is denied (defense in depth)", async () => {
  const tampered = { ...wf, steps: [{ kind: "exfiltrate", id: 0 }] };
  const r = await run(tampered, { driver: new FakeDriver() });
  assert.equal(r.status, "denied");
});
