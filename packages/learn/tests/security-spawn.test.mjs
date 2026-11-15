// Child processes for LEARN_CRUCIBLE_CMD, LEARN_GATHER_CMD and LEARN_TELOS_CMD.
// Released 1.6.0 split the variable on whitespace and ran the child in the caller's folder with
// the full environment, so with the documented `python -m crucible` a crucible/ package planted
// in a course folder ran on every `learn assist --crucible`. Children now start through the
// vendored safe spawn helper. All fixtures are local: temporary folders and test scripts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, copyFileSync, realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { telosRender } from "../src/interop/telos.mjs";
import { crucibleAssess } from "../src/interop/crucible.mjs";

const PROBE = fileURLToPath(new URL("./fixtures/probe-child.mjs", import.meta.url));
const FAKE = fileURLToPath(new URL("./fixtures/fake-telos.mjs", import.meta.url));
const CLI = fileURLToPath(new URL("../src/cli.mjs", import.meta.url));
const PLANTED = "FAKE_KEY_do_not_forward_4242";
const tmp = () => mkdtempSync(join(tmpdir(), "learn-spawn-"));
const real = (p) => realpathSync.native(p).toLowerCase();

function withEnv(vars, fn) {
  const saved = Object.fromEntries(Object.keys(vars).map((k) => [k, process.env[k]]));
  Object.assign(process.env, vars);
  return Promise.resolve().then(fn).finally(() => {
    for (const [k, v] of Object.entries(saved)) { if (v === undefined) delete process.env[k]; else process.env[k] = v; }
  });
}

test("a LEARN_*_CMD child starts in a private empty folder and sees only allowlisted variables", async () => {
  const dir = tmp();
  const spec = join(dir, "scene.json");
  writeFileSync(spec, "{}");
  await withEnv({ LEARN_PROBE_PLANTED: PLANTED, LEARN_PROBE_PASSED: "named", LEARN_CHILD_ENV: "LEARN_PROBE_PASSED" }, async () => {
    const r = await telosRender(spec, { cmd: "node " + PROBE });
    assert.equal(r.verdict, "MATCH");
  });
  const report = JSON.parse(readFileSync(join(dir, "probe-report.json"), "utf8"));
  assert.notEqual(report.cwd.toLowerCase(), real(process.cwd()), "the child must not inherit the caller's folder");
  assert.deepEqual(report.cwdEntries, [], "the child's folder is empty");
  assert.equal(report.sawPlanted, null, "an unlisted variable must not reach the child");
  assert.equal(report.sawPassed, "named", "LEARN_CHILD_ENV names variables that may pass");
  assert.equal(report.pythonSafePath, "1");
  if (process.platform === "win32") assert.equal(report.noDefaultCwd, "1");
});

test("LEARN_*_CMD takes a JSON argv array, so a path with a space stays one argument", async () => {
  const dir = tmp();
  const spaced = join(dir, "tools with space");
  mkdirSync(spaced);
  const script = join(spaced, "fake telos.mjs");
  copyFileSync(FAKE, script);
  const r = await telosRender(join(dir, "scene.json"), { cmd: JSON.stringify(["node", script]) });
  assert.equal(r.ran, true);
  assert.equal(r.verdict, "MATCH");
});

test("a relative path in LEARN_*_CMD is refused with a reason, since the child's folder is private", async () => {
  const r = await telosRender(join(tmp(), "scene.json"), { cmd: "node ../telos/src/cli.mjs" });
  assert.equal(r.ran, false);
  assert.equal(r.verdict, "UNVERIFIABLE");
  assert.match(r.reason, /absolute path/);
  const c = await crucibleAssess(join(tmp(), "t.json"), { cmd: '["./crucible.exe"]' });
  assert.equal(c.ran, false);
  assert.match(c.reason, /absolute path/);
});

// The Python the test uses, when it is 3.11 or later (the -P floor).
function python311() {
  const r = spawnSync("python", ["-c", "import sys; print(sys.version_info >= (3, 11))"], { encoding: "utf8" });
  return !r.error && r.status === 0 && r.stdout.trim() === "True";
}

test("the planted crucible/ package in the caller's folder does not run under LEARN_CRUCIBLE_CMD='python -m crucible'", async (t) => {
  if (!python311()) return t.skip("needs python 3.11 or later on PATH");
  const work = tmp();
  const pkg = join(work, "crucible");
  mkdirSync(pkg);
  writeFileSync(join(pkg, "__init__.py"), "");
  writeFileSync(join(pkg, "__main__.py"),
    "import os\nopen(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'MARKER'), 'w').write('ran')\n");
  // Control: the plant is live, since python -m puts the working folder first on sys.path.
  spawnSync("python", ["-m", "crucible"], { cwd: work });
  assert.ok(existsSync(join(pkg, "MARKER")), "control: the planted package runs from its own folder");
  rmSync(join(pkg, "MARKER"));

  writeFileSync(join(work, "draft.md"), "My engine reduces loop memory 265x.");
  const state = tmp();
  const r = spawnSync(process.execPath, [CLI, "assist", "draft.md", "--crucible", "--out", join(state, "assist")], {
    cwd: work, encoding: "utf8", timeout: 60000,
    env: { ...process.env, LEARN_CRUCIBLE_CMD: "python -m crucible", LEARN_HOME: state },
  });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /crucible: /);
  assert.equal(existsSync(join(pkg, "MARKER")), false, "the planted crucible package ran");
});
