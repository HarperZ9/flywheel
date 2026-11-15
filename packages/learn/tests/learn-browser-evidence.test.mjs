import { test } from "node:test";
import assert from "node:assert/strict";
import { run } from "../src/runtime/runner.mjs";
import { NativeDriver } from "../src/actuation/native-driver.mjs";
import { loadWorkflow } from "../src/workflow/schema.mjs";
import "../src/adapters/fake.mjs";

class EvidenceDriver {
  constructor() { this.actions = []; }
  async navigate(target) { this.actions.push("navigate:" + target); return { payload: "navigated:" + target }; }
  async click(target) { this.actions.push("click:" + target); return { payload: "clicked:" + target }; }
  async fill(target) { this.actions.push("fill:" + target); return { payload: "filled:" + target }; }
  async waitFor(target) { this.actions.push("waitFor:" + target); return { payload: "present:" + target }; }
  async capture(kind) {
    this.actions.push("capture:" + kind);
    return { kind, payload: "evidence:artifact", evidenceRef: "browser-evidence:fixture" };
  }
  async snapshot() { return { url: "https://example.com", fields: {} }; }
}

test("capture steps preserve browser evidence refs in the ledger", async () => {
  const wf = loadWorkflow({
    adapter: "fake",
    course: "browser",
    steps: [{ kind: "capture", capture: "evidence" }],
  });

  const result = await run(wf, { driver: new EvidenceDriver() });
  const entry = result.ledger.entries()[0].entry;

  assert.equal(result.status, "completed");
  assert.equal(entry.stepKind, "capture");
  assert.equal(entry.evidenceRef, "browser-evidence:fixture");
  assert.equal(result.ledger.verify().ok, true);
});

test("browser evidence support does not weaken assess human gate", async () => {
  const wf = loadWorkflow({
    adapter: "fake",
    course: "browser",
    steps: [{ kind: "assess", label: "exam" }],
  });
  const driver = new EvidenceDriver();

  const result = await run(wf, { driver, submissionMode: "witnessed-auto" });

  assert.equal(result.status, "halted-assess");
  assert.deepEqual(driver.actions, []);
});

test("native driver evidence capture returns a browser evidence ref", async () => {
  const driver = new NativeDriver({}, {
    async pageState() {
      return { url: "https://example.com", title: "Example", text: "body", html: "<html></html>" };
    },
  });

  const result = await driver.capture("evidence");

  assert.equal(result.kind, "evidence");
  assert.equal(result.payload, "browser-evidence:https://example.com");
  assert.equal(result.evidenceRef, "browser-evidence:https://example.com");
});
