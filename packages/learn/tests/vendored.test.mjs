// The vendored safe spawn helper must stay byte-identical to its canonical release
// (safe_spawn.mjs 1.0.1). VENDORED.sha256 records the copy's hash in sha256sum format; this test
// fails when the file drifts from the record, when the record drifts from the canonical hash, or
// when a checkout rewrites its line endings (the .gitattributes rule keeps it byte-exact).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
// Canonical hash of safe_spawn.mjs 1.0.1, from the helper's own SHA256SUMS.
const CANONICAL = "c2a97db6b84b7a019696c684408c91277cad545e5a78eae90609e758d106202d";
// safe_spawn.mjs 1.0.0, superseded: a PATH entry that reached the working folder could start a
// program planted there. A copy with this hash fails with that reason named.
const SUPERSEDED_1_0_0 = "c1572ae596d63a34288a4e02de2c0d671384bd341cb5c8070b4c70664f8c4ff6";
const REL = "src/_vendor/safe_spawn.mjs";

const sha256 = (buf) => createHash("sha256").update(buf).digest("hex");

test("VENDORED.sha256 records the vendored helper at its canonical hash", () => {
  const lines = readFileSync(join(ROOT, "VENDORED.sha256"), "utf8").split("\n").filter((l) => l.trim() && !l.startsWith("#"));
  const rows = lines.map((l) => l.trim().split(/\s+\*?/));
  assert.deepEqual(rows, [[CANONICAL, REL]]);
});

test("the vendored helper's bytes hash to the record (no local edit, no CRLF rewrite)", () => {
  const bytes = readFileSync(join(ROOT, ...REL.split("/")));
  assert.equal(bytes.includes(13), false, "the vendored copy must keep LF line endings");
  assert.notEqual(sha256(bytes), SUPERSEDED_1_0_0, "the vendored helper is the superseded 1.0.0; vendor 1.0.1");
  assert.equal(sha256(bytes), CANONICAL);
});

test("the vendored helper reports version 1.0.1 and .gitattributes keeps it byte-exact", async () => {
  const mod = await import("../src/_vendor/safe_spawn.mjs");
  assert.equal(mod.SAFE_SPAWN_VERSION, "1.0.1");
  const attrs = readFileSync(join(ROOT, ".gitattributes"), "utf8");
  assert.match(attrs, /^\*\*\/_vendor\/safe_spawn\.mjs\s+-text\s*$/m);
});
