// Falsifiable integrity selftests — each proves a load-bearing invariant fails if weakened.
import { test } from "node:test";
import assert from "node:assert/strict";
import { decide } from "../src/accountability/gate.mjs";
import { run } from "../src/runtime/runner.mjs";
import { loadWorkflow } from "../src/workflow/schema.mjs";
import { FakeDriver } from "../src/actuation/driver.mjs";
import { Ledger } from "../src/accountability/ledger.mjs";
import "../src/adapters/fake.mjs";

const KINDS = new Set(["navigate", "assess", "complete"]);

test("INVARIANT 1: assess never resolves to allow, under any flag", () => {
  for (const flag of [false, true]) {
    assert.equal(decide({ kind: "assess", allowIrreversible: true }, { sealedKinds: KINDS, allowIrreversible: flag }).decision, "needs-human");
  }
});

test("INVARIANT 1 (e2e): a workflow with an assess step HALTS before actuating it", async () => {
  const wf = loadWorkflow({ adapter: "fake", course: "c", steps: [{ kind: "assess", label: "exam" }, { kind: "complete" }] });
  const driver = new FakeDriver();
  const r = await run(wf, { driver });
  assert.equal(r.status, "halted-assess");
  assert.equal(driver.actions.length, 0); // NOTHING was actuated
});

test("INVARIANT 2: an undeclared step kind is denied (no actuation)", async () => {
  const driver = new FakeDriver();
  const r = await run({ adapter: "fake", course: "c", seal: "x", steps: [{ kind: "wipe", id: 0 }] }, { driver });
  assert.equal(r.status, "denied");
  assert.equal(driver.actions.length, 0);
});

test("INVARIANT 3: a tampered ledger line is detected", () => {
  const l = new Ledger(); l.append({ kind: "step", n: 1 }); l.append({ kind: "step", n: 2 });
  l.entries()[0].entry.n = 42;
  assert.equal(l.verify().ok, false);
});
