import { test } from "node:test";
import assert from "node:assert/strict";
import { makeGenericAdapter } from "../src/adapters/generic.mjs";
import { getAdapter } from "../src/adapters/types.mjs";
import { FakeDriver } from "../src/actuation/driver.mjs";

test("default generic adapter is registered", () => {
  const a = getAdapter("generic");
  assert.equal(typeof a.captureCompletion, "function");
});

test("captureCompletion uses the driver and returns a cert id + payload", async () => {
  const a = makeGenericAdapter({ certId: "cert:demo", captureKind: "dom" });
  const driver = new FakeDriver();
  await driver.navigate("https://lms.test/course/done");
  const done = await a.captureCompletion(driver);
  assert.equal(done.certId, "cert:demo");
  assert.match(done.payload, /capture:dom/);
  assert.ok(driver.actions.includes("capture:dom"));
});

test("locateAssessment reports where graded content is, never answers it", async () => {
  const a = makeGenericAdapter({ assessmentSelector: "#quiz", assessmentLabel: "final exam" });
  const loc = await a.locateAssessment();
  assert.equal(loc.selector, "#quiz");
  assert.equal(loc.label, "final exam");
});
