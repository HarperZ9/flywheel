import { test } from "node:test";
import assert from "node:assert/strict";
import { decide } from "../src/accountability/gate.mjs";

const KINDS = new Set(["navigate", "click", "fill", "submit", "assess", "complete"]);

test("declared logistics step is allowed", () => {
  assert.equal(decide({ kind: "navigate", target: "x" }, { sealedKinds: KINDS }).decision, "allow");
});
test("assess is ALWAYS needs-human, never allow", () => {
  assert.equal(decide({ kind: "assess", label: "q" }, { sealedKinds: KINDS }).decision, "needs-human");
  assert.equal(decide({ kind: "assess", allowIrreversible: true }, { sealedKinds: KINDS, allowIrreversible: true }).decision, "needs-human");
});
test("undeclared kind is denied", () => {
  assert.equal(decide({ kind: "drop_table" }, { sealedKinds: KINDS }).decision, "deny");
});
test("submit needs human unless allowIrreversible", () => {
  assert.equal(decide({ kind: "submit", target: "t" }, { sealedKinds: KINDS }).decision, "needs-human");
  assert.equal(decide({ kind: "submit", target: "t", allowIrreversible: true }, { sealedKinds: KINDS, allowIrreversible: true }).decision, "allow");
});
test("sensitive fill (credential/payment) halts for human", () => {
  assert.equal(decide({ kind: "fill", target: "pw", sensitive: true }, { sealedKinds: KINDS }).decision, "needs-human");
});
