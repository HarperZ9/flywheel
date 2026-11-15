// With LEARN_NATIVE_CONTROL unset, a native run fails at once with a setup message and imports
// nothing. Runs in a child process so the module reads a clean environment. Not run against the
// released 1.6.0 tree: that version would import from a local path instead.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const DRIVER = pathToFileURL(fileURLToPath(new URL("../src/actuation/native-driver.mjs", import.meta.url))).href;

test("NativeDriver.open without LEARN_NATIVE_CONTROL fails with a setup instruction", () => {
  const env = { ...process.env };
  delete env.LEARN_NATIVE_CONTROL;
  const script = `import(${JSON.stringify(DRIVER)}).then((m) => m.NativeDriver.open()).then(() => console.log("OPENED"), (e) => console.log(e.message));`;
  const r = spawnSync(process.execPath, ["--input-type=module", "-e", script], { env, encoding: "utf8", timeout: 20000 });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /set LEARN_NATIVE_CONTROL/);
  assert.doesNotMatch(r.stdout, /OPENED/);
});

// Review note on LEARN_NATIVE_CONTROL. A relative value resolved against the folder the run
// started in, so a browser.mjs planted there was imported and ran: the same working-folder class
// as the LEARN_*_CMD fix. The value must now be absolute. The planted module only writes a marker.
test("a relative LEARN_NATIVE_CONTROL is refused and nothing from the working folder is imported", () => {
  const work = mkdtempSync(join(tmpdir(), "learn-native-rel-"));
  mkdirSync(join(work, "native-control"));
  writeFileSync(join(work, "native-control", "browser.mjs"),
    "import { writeFileSync } from 'node:fs';\n" +
    "writeFileSync(new URL('./MARKER', import.meta.url), 'imported');\n" +
    "export async function ensureChrome() { throw new Error('planted module ran'); }\n");
  const script = `import(${JSON.stringify(DRIVER)}).then((m) => m.NativeDriver.open()).then(() => console.log("OPENED"), (e) => console.log(e.message));`;
  const open = (value) => spawnSync(process.execPath, ["--input-type=module", "-e", script],
    { cwd: work, env: { ...process.env, LEARN_NATIVE_CONTROL: value }, encoding: "utf8", timeout: 20000 });

  const rel = open("native-control");
  assert.equal(rel.status, 0, rel.stderr);
  assert.equal(existsSync(join(work, "native-control", "MARKER")), false, "the planted module was imported");
  assert.match(rel.stdout, /LEARN_NATIVE_CONTROL must be an absolute path/);

  // Control: the plant is live. Named by its absolute path, it is imported and runs.
  const abs = open(join(work, "native-control"));
  assert.equal(abs.status, 0, abs.stderr);
  assert.match(abs.stdout, /planted module ran/);
  assert.equal(existsSync(join(work, "native-control", "MARKER")), true);
});
