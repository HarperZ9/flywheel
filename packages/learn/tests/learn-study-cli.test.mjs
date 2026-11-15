import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { main } from "../src/cli.mjs";

const NOW = "2026-06-30T00:00:00.000Z";

async function seedSession(dir, id, { objectives = "a,b" } = {}) {
  await main(["tutor", "plan", id, "--topic", "t", "--objectives", objectives], { dir });
}

test("learn tutor due <id> --now: lists objectives due for review", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s1");
  await main(["tutor", "record", "s1", "--objective", "a", "--prompt", "q", "--answer", "x", "--correct", "true"], { dir });
  const r = await main(["tutor", "due", "s1", "--now", NOW], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /b/); // "b" never practiced -> due
});

test("learn tutor misconceptions <id>: lists ranked wrong-attempt aggregation", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s2");
  await main(["tutor", "record", "s2", "--objective", "a", "--prompt", "q", "--answer", "x", "--correct", "false", "--feedback", "sign error"], { dir });
  const r = await main(["tutor", "misconceptions", "s2"], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /sign error/);
});

test("learn tutor retrieval <id> --draft <file>: emits cloze prompts from the operator's own draft", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s3");
  const draftPath = join(dir, "draft.txt");
  writeFileSync(draftPath, "The hash chain detects tampering in 100% of single-entry edits.");
  const r = await main(["tutor", "retrieval", "s3", "--draft", draftPath, "--objective", "a"], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /___/);
});

test("learn tutor explain <id> --file <file>: builds a crucible thesis from the operator's own explanation", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s4");
  const explainPath = join(dir, "explain.txt");
  writeFileSync(explainPath, "The engine reduces build time by 40% because of caching.");
  const r = await main(["tutor", "explain", "s4", "--file", explainPath], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /thesis/i);
});

test("learn tutor predict <id>: records a pending prediction attempt", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s5");
  const r = await main(["tutor", "predict", "s5", "--objective", "a", "--prompt", "what happens?", "--prediction", "it settles faster"], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /pending/i);
});

test("learn tutor score <id> --index <n> --correct <bool>: scores a pending prediction", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s6");
  await main(["tutor", "predict", "s6", "--objective", "a", "--prompt", "q", "--prediction", "p"], { dir });
  const r = await main(["tutor", "score", "s6", "--index", "0", "--correct", "true", "--note", "matched render"], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /scored/i);
});

test("learn tutor path <id>: topologically orders objectives (throws surfaced as non-zero code on cycle)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s7");
  const r = await main(["tutor", "path", "s7"], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /a/);
  assert.match(r.out, /b/);
});

test("learn tutor study <id> --now: prints the composed study plan", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s8");
  await main(["tutor", "record", "s8", "--objective", "a", "--prompt", "q", "--answer", "x", "--correct", "false", "--feedback", "confused"], { dir });
  const r = await main(["tutor", "study", "s8", "--now", NOW], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /due/i);
});

test("learn tutor study-receipt <id> --now: writes a witnessed study receipt to disk", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await seedSession(dir, "s9");
  await main(["tutor", "record", "s9", "--objective", "a", "--prompt", "q", "--answer", "x", "--correct", "true"], { dir });
  const r = await main(["tutor", "study-receipt", "s9", "--now", NOW], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /study-receipt.json/);
  const written = JSON.parse(readFileSync(join(dir, "tutor", "s9.study-receipt.json"), "utf8"));
  assert.equal(written.verified, true);
});

test("usage string mentions the new subcommands", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const r = await main(["tutor"], { dir });
  assert.equal(r.code, 1);
  for (const sub of ["due", "misconceptions", "retrieval", "explain", "predict", "score", "path", "study", "study-receipt"]) {
    assert.match(r.out, new RegExp(sub), `usage should mention ${sub}`);
  }
});
