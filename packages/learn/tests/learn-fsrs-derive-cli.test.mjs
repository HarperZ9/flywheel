// CLI + MCP surface tests for `tutor derive-schedule` / learn_tutor_derive_schedule.
//
// Proves the user-facing surface: re-derive the FSRS schedule from the witnessed graded log, emit a
// MATCH/DRIFT verdict receipt to disk, and catch a tampered cached itemState as DRIFT (non-zero exit).
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { main } from "../src/cli.mjs";
import { dispatch } from "../src/mcp.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const D2 = "2026-07-02T00:00:00.000Z";

test("CLI: derive-schedule re-derives a clean session to MATCH and writes a verified receipt", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-derive-"));
  await main(["tutor", "plan", "s", "--topic", "t", "--objectives", "a,b", "--enable-fsrs"], { dir });
  await main(["tutor", "record", "s", "--objective", "a", "--grade", "3", "--now", NOW], { dir });
  await main(["tutor", "record", "s", "--objective", "a", "--grade", "4", "--now", D2], { dir });
  await main(["tutor", "record", "s", "--objective", "b", "--grade", "0", "--now", NOW], { dir });

  const r = await main(["tutor", "derive-schedule", "s"], { dir });
  assert.equal(r.code, 0, "a clean session re-derives with a success exit code");
  assert.match(r.out, /verdict MATCH/);
  assert.match(r.out, /ledger verified/);

  const receipt = JSON.parse(readFileSync(join(dir, "tutor", "s.derive-schedule.json"), "utf8"));
  assert.equal(receipt.verdict, "MATCH");
  assert.equal(receipt.ledgerVerified, true);
  assert.equal(receipt.fsrsAttempts, 3);
  assert.ok(receipt.perObjective.every((p) => p.match));
});

test("CLI: --optimize records a per-learner difficulty prior in the receipt", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-derive-opt-"));
  await main(["tutor", "plan", "s", "--topic", "t", "--objectives", "a,b", "--enable-fsrs"], { dir });
  await main(["tutor", "record", "s", "--objective", "a", "--grade", "4", "--now", NOW], { dir });
  await main(["tutor", "record", "s", "--objective", "b", "--grade", "0", "--now", NOW], { dir });

  const r = await main(["tutor", "derive-schedule", "s", "--optimize"], { dir });
  assert.equal(r.code, 0);
  const receipt = JSON.parse(readFileSync(join(dir, "tutor", "s.derive-schedule.json"), "utf8"));
  // The all-correct objective (a) must get an easier (higher) difficulty prior than the failed one (b).
  assert.ok(receipt.priors.a > receipt.priors.b, "per-learner prior: correct history => easier item");
});

test("CLI: a tampered cached itemState is caught as DRIFT with a non-zero exit", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-derive-drift-"));
  await main(["tutor", "plan", "s", "--topic", "t", "--objectives", "a", "--enable-fsrs"], { dir });
  await main(["tutor", "record", "s", "--objective", "a", "--grade", "3", "--now", NOW], { dir });

  // Tamper the persisted cache so it no longer matches the witnessed log.
  const path = join(dir, "tutor", "s.json");
  const sess = JSON.parse(readFileSync(path, "utf8"));
  sess.itemState.a.stability = 12345;
  writeFileSync(path, JSON.stringify(sess));

  const r = await main(["tutor", "derive-schedule", "s"], { dir });
  assert.equal(r.code, 1, "DRIFT must surface as a failing exit code, not a silent pass");
  assert.match(r.out, /verdict DRIFT/);
  assert.match(r.out, /DRIFT on: a/);
});

test("MCP: learn_tutor_derive_schedule returns the same verdict as the CLI", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-derive-mcp-"));
  await dispatch("learn_tutor_plan", { sessionId: "m", topic: "t", objectives: ["a"], enableFsrs: true }, { dir });
  await dispatch("learn_tutor_record", { sessionId: "m", objective: "a", grade: 3, now: NOW }, { dir });

  const clean = await dispatch("learn_tutor_derive_schedule", { sessionId: "m" }, { dir });
  assert.equal(clean.verdict, "MATCH");
  assert.equal(clean.ledgerVerified, true);
  assert.equal(clean.sessionId, "m");
});
