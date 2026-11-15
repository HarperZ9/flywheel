import { test } from "node:test";
import assert from "node:assert/strict";
import { FakeDriver } from "../src/actuation/driver.mjs";
import { getAdapter } from "../src/adapters/types.mjs";
import "../src/adapters/fake.mjs"; // self-registers

test("FakeDriver records actions and returns payloads", async () => {
  const d = new FakeDriver();
  await d.navigate("course://intro");
  const cap = await d.capture("dom");
  assert.deepEqual(d.actions, ["navigate:course://intro", "capture:dom"]);
  assert.equal(typeof cap.payload, "string");
});

test("FakeAdapter is registered and reports completion", async () => {
  const a = getAdapter("fake");
  const done = await a.captureCompletion();
  assert.match(done.certId, /cert/);
});
