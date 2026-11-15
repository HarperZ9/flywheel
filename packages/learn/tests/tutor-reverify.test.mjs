// Tutor-receipt re-verification: the verifier must PASS a clean receipt and FAIL each known-bad
// input. A verifier that cannot fail on a known-bad input is not a verifier, so every typed
// failure code here has a negative fixture the check rejects.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { newSession, recordAttempt, masteryReceipt } from "../src/tutor/tutor.mjs";
import { studyReceipt } from "../src/tutor/study.mjs";
import { reverifyReceipt, reverifyFiles, reverifySelfCheck, CHAIN_BROKEN, VERDICT_MISMATCH } from "../src/tutor/reverify.mjs";
import { main } from "../src/cli.mjs";
import { dispatch } from "../src/mcp.mjs";

const NOW = "2026-06-30T00:00:00.000Z";

function masteredSession() {
  const s = newSession({ topic: "t", objectives: ["x"] });
  for (const q of ["q1", "q2", "q3"]) recordAttempt(s, { objective: "x", prompt: q, answer: "a", correct: true });
  return s;
}

// JSON round-trip mirrors what a consumer reads back from disk.
const roundTrip = (r) => JSON.parse(JSON.stringify(r));

test("reverifyReceipt: a clean mastery receipt re-verifies as VERIFIED with a witnessed summary", () => {
  const r = reverifyReceipt(roundTrip(masteryReceipt(masteredSession())));
  assert.equal(r.verdict, "VERIFIED");
  assert.deepEqual(r.failures, []);
  assert.match(r.witness.digest, /^sha256:[0-9a-f]{64}$/);
  assert.equal(r.summary.entries, 3);
  assert.equal(r.summary.rederivedReady, true);
});

test("reverifyReceipt: a clean study receipt re-verifies as VERIFIED", () => {
  const r = reverifyReceipt(roundTrip(studyReceipt(masteredSession(), { now: NOW })));
  assert.equal(r.verdict, "VERIFIED");
  assert.deepEqual(r.failures, []);
});

test("reverifyReceipt: a tampered MIDDLE entry yields CHAIN_BROKEN with the offending entry id", () => {
  const receipt = roundTrip(masteryReceipt(masteredSession()));
  receipt.entries[1].entry.correct = false; // tamper the middle receipt entry
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  const broken = r.failures.find((f) => f.code === CHAIN_BROKEN);
  assert.ok(broken, "expected a CHAIN_BROKEN failure");
  assert.equal(broken.seq, 1);
  assert.equal(broken.hash, receipt.entries[1].hash);
});

test("reverifyReceipt: author-controlled booleans never gate; a tampered receipt claiming verified still FAILS", () => {
  const receipt = roundTrip(masteryReceipt(masteredSession()));
  receipt.entries[1].entry.correct = false;
  receipt.ledgerVerified = true; // the author says it is fine; the evidence says otherwise
  receipt.verified = true;
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  assert.ok(r.failures.some((f) => f.code === CHAIN_BROKEN));
});

test("reverifyReceipt: a hand-edited overall verdict yields VERDICT_MISMATCH", () => {
  const receipt = roundTrip(masteryReceipt(masteredSession()));
  receipt.mastery.ready = false; // chain intact, verdict edited
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  const mm = r.failures.find((f) => f.code === VERDICT_MISMATCH);
  assert.ok(mm, "expected a VERDICT_MISMATCH failure");
  assert.equal(mm.stored.ready, false);
  assert.equal(mm.rederived.ready, true);
});

test("reverifyReceipt: a hand-edited per-objective stat yields VERDICT_MISMATCH", () => {
  const receipt = roundTrip(masteryReceipt(masteredSession()));
  receipt.mastery.perObjective[0].accuracy = 0.5;
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  assert.ok(r.failures.some((f) => f.code === VERDICT_MISMATCH));
});

test("reverifyReceipt: a truncated chain (dropped tail entry) yields CHAIN_BROKEN via attempt accounting", () => {
  const receipt = roundTrip(masteryReceipt(masteredSession()));
  receipt.entries.pop(); // hash-consistent truncation; totalAttempts still claims 3
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "FAILED");
  assert.ok(r.failures.some((f) => f.code === CHAIN_BROKEN));
});

test("reverifyReceipt: a chainless receipt is UNVERIFIED, never verified", () => {
  const receipt = roundTrip(masteryReceipt(masteredSession()));
  delete receipt.entries;
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "UNVERIFIED");
  assert.ok(r.reasons.length > 0);
});

test("reverifyReceipt: a receipt with no stored verdict is UNVERIFIED", () => {
  const receipt = roundTrip(masteryReceipt(masteredSession()));
  delete receipt.mastery;
  const r = reverifyReceipt(receipt);
  assert.equal(r.verdict, "UNVERIFIED");
});

test("reverifySelfCheck: the doctor probe passes (clean passes, every known-bad input fails)", () => {
  assert.equal(reverifySelfCheck(), true);
});

// ---- CLI ----

async function seedReceipts(dir, id) {
  await main(["tutor", "plan", id, "--topic", "t", "--objectives", "x"], { dir });
  for (const q of ["q1", "q2", "q3"]) {
    await main(["tutor", "record", id, "--objective", "x", "--prompt", q, "--answer", "a", "--correct", "true"], { dir });
  }
  await main(["tutor", "receipt", id], { dir });
  await main(["tutor", "study-receipt", id, "--now", NOW], { dir });
}

test("learn tutor reverify <id>: clean receipts exit 0 with a witnessed summary", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedReceipts(dir, "rv1");
  const r = await main(["tutor", "reverify", "rv1"], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /VERIFIED/);
  assert.match(r.out, /witnessed: sha256:[0-9a-f]{64}/);
});

test("learn tutor reverify <id>: a tampered middle entry on disk exits 1 with CHAIN_BROKEN", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedReceipts(dir, "rv2");
  const p = join(dir, "tutor", "rv2.mastery.json");
  const receipt = JSON.parse(readFileSync(p, "utf8"));
  receipt.entries[1].entry.correct = false;
  writeFileSync(p, JSON.stringify(receipt, null, 2));
  const r = await main(["tutor", "reverify", "rv2"], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /CHAIN_BROKEN/);
  assert.match(r.out, /seq=1/);
});

test("learn tutor reverify <id>: a hand-edited verdict on disk exits 1 with VERDICT_MISMATCH", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedReceipts(dir, "rv3");
  const p = join(dir, "tutor", "rv3.study-receipt.json");
  const receipt = JSON.parse(readFileSync(p, "utf8"));
  receipt.mastery.ready = false;
  writeFileSync(p, JSON.stringify(receipt, null, 2));
  const r = await main(["tutor", "reverify", "rv3"], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /VERDICT_MISMATCH/);
});

test("learn tutor reverify --file: a chainless receipt file exits 1 as UNVERIFIED", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const p = join(dir, "chainless.json");
  writeFileSync(p, JSON.stringify({ topic: "t", objectives: ["x"], mastery: { ready: true, threshold: 0.8, minAttempts: 3, perObjective: [], weakest: [] } }));
  const r = await main(["tutor", "reverify", "--file", p], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /UNVERIFIED/);
});

test("learn tutor reverify <id>: no receipt on disk exits 1 with a pointer to emit one first", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const r = await main(["tutor", "reverify", "nosuch"], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /no tutor receipt/i);
});

test("usage string mentions reverify", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const r = await main(["tutor"], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /reverify/);
});

// ---- MCP ----

test("mcp learn_tutor_reverify: clean receipts return ok true; a tampered file returns ok false with CHAIN_BROKEN", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedReceipts(dir, "rv4");
  const clean = await dispatch("learn_tutor_reverify", { sessionId: "rv4" }, { dir });
  assert.equal(clean.ok, true);
  assert.ok(clean.results.every((x) => x.verdict === "VERIFIED"));

  const p = join(dir, "tutor", "rv4.mastery.json");
  const receipt = JSON.parse(readFileSync(p, "utf8"));
  receipt.entries[1].entry.correct = false;
  writeFileSync(p, JSON.stringify(receipt, null, 2));
  const bad = await dispatch("learn_tutor_reverify", { sessionId: "rv4" }, { dir });
  assert.equal(bad.ok, false);
  assert.ok(bad.results.some((x) => x.failures.some((f) => f.code === "CHAIN_BROKEN")));
});
