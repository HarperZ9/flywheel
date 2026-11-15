import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { TOOLS, dispatch, handle } from "../src/mcp.mjs";
import { newSession, recordAttempt } from "../src/tutor/tutor.mjs";
import { saveSession } from "../src/tutor/tutorstore.mjs";

const NOW = "2026-06-30T00:00:00.000Z";

function seed(dir, id) {
  const s = newSession({ topic: "t", objectives: ["a", "b"] });
  recordAttempt(s, { objective: "a", prompt: "q", answer: "x", correct: false, feedback: "sign error" });
  saveSession(dir, id, s);
  return s;
}

test("learn_tutor_due, learn_tutor_studyplan, learn_tutor_misconceptions are registered as advisory tools", () => {
  for (const name of ["learn_tutor_due", "learn_tutor_studyplan", "learn_tutor_misconceptions"]) {
    const t = TOOLS.find((x) => x.name === name);
    assert.ok(t, `${name} present`);
    assert.equal(typeof t.description, "string");
  }
});

test("learn_tutor_due: read-only over a saved session, lists due objectives", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  seed(dir, "mcp1");
  const out = await dispatch("learn_tutor_due", { sessionId: "mcp1", now: NOW }, { dir });
  assert.ok(Array.isArray(out.due));
  assert.ok(out.due.some((d) => d.objective === "b"));
});

test("learn_tutor_due: throws (does not silently no-op) for an unknown session", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  await assert.rejects(() => dispatch("learn_tutor_due", { sessionId: "nope", now: NOW }, { dir }));
});

test("learn_tutor_studyplan: returns the composed plan (due + misconceptions + order + readiness + mastery)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  seed(dir, "mcp2");
  const out = await dispatch("learn_tutor_studyplan", { sessionId: "mcp2", now: NOW }, { dir });
  assert.ok(Array.isArray(out.due));
  assert.ok(Array.isArray(out.misconceptions));
  assert.ok(Array.isArray(out.order));
  assert.ok(Array.isArray(out.readiness));
  assert.equal(typeof out.mastery.ready, "boolean");
});

test("learn_tutor_misconceptions: returns ranked wrong-attempt aggregation, read-only", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  seed(dir, "mcp3");
  const out = await dispatch("learn_tutor_misconceptions", { sessionId: "mcp3" }, { dir });
  assert.ok(Array.isArray(out.misconceptions));
  assert.ok(out.misconceptions.some((m) => m.objective === "a"));
});

test("advisory tools never mutate the saved session (read-only over the store)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const s = seed(dir, "mcp4");
  const before = JSON.stringify(s);
  await dispatch("learn_tutor_due", { sessionId: "mcp4", now: NOW }, { dir });
  await dispatch("learn_tutor_studyplan", { sessionId: "mcp4", now: NOW }, { dir });
  await dispatch("learn_tutor_misconceptions", { sessionId: "mcp4" }, { dir });
  const { loadSession } = await import("../src/tutor/tutorstore.mjs");
  const after = JSON.stringify(loadSession(dir, "mcp4"));
  assert.equal(after, before);
});

test("tools/call routes learn_tutor_studyplan through the JSON-RPC handler", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  seed(dir, "mcp5");
  const res = await handle({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "learn_tutor_studyplan", arguments: { sessionId: "mcp5", now: NOW } } }, { dir });
  assert.ok(res.result.content[0].text.includes("due"));
});
