import { test } from "node:test";
import assert from "node:assert/strict";
import { doctor } from "../src/doctor.mjs";
import { status } from "../src/status.mjs";
import { version } from "../src/index.mjs";

test("version is bumped to 2.3.0", () => {
  assert.equal(version, "2.3.0");
});

test("status advertises the telos render bridge and the aid invariant", () => {
  const s = status();
  assert.match(JSON.stringify(s.interop.telosEngine), /render|visuali/i);
  assert.ok(s.integrityInvariants.some((i) => /aid|visuali/i.test(i)));
});

test("doctor re-checks the aid invariants and stays MATCH", async () => {
  const d = await doctor();
  assert.equal(d.status, "MATCH");
  assert.ok(d.checks.some((c) => c.name === "telos.render_fail_closed" && c.status === "MATCH"));
  assert.ok(d.checks.some((c) => c.name === "receipt.aid_never_graded" && c.status === "MATCH"));
});
