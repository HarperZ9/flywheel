import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { main } from "../src/cli.mjs";
import { dispatch } from "../src/mcp.mjs";

const NOW = "2026-06-30T00:00:00.000Z";
const LATER = "2026-07-20T00:00:00.000Z";

test("CLI: plan --enable-fsrs seeds itemState; record --grade updates it; study --use-fsrs ranks by retrievability", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-fsrs-"));
  const plan = await main(["tutor", "plan", "s", "--topic", "t", "--objectives", "strong,weak", "--enable-fsrs"], { dir });
  assert.equal(plan.code, 0);
  assert.match(plan.out, /FSRS scheduling enabled/i);

  // strong: an easy success -> high stability. weak: a fail -> low stability.
  await main(["tutor", "record", "s", "--objective", "strong", "--grade", "4", "--now", NOW], { dir });
  await main(["tutor", "record", "s", "--objective", "weak", "--grade", "0", "--now", NOW], { dir });

  const sess = JSON.parse(readFileSync(join(dir, "tutor", "s.json"), "utf8"));
  assert.ok(sess.itemState.strong && sess.itemState.weak, "itemState persisted through the store");
  assert.equal(sess.attempts.length, 2, "graded attempts are still witnessed in session.attempts");

  const study = await main(["tutor", "study", "s", "--now", LATER, "--use-fsrs"], { dir });
  assert.equal(study.code, 0);
  // The weak (low-stability) item must lead the FSRS-ranked order.
  assert.match(study.out, /order: weak/);
});

test("CLI: record --grade without --now fails clearly; out-of-range grade rejected", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-fsrs-"));
  await main(["tutor", "plan", "s", "--topic", "t", "--objectives", "a", "--enable-fsrs"], { dir });
  const noNow = await main(["tutor", "record", "s", "--objective", "a", "--grade", "3"], { dir });
  assert.equal(noNow.code, 1);
  assert.match(noNow.out, /now is required/i);
  const badGrade = await main(["tutor", "record", "s", "--objective", "a", "--grade", "9", "--now", NOW], { dir });
  assert.equal(badGrade.code, 1);
  assert.match(badGrade.out, /grade must be an integer 0-4/i);
});

test("CLI: --use-fsrs on a NON-FSRS session is advisory (no-op fallback, no crash)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-fsrs-"));
  await main(["tutor", "plan", "s", "--topic", "t", "--objectives", "a,b"], { dir }); // no --enable-fsrs
  await main(["tutor", "record", "s", "--objective", "a", "--prompt", "q", "--answer", "x", "--correct", "true"], { dir });
  const study = await main(["tutor", "study", "s", "--now", NOW, "--use-fsrs"], { dir });
  assert.equal(study.code, 0, "flag must not error on a legacy session; it falls back to interleave");
  const dueR = await main(["tutor", "due", "s", "--now", NOW, "--use-fsrs"], { dir });
  assert.equal(dueR.code, 0);
});

test("MCP: enableFsrs + grade recording + useFsrs study plan round-trip", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-fsrs-mcp-"));
  const plan = await dispatch("learn_tutor_plan", { sessionId: "m", topic: "t", objectives: ["strong", "weak"], enableFsrs: true }, { dir });
  assert.equal(plan.fsrs, true);
  await dispatch("learn_tutor_record", { sessionId: "m", objective: "strong", grade: 4, now: NOW }, { dir });
  await dispatch("learn_tutor_record", { sessionId: "m", objective: "weak", grade: 0, now: NOW }, { dir });
  const sp = await dispatch("learn_tutor_studyplan", { sessionId: "m", now: LATER, useFsrs: true }, { dir });
  assert.equal(sp.order[0], "weak", "MCP FSRS study order leads with the most-at-risk item");
  // mastery untouched: two attempts, one correct -> not ready.
  assert.equal(sp.mastery.ready, false);
});

test("MCP: learn_tutor_record with grade but no now throws clearly", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-fsrs-mcp-"));
  await dispatch("learn_tutor_plan", { sessionId: "m", topic: "t", objectives: ["a"], enableFsrs: true }, { dir });
  await assert.rejects(
    () => dispatch("learn_tutor_record", { sessionId: "m", objective: "a", grade: 3 }, { dir }),
    /now/i,
  );
});
