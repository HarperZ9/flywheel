// Flagship-parity examples test — asserts learn ships examples/ (course.json, study.json,
// demo.mjs, learn-demo.html) at the same standard as crucible/examples and gather/examples, and
// that the demo never crosses the integrity line: it must halt at `assess` (never auto-complete
// graded work) and must never fabricate/reveal an answer inside the tutor study-loop it prints.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { execFileSync } from "node:child_process";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => readFileSync(path.join(ROOT, rel), "utf8");
const exists = (rel) => existsSync(path.join(ROOT, rel));

test("examples/ ships course.json, study.json, demo.mjs, learn-demo.html", () => {
  for (const rel of [
    "examples/course.json",
    "examples/study.json",
    "examples/demo.mjs",
    "examples/learn-demo.html",
  ]) {
    assert.ok(exists(rel), `missing ${rel}`);
  }
});

test("examples/course.json is a valid fake-adapter workflow with an assess step", () => {
  const wf = JSON.parse(read("examples/course.json"));
  assert.equal(wf.adapter, "fake");
  assert.ok(Array.isArray(wf.steps) && wf.steps.length > 0);
  assert.ok(wf.steps.some((s) => s.kind === "assess"), "course.json must include an assess step (the halt)");
});

test("examples/study.json has a concept map with requires: for at least one objective", () => {
  const study = JSON.parse(read("examples/study.json"));
  assert.ok(Array.isArray(study.sessionObjectives) && study.sessionObjectives.length > 1);
  assert.ok(Array.isArray(study.conceptMap) && study.conceptMap.length > 1);
  const withRequires = study.conceptMap.filter((o) => o && typeof o === "object" && Array.isArray(o.requires) && o.requires.length > 0);
  assert.ok(withRequires.length >= 1, "study.json's conceptMap must include at least one objective with a non-empty requires:");
  // every sessionObjectives id must also appear in the concept map, and vice versa
  const sessionIds = new Set(study.sessionObjectives);
  const mapIds = new Set(study.conceptMap.map((o) => o.id));
  for (const id of sessionIds) assert.ok(mapIds.has(id), `conceptMap missing id "${id}" from sessionObjectives`);
  for (const id of mapIds) assert.ok(sessionIds.has(id), `sessionObjectives missing id "${id}" from conceptMap`);
});

test("node examples/demo.mjs runs clean (exit 0) and shows the halt", () => {
  const out = execFileSync(process.execPath, ["examples/demo.mjs"], { cwd: ROOT, encoding: "utf8" });
  assert.match(out, /halted-assess/, "demo.mjs output must show the workflow halting at assess");
  assert.match(out, /Quiz 1/, "demo.mjs output must name the graded step it halted at");
});

test("demo.mjs output never fabricates or reveals a graded-quiz answer", () => {
  const out = execFileSync(process.execPath, ["examples/demo.mjs"], { cwd: ROOT, encoding: "utf8" });
  // The only "answers" the demo may print are the operator's OWN recorded practice answers from
  // study.json (3x^2, 5x^4, 7x^6, etc.) or explicit sentinels like "(withheld)"/blanked cloze text.
  // It must never print a synthesized/derived answer for the halted `assess` step itself.
  assert.ok(!/quiz answer/i.test(out), "demo.mjs must never print a synthesized quiz answer");
  assert.ok(!/the answer is/i.test(out), "demo.mjs must never assert a graded answer");
});

test("demo.mjs prints due/mastery from the tutor study-loop over study.json", () => {
  const out = execFileSync(process.execPath, ["examples/demo.mjs"], { cwd: ROOT, encoding: "utf8" });
  assert.match(out, /due/i);
  assert.match(out, /mastery/i);
});

test("examples/learn-demo.html is self-contained (no external network deps) and states the integrity line", () => {
  const html = read("examples/learn-demo.html");
  assert.match(html, /<!doctype html>/i);
  // no remote script/style tags pulling from a CDN or other origin
  assert.ok(!/<script[^>]+src=["']https?:\/\//i.test(html), "learn-demo.html must not load remote scripts");
  const linkTags = html.match(/<link[^>]+>/gi) || [];
  for (const tag of linkTags) {
    assert.ok(!/href=["']https?:\/\//i.test(tag), `learn-demo.html must not load a remote stylesheet: ${tag}`);
  }
  assert.match(html, /assess/i);
  assert.match(html, /halt/i);
});
