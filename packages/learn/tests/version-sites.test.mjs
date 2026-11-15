// One version everywhere it is written. In 1.6.0 package.json and src/index.mjs said 1.6.0
// while the MCP serverInfo said 1.0.0, and nothing tied them together. This fails on any drift
// between package.json, package-lock.json, src/index.mjs, serverInfo, status, doctor, the newest
// CHANGELOG heading and the README's release line.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { version } from "../src/index.mjs";
import { handle } from "../src/mcp.mjs";
import { status } from "../src/status.mjs";
import { doctor } from "../src/doctor.mjs";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const read = (rel) => readFileSync(join(ROOT, rel), "utf8");
const pkg = JSON.parse(read("package.json"));

test("package.json, package-lock.json, src/index.mjs, serverInfo, status and doctor agree", async () => {
  const lock = JSON.parse(read("package-lock.json"));
  const init = await handle({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} });
  const sites = {
    "package-lock.json": lock.version,
    "package-lock.json packages[\"\"]": lock.packages[""].version,
    "src/index.mjs": version,
    "serverInfo.version": init.result.serverInfo.version,
    "status().version": status().version,
    "doctor().version": (await doctor()).version,
  };
  for (const [site, v] of Object.entries(sites)) assert.equal(v, pkg.version, `${site} says ${v}, package.json says ${pkg.version}`);
});

test("the newest CHANGELOG release heading is the package version", () => {
  const m = read("CHANGELOG.md").match(/^## (\d+\.\d+\.\d+)\b/m);
  assert.ok(m, "CHANGELOG.md has a release heading");
  assert.equal(m[1], pkg.version);
});

test("the README's release line names the package version", () => {
  assert.ok(read("README.md").includes("**Release:** `" + pkg.version + "`"));
});

// The README's test count was typed by hand and nothing checked it. Every test in this suite is a
// top-level test( call, so counting those lines gives the number node --test reports.
test("the README's test count matches the tests in tests/", () => {
  const files = readdirSync(join(ROOT, "tests")).filter((f) => f.endsWith(".test.mjs"));
  const count = files.reduce((n, f) => n + (read(join("tests", f)).match(/^test\(/gm) || []).length, 0);
  const m = read("README.md").match(/\*\*Tests:\*\* (\d+) /);
  assert.ok(m, "README.md has a **Tests:** line");
  assert.equal(Number(m[1]), count, `README says ${m[1]} tests; tests/ declares ${count}`);
});
