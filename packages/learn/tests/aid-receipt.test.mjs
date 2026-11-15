import { test } from "node:test";
import assert from "node:assert/strict";
import { Ledger } from "../src/accountability/ledger.mjs";
import { buildReceipt } from "../src/receipt/receipt.mjs";
import { toAidLedgerEntry } from "../src/interop/telos.mjs";

function ledgerWith(...entries) {
  const l = new Ledger();
  for (const e of entries) l.append(e);
  return l;
}

test("an aid render lands in aidVisualizations and in NO graded channel", () => {
  const aid = toAidLedgerEntry(
    { selected_profile: "canvas2d-receipt-renderer", scene_spec_hash: "sha256:a", result_hash: "sha256:b", verdict: "MATCH" },
    { concept: "y = x^2", seq: 0 }
  );
  const ledger = ledgerWith(aid);
  const { json } = buildReceipt({ workflow: { course: "c", seal: "s" }, ledger, completion: null });

  assert.equal(json.aidVisualizations.length, 1);
  assert.equal(json.aidVisualizations[0].concept, "y = x^2");
  assert.equal(json.aidVisualizations[0].verdict, "MATCH");
  // Structural exclusion from graded work (integrity invariant 1 & 2):
  assert.equal(json.humanAssessments.length, 0);
  assert.equal(json.witnessedAutoSubmissions.length, 0);
  assert.equal(json.manualSubmissions.length, 0);
});

test("aidVisualizations is empty for a normal run with no renders", () => {
  const ledger = ledgerWith({ kind: "step", seq: 0 }, { kind: "human-assessment", seq: 1, note: "quiz", at: "t" });
  const { json } = buildReceipt({ workflow: { course: "c", seal: "s" }, ledger, completion: null });
  assert.equal(json.aidVisualizations.length, 0);
  assert.equal(json.humanAssessments.length, 1); // real graded work still recorded
});
