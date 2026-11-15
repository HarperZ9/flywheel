// The published package must not carry a developer's local path. Released 1.6.0 fell back to a
// hard-coded path from the author's machine when LEARN_NATIVE_CONTROL was unset, and its
// docs/smoke.md named the same folder. This walks every file package.json "files" ships.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, dirname, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const TEXT = /\.(mjs|js|json|md|svg|html|txt)$/i;
// A drive-letter path into a dev tree, or a home folder with a user name after it.
const LOCAL = [/\b[A-Za-z]:[\\/]+dev[\\/]/i, /\/Users\/[A-Za-z]/, /\/home\/[a-z]/, /[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z]/i];

function walk(p, out = []) {
  if (statSync(p).isDirectory()) { for (const n of readdirSync(p)) walk(join(p, n), out); }
  else out.push(p);
  return out;
}

function shipped() {
  const pkg = JSON.parse(readFileSync(join(ROOT, "package.json"), "utf8"));
  const files = [join(ROOT, "package.json")];
  for (const entry of pkg.files) walk(join(ROOT, entry), files);
  return files.filter((f) => TEXT.test(f));
}

test("no shipped file names a local development path", () => {
  const hits = [];
  for (const f of shipped()) {
    const text = readFileSync(f, "utf8");
    for (const re of LOCAL) if (re.test(text)) hits.push(`${relative(ROOT, f)} matches ${re}`);
  }
  assert.deepEqual(hits, []);
});
