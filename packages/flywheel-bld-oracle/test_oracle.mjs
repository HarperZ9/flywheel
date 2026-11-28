// SPDX-License-Identifier: MIT
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const WASM_PATH = join(HERE, "oracle.wasm");

function refFnv1aByte(acc, b) {
  return Number(((BigInt(acc) ^ (BigInt(b) & 0xffn)) * 16777619n) & 0xffffffffn);
}

function refFnv1aStep(acc, word) {
  let h = refFnv1aByte(acc, word & 0xff);
  h = refFnv1aByte(h, (word >>> 8) & 0xff);
  h = refFnv1aByte(h, (word >>> 16) & 0xff);
  return refFnv1aByte(h, (word >>> 24) & 0xff);
}

function refMerkleCombine(left, right) {
  let h = refFnv1aByte(2166136261, 1);
  h = refFnv1aStep(h, left);
  return refFnv1aStep(h, right);
}

async function loadOracle() {
  const bytes = readFileSync(WASM_PATH);
  assert.deepEqual([...bytes.subarray(0, 4)], [0x00, 0x61, 0x73, 0x6d]);
  const mod = await WebAssembly.compile(bytes);
  const env = {};
  for (const imp of WebAssembly.Module.imports(mod)) {
    assert.equal(imp.module, "env", `unexpected import module: ${imp.module}`);
    assert.match(imp.name, /^print_/, `unexpected non-print host import: ${imp.name}`);
    env[imp.name] = () => {};
  }
  const instance = await WebAssembly.instantiate(mod, { env });
  return instance.exports;
}

test("known-answer FNV-1a receipt and Merkle accumulator match JS reference", async () => {
  const ex = await loadOracle();
  assert.equal(ex.fnv1a_init(), 2166136261n);
  const leafA = ex.fnv1a_step(ex.fnv1a_init(), 42n);
  const leafB = ex.fnv1a_step(ex.fnv1a_init(), 99n);
  const expA = BigInt(refFnv1aStep(2166136261, 42));
  const expB = BigInt(refFnv1aStep(2166136261, 99));
  assert.equal(leafA, expA);
  assert.equal(leafB, expB);
  const root = ex.merkle_combine(leafA, leafB);
  const expRoot = BigInt(refMerkleCombine(Number(expA), Number(expB)));
  assert.equal(root, expRoot);
  assert.equal(ex.verify_receipt_digest(root, expRoot), 1);
  assert.equal(ex.main(), 0);
});

test("tolerance and control-gap validator enforce exact bounds", async () => {
  const ex = await loadOracle();
  assert.equal(ex.check_tolerance(1e-13, 1e-10), 1);
  assert.equal(ex.check_tolerance(1e-9, 1e-10), -201);
  assert.equal(ex.check_tolerance(-0.01, 0.1), -201);
  assert.equal(ex.check_control_gap(0.2, 0.75, 0.3), 1);
  assert.equal(ex.check_control_gap(0.5, 0.55, 0.2), -202);
  assert.equal(ex.check_control_gap(0.2, 0.9, 0.0), -202);
});

test("planted failing controls are rejected fail-closed", async () => {
  const ex = await loadOracle();
  const root = ex.merkle_combine(
    ex.fnv1a_step(ex.fnv1a_init(), 1001n),
    ex.fnv1a_step(ex.fnv1a_init(), 2002n),
  );
  const tolOk = ex.check_tolerance(1e-12, 1e-10);
  const gapOk = ex.check_control_gap(0.1, 0.9, 0.25);
  const recOk = ex.verify_receipt_digest(root, root);

  assert.equal(ex.evaluate_verdict(3, 3, 1, tolOk, gapOk, recOk), 1);
  // Planted Control 1: missing planted controls
  assert.equal(ex.evaluate_verdict(0, 0, 1, tolOk, gapOk, recOk), -101);
  // Planted Control 2: planted failing control passed (caught < total)
  assert.equal(ex.evaluate_verdict(3, 2, 1, tolOk, gapOk, recOk), -102);
  // Planted Control 3: tampered receipt digest
  const recBad = ex.verify_receipt_digest(root, root ^ 1n);
  assert.equal(recBad, -301);
  assert.equal(ex.evaluate_verdict(3, 3, 1, tolOk, gapOk, recBad), -103);
  // Planted Control 4: tolerance breach, control-gap collapse, candidate fail
  const tolBad = ex.check_tolerance(0.5, 0.01);
  const gapBad = ex.check_control_gap(0.8, 0.81, 0.2);
  assert.equal(ex.evaluate_verdict(3, 3, 1, tolBad, gapOk, recOk), -104);
  assert.equal(ex.evaluate_verdict(3, 3, 1, tolOk, gapBad, recOk), -105);
  assert.equal(ex.evaluate_verdict(3, 3, 0, tolOk, gapOk, recOk), -106);
});
