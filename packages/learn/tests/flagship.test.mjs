import { test } from "node:test";
import assert from "node:assert/strict";
import { doctor } from "../src/doctor.mjs";
import { status } from "../src/status.mjs";
import { getAdapter } from "../src/adapters/types.mjs";
import { LMS_PLATFORMS } from "../src/adapters/lms.mjs";
import { run, resume } from "../src/runtime/runner.mjs";
import { loadWorkflow } from "../src/workflow/schema.mjs";
import { FakeDriver } from "../src/actuation/driver.mjs";
import { buildReceipt } from "../src/receipt/receipt.mjs";
import { version } from "../src/index.mjs";
import "../src/adapters/fake.mjs";

test("doctor exercises every invariant and returns MATCH", async () => {
  const d = await doctor();
  assert.equal(d.status, "MATCH");
  assert.equal(d.version, version);
  assert.match(version, /^\d+\.\d+\.\d+$/);
  assert.ok(d.checks.length >= 4);
  assert.ok(d.checks.every((c) => c.status === "MATCH"));
});

test("status reports version + integrity invariants + html receipt format", () => {
  const s = status();
  assert.equal(s.version, version);
  assert.ok(s.integrityInvariants.some((i) => /assess/i.test(i)));
  assert.ok(s.receiptFormats.includes("html"));
});

test("LMS adapter pack is registered (coursera/udemy/linkedin-learning/edx/credly)", () => {
  for (const p of ["coursera", "udemy", "linkedin-learning", "edx", "credly"]) {
    assert.ok(LMS_PLATFORMS.includes(p));
    assert.equal(typeof getAdapter(p).captureCompletion, "function");
  }
});

test("receipt now emits html with the logistics/assessment split", async () => {
  const wf = loadWorkflow({ adapter: "fake", course: "intro",
    steps: [{ kind: "navigate", target: "x" }, { kind: "assess", label: "quiz" }, { kind: "complete" }] });
  const driver = new FakeDriver();
  const first = await run(wf, { driver });
  const done = await resume(wf, { driver, ledger: first.ledger, haltedAt: first.haltedAt, allowIrreversible: true,
    humanAttest: { seq: 1, note: "did quiz", at: "2026-06-30T00:00:00Z" } });
  const { html } = buildReceipt({ workflow: wf, ledger: done.ledger, completion: done.completion });
  assert.match(html, /<!doctype html>/i);
  assert.match(html, /Human assessments/);
  assert.match(html, /did quiz/);
});
