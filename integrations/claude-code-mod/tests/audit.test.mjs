import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import { audit, auditModule } from "../scripts/audit-mods.mjs";

const here = fileURLToPath(new URL(".", import.meta.url));
const FIXTURES = join(here, "fixtures", "mods");
const ROOT = join(here, "..");
const rules = (mod) => mod.findings.map((f) => `${f.severity} ${f.rule}`).sort();

test("audit flags a mod that approves at tool.check and through a classic PermissionRequest hook", () => {
  const { mods } = audit([FIXTURES]);
  const bad = mods.find((m) => m.name === "permissive-policy-sample");
  assert.deepEqual(rules(bad), ["HIGH approve-at-check", "HIGH classic-allow"]);
});

test("audit flags forged consent, a constant 'allow', answering calls, speaking as the user and skipping tiers", () => {
  const { mods } = audit([FIXTURES]);
  const bad = mods.find((m) => m.name === "forged-consent-sample");
  assert.deepEqual(rules(bad), ["HIGH approve-at-check", "HIGH forged-consent", "MEDIUM answers-tool-call",
    "MEDIUM skips-tiers", "MEDIUM speaks-as-user"]);
});

test("audit stays quiet on a guard that only denies, even with 'allow' in a comment", () => {
  const { mods } = audit([FIXTURES]);
  assert.deepEqual(rules(mods.find((m) => m.name === "honest-guard")), []);
});

test("self-audit: this mod has no findings, including through its imported lib files", () => {
  const report = audit([ROOT]);
  const self = report.mods.find((m) => m.name === "flywheel-mod");
  assert.ok(self, "the audit found this plugin");
  assert.equal(self.modules.length, 5, "module.mjs plus its four lib imports");
  assert.deepEqual(self.findings, []);
});

test("a decision computed at run time is reported for review, not passed silently", () => {
  const src = "export function register(on){ on('tool.check', async ($,e,next) => ({ decision: pick(e) })) }";
  assert.deepEqual(auditModule("x.js", src).map((f) => f.rule), ["dynamic-decision"]);
});

test("the CLI exits 1 when a HIGH finding exists and 0 when none does", () => {
  const script = join(ROOT, "scripts", "audit-mods.mjs");
  const bad = spawnSync(process.execPath, [script, FIXTURES], { encoding: "utf8" });
  assert.equal(bad.status, 1);
  assert.match(bad.stdout, /3 hooks\.json file\(s\), 3 with a mod module; 4 high, 3 medium, 0 info/);
  const good = spawnSync(process.execPath, [script, join(FIXTURES, "honest-guard")], { encoding: "utf8" });
  assert.equal(good.status, 0);
});
