// The browser entry loads in a page with no bundler: every module it reaches imports only by
// relative path, and none touches a Node global. A control proves the walk can fail.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SPEC = /(?:^|\n)\s*(?:import|export)\s[^;]*?from\s+"([^"]+)"/g;
const NODE_GLOBAL = /\b(process\.|Buffer\b|require\(|__dirname|__filename)/;

function walk(entry, { readText = (p) => readFileSync(p, "utf8") } = {}) {
  const seen = new Set();
  const problems = [];
  const visit = (file) => {
    if (seen.has(file)) return;
    seen.add(file);
    const text = readText(file);
    const code = text.replace(/\/\/.*$/gm, "");
    if (NODE_GLOBAL.test(code)) problems.push(`${file}: uses a Node global`);
    for (const m of text.matchAll(SPEC)) {
      const spec = m[1];
      if (!spec.startsWith("./") && !spec.startsWith("../")) { problems.push(`${file}: imports ${spec}`); continue; }
      visit(resolve(dirname(file), spec));
    }
  };
  visit(entry);
  return { files: [...seen], problems };
}

test("src/browser.mjs reaches only relative imports and no Node globals", () => {
  const { files, problems } = walk(join(ROOT, "src/browser.mjs"));
  assert.deepEqual(problems, []);
  assert.ok(files.length >= 8, `walked ${files.length} modules`);
});

test("control: the walk flags a module that imports node:crypto", () => {
  const fake = {
    [join(ROOT, "x/entry.mjs")]: 'export { a } from "./b.mjs";\n',
    [join(ROOT, "x/b.mjs")]: 'import { createHash } from "node:crypto";\nexport const a = 1;\n',
  };
  const { problems } = walk(join(ROOT, "x/entry.mjs"), { readText: (p) => fake[p] });
  assert.equal(problems.length, 1);
  assert.match(problems[0], /node:crypto/);
});

test("control: the tutor module itself is not browser-safe (it chains a ledger)", () => {
  const { problems } = walk(join(ROOT, "src/tutor/tutor.mjs"));
  assert.ok(problems.some((p) => p.includes("node:crypto")));
});

test("package.json exports the browser entry", () => {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  assert.equal(pkg.exports["./browser"], "./src/browser.mjs");
});

test("the browser entry exposes practice, schedule and diagnosis, with the same behaviour as tutor.mjs", async () => {
  const b = await import("../src/browser.mjs");
  const t = await import("../src/tutor/tutor.mjs");
  for (const name of ["newSession", "recordAttempt", "mastery", "due", "diagnose", "diagnoseChoice", "misconceptions"]) {
    assert.equal(typeof b[name], "function", name);
  }
  assert.equal(b.newSession, t.newSession);
  const s = b.newSessionWithFSRS({ topic: "t", objectives: ["q1"] });
  b.recordAttemptWithGrade(s, { objective: "q1", correct: true, now: "2026-10-01T00:00:00.000Z" });
  assert.deepEqual(b.due(s, { now: "2026-10-01T00:00:00.000Z", useFSRS: true }), []);
  assert.equal(b.due(s, { now: "2026-11-30T00:00:00.000Z", useFSRS: true }).length, 1);
});
