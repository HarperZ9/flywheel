// SPDX-License-Identifier: AGPL-3.0-only
//
// Receipt behavior tests (SPEC s.17) for the Node.js implementation.
// Run with:  node --test impl/js/test_receipt.js   (from the repo root)
//
// These prove the verifier can FAIL: a receipt that always returned
// RECEIPT_VALID would be a certificate of authenticity, violating facts-only.

"use strict";

const test = require("node:test");
const assert = require("node:assert");
const crypto = require("node:crypto");
const emet = require("./emet.js");

const NOW = "2026-07-02T12:34:56Z";

// A verify --json envelope over a subject whose recorded digest is `digest`.
function verifyEnv(p, digest) {
  return {
    command: "verify",
    results: [{ got: digest, path: p, verdict: "MATCH", want: digest }],
    verdict: "MATCH",
  };
}

const DG = "a".repeat(64);

test("receipt has the stable format tag and pinned method", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  assert.strictEqual(r.format, "emet-witness-receipt/v1");
  assert.strictEqual(r.issued_at, NOW);
  assert.strictEqual(r.re_derivation_method, "hash");
});

test("receipt_id is the content address of the addressed body", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  assert.strictEqual(r.receipt_id, emet.receiptIdHash(r));
});

test("the witness block does NOT govern the content address (cross-impl parity)", () => {
  // SPEC s.17.2: witness is per-implementation producer identity, excluded from
  // the address so Python/Rust/Node re-derive the same id for the same input.
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  const original = r.receipt_id;
  r.witness = { implementation: "emet-python-reference", spec_version: "1.0.0", self_sha256: "dead".repeat(16) };
  assert.strictEqual(emet.receiptIdHash(r), original);
  assert.strictEqual(emet.checkReceipt(r, null, false, null).verdict, "RECEIPT_VALID");
});

test("subject digest and verdict record are carried faithfully", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  assert.strictEqual(r.subject[0].path, "a.txt");
  assert.strictEqual(r.subject[0].sha256, DG);
  assert.strictEqual(r.verdict_record[0].verdict, "MATCH");
  assert.strictEqual(r.verdict_record[0].command, "verify");
  assert.strictEqual(r.verdict_record[0].subject_index, 0);
});

test("witness pins spec_version and this implementation's identity", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  assert.strictEqual(r.witness.spec_version, "1.0.0");
  assert.strictEqual(r.witness.implementation, "emet-node-reference");
  assert.strictEqual(r.witness.self_sha256.length, 64);
});

test("an untouched receipt checks VALID", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  assert.strictEqual(emet.checkReceipt(r, null, false, null).verdict, "RECEIPT_VALID");
});

test("CAN-IT-FAIL: a flipped receipt_id is TAMPERED", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  const first = r.receipt_id[0] === "0" ? "1" : "0";
  r.receipt_id = first + r.receipt_id.slice(1);
  const res = emet.checkReceipt(r, null, false, null);
  assert.strictEqual(res.verdict, "RECEIPT_TAMPERED");
  assert.match(res.detail, /receipt_id/);
});

test("CAN-IT-FAIL: mutating a governed field (verdict) without recomputing the id is TAMPERED", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  r.verdict_record[0].verdict = "DRIFT"; // id left stale on purpose
  assert.strictEqual(emet.checkReceipt(r, null, false, null).verdict, "RECEIPT_TAMPERED");
});

test("CAN-IT-FAIL: a malformed / wrong-format receipt is UNVERIFIABLE, never a throw", () => {
  assert.strictEqual(emet.checkReceipt({ not: "a receipt" }, null, false, null).verdict, "RECEIPT_UNVERIFIABLE");
  assert.strictEqual(emet.checkReceipt({ format: "wrong" }, null, false, null).verdict, "RECEIPT_UNVERIFIABLE");
});

test("CAN-IT-FAIL: HMAC signature verifies with the correct key, fails with the wrong key, is UNVERIFIABLE with no key", () => {
  const keyA = Buffer.from("keyA");
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, keyA);
  assert.notStrictEqual(r.signature, null);
  assert.strictEqual(emet.checkReceipt(r, null, false, keyA).verdict, "RECEIPT_VALID");
  assert.strictEqual(emet.checkReceipt(r, null, false, Buffer.from("keyB")).verdict, "RECEIPT_TAMPERED");
  assert.strictEqual(emet.checkReceipt(r, null, false, null).verdict, "RECEIPT_UNVERIFIABLE");
});

test("an unsigned receipt has a null signature and verifies on the content address alone", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, null);
  assert.strictEqual(r.signature, null);
  assert.strictEqual(emet.checkReceipt(r, null, false, null).verdict, "RECEIPT_VALID");
});

test("the Node HMAC signature matches Node crypto over the addressed body", () => {
  // Sanity that signReceipt is a straight HMAC-SHA256 over the addressed body,
  // the same construction the Python reference and Rust port use.
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, Buffer.from("k"));
  const body = {};
  for (const k of Object.keys(r)) {
    if (k === "receipt_id" || k === "signature" || k === "witness") continue;
    body[k] = r[k];
  }
  const expected = crypto.createHmac("sha256", Buffer.from("k")).update(emet.canonicalJson(body), "utf8").digest("hex");
  assert.strictEqual(r.signature, expected);
});

test("no authority token appears anywhere in an emitted receipt", () => {
  const r = emet.emitReceipt(verifyEnv("a.txt", DG), null, NOW, Buffer.from("k"));
  const s = JSON.stringify(r);
  for (const tok of ["TRUSTED", "APPROVED", "SAFE", "AUTHORIZED", "PERMITTED", "VERIFIED_AUTHORITY"]) {
    assert.ok(!s.includes(tok), `authority token ${tok} leaked`);
  }
});
