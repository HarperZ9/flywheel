// Peer commands given as a bare name, and the PATH they are looked up on.
// A LEARN_*_CMD such as ["crucible"] resolves on PATH. The safe spawn helper 1.0.0 skipped only
// relative PATH entries, so an absolute entry that reached the course folder (the folder learn
// runs in) started a program planted there: an entry naming the folder or a folder below it, a
// junction or symlink to it, and a quoted spelling of it. The child's PATH kept the same entries,
// so a peer command that runs a helper by bare name, the way npm's command shims run node,
// started a helper planted there too. The helper 1.0.1 drops every such entry from the lookup and
// from the child's PATH, and on Windows refuses a drive-relative name such as C:tool. Each test
// runs the learn CLI in a course folder that holds the plant. All fixtures are local temporary
// folders and scripts.
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  chmodSync, copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync,
  statSync, symlinkSync, writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { delimiter, dirname, join, parse } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const WINDOWS = process.platform === "win32";
const CLI = fileURLToPath(new URL("../src/cli.mjs", import.meta.url));
const RENDER = JSON.stringify({ verdict: "MATCH", selected_profile: "real-peer" });
const DRAFT = "Loop memory drops 265x, as https://example.org/paper shows.";
const windowsOnly = { skip: !WINDOWS && "cmd.exe and drive-relative names are Windows behavior" };

function write(p, text, mode) {
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, text);
  if (mode) chmodSync(p, mode);
  return p;
}

// A command `name` in `folder` that records its arguments in `log` and prints a render result.
function realTool(folder, name, log) {
  const body = write(join(folder, `${name}-body.cjs`), `require("fs").writeFileSync(${JSON.stringify(log)}, `
    + `JSON.stringify(process.argv.slice(2)));\nprocess.stdout.write(${JSON.stringify(RENDER)});\n`);
  if (WINDOWS) return write(join(folder, `${name}.cmd`), `@echo off\r\n"${process.execPath}" "${body}" %*\r\n`);
  return write(join(folder, name), `#!/bin/sh\nexec "${process.execPath}" "${body}" "$@"\n`, 0o755);
}

// A command `name` in `folder` that leaves `marker` behind if it ever runs.
function plant(folder, name, marker) {
  if (WINDOWS) return write(join(folder, `${name}.cmd`), `@echo off\r\necho x> "${marker}"\r\necho PLANTED\r\n`);
  return write(join(folder, name), `#!/bin/sh\necho x > "${marker}"\necho PLANTED\n`, 0o755);
}

// A peer command that runs `helper` by bare name, the way npm's command shims run node.
function callsHelper(folder) {
  if (WINDOWS) return write(join(folder, "peer.cmd"), "@echo off\r\nhelper %*\r\n");
  return write(join(folder, "peer"), '#!/bin/sh\nexec helper "$@"\n', 0o755);
}

// root/course is where learn runs and where the plants go; root/bin holds the real `tool`. The
// whole root is removed when the test `t` ends.
function world(t) {
  const root = realpathSync.native(mkdtempSync(join(tmpdir(), "learn-path-")));
  t.after(() => rmSync(root, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }));
  const w = {
    root, course: join(root, "course"), bin: join(root, "bin"), state: join(root, "state"),
    marker: join(root, "PLANTED-RAN"), log: join(root, "REAL-RAN.json"),
  };
  mkdirSync(w.course);
  realTool(w.bin, "tool", w.log);
  writeFileSync(join(w.course, "draft.md"), DRAFT);
  writeFileSync(join(w.course, "concept.json"), JSON.stringify({ title: "Area under a curve" }));
  return w;
}

// Run the learn CLI in the course folder with PATH made of `entries` and `vars` on top. The
// caller's own PATH and LEARN_* settings are left out, so the test sees only its fixtures.
function learn(w, args, entries, vars) {
  const env = Object.fromEntries(Object.entries(process.env)
    .filter(([k]) => k.toUpperCase() !== "PATH" && !k.toUpperCase().startsWith("LEARN_")));
  Object.assign(env, { PATH: entries.join(delimiter), LEARN_HOME: w.state }, vars);
  return spawnSync(process.execPath, [CLI, ...args], { cwd: w.course, env, encoding: "utf8", timeout: 60000 });
}

const visualize = (w, entries, cmd) => learn(w,
  ["visualize", join(w.course, "concept.json"), "--out", join(w.state, "runs")], entries, { LEARN_TELOS_CMD: cmd });
const assist = (w, flag, entries, vars) => learn(w,
  ["assist", "draft.md", flag, "--out", join(w.state, "assist")], entries, vars);

// No plant ran, and the real command ran with `args` first.
function realRan(w, r, args, log = w.log) {
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(existsSync(w.marker), false, "a program planted in the course folder ran: " + r.stdout);
  assert.ok(existsSync(log), "the real peer command did not run: " + r.stdout + r.stderr);
  assert.deepEqual(JSON.parse(readFileSync(log, "utf8")).slice(0, args.length), args);
}

const sameFolder = (a, b) => {
  const [x, y] = [statSync(a, { bigint: true }), statSync(b, { bigint: true })];
  return x.dev === y.dev && x.ino === y.ino;
};

test("LEARN_TELOS_CMD by bare name skips PATH entries at or below the course folder", (t) => {
  // npm run and an activated project venv put a folder like node_modules/.bin first on PATH.
  const w = world(t);
  const below = join(w.course, "node_modules", ".bin");
  plant(below, "tool", w.marker);
  plant(w.course, "tool", w.marker);
  const r = visualize(w, [below, w.course, w.bin], JSON.stringify(["tool"]));
  realRan(w, r, ["render"]);
  assert.match(r.stdout, /-> MATCH \(profile real-peer\)/);
});

test("LEARN_CRUCIBLE_CMD by bare name skips a PATH entry naming the course folder", (t) => {
  const w = world(t);
  plant(w.course, "tool", w.marker);
  const r = assist(w, "--crucible", [w.course, w.bin], { LEARN_CRUCIBLE_CMD: "tool" });
  realRan(w, r, ["assess", join(w.state, "assist", "crucible-thesis.json")]);
  assert.match(r.stdout, /crucible: ran \(exit 0\)/);
});

// The scripts folder of a virtual environment: Scripts on Windows, bin elsewhere.
const venvScripts = (w) => join(w.course, ".venv", WINDOWS ? "Scripts" : "bin");

test("the documented [\"python\", \"-m\", \"crucible\"] skips a venv inside the course folder", (t) => {
  // An activated venv puts its scripts folder first on PATH. Inside the course folder that folder
  // is course content, so bare python resolves to the next Python on PATH, which gets -P.
  const w = world(t);
  plant(venvScripts(w), "python", w.marker);
  realTool(w.bin, "python", w.log);
  const r = assist(w, "--crucible", [venvScripts(w), w.bin],
    { LEARN_CRUCIBLE_CMD: JSON.stringify(["python", "-m", "crucible"]) });
  realRan(w, r, ["-P", "-m", "crucible", "assess", join(w.state, "assist", "crucible-thesis.json")]);
  assert.match(r.stdout, /crucible: ran \(exit 0\)/);
});

test("LEARN_GATHER_CMD by bare name skips a PATH entry naming the course folder", (t) => {
  const w = world(t);
  plant(w.course, "tool", w.marker);
  const r = assist(w, "--gather", [w.course, w.bin], { LEARN_GATHER_CMD: JSON.stringify(["tool"]) });
  realRan(w, r, ["run", "https://example.org/paper"]);
  assert.match(r.stdout, /gather: 1 source\(s\) processed/);
});

test("a junction or symlink to the course folder on PATH is skipped", (t) => {
  const w = world(t);
  plant(w.course, "tool", w.marker);
  const at = join(w.root, "linkbin");
  symlinkSync(w.course, at, WINDOWS ? "junction" : "dir");
  assert.ok(sameFolder(at, w.course), "the link must lead into the course folder");
  const r = visualize(w, [at, w.bin], JSON.stringify(["tool"]));
  realRan(w, r, ["render"]);
});

test("a quoted PATH entry naming the course folder is skipped", (t) => {
  // 1.0.0 stripped the quotes and searched the folder. Windows reads the entry as the folder
  // too, so it must leave; POSIX reads the quotes literally, so the entry is relative there.
  const w = world(t);
  plant(w.course, "tool", w.marker);
  const r = visualize(w, [`"${w.course}"`, w.bin], JSON.stringify(["tool"]));
  realRan(w, r, ["render"]);
});

test("a peer command's own lookup never reaches a helper planted in the course folder", (t) => {
  // The peer command is absolute and outside the course folder; the helper it runs by bare name
  // is looked up on the PATH learn hands it, which must not name the course folder.
  const w = world(t);
  plant(w.course, "helper", w.marker);
  const helpers = join(w.root, "helpers");
  realTool(helpers, "helper", w.log);
  const peer = callsHelper(join(w.root, "tools"));
  const r = visualize(w, [w.course, helpers], JSON.stringify([peer]));
  realRan(w, r, ["render"]);
});

test("an entry with inner quotes never hands the course folder to a peer command", windowsOnly, (t) => {
  // cmd.exe drops every quote, so "<course>"\bin is <course>\bin to the peer command's shell.
  // 1.0.0 stripped only a leading and a trailing quote, found no such folder, and handed the
  // entry on as written.
  const w = world(t);
  plant(join(w.course, "bin"), "helper", w.marker);
  const helpers = join(w.root, "helpers");
  realTool(helpers, "helper", w.log);
  const peer = callsHelper(join(w.root, "tools"));
  const r = visualize(w, [`"${w.course}"\\bin`, helpers], JSON.stringify([peer]));
  realRan(w, r, ["render"]);
});

test("a drive-relative command name is refused before anything starts", windowsOnly, (t) => {
  // C:tool names a file in drive C's current folder, which is the course folder here. The 1.0.0
  // lookup already failed closed on it (NOT_FOUND); this pins the refusal as BAD_PATH.
  const w = world(t);
  copyFileSync(join(process.env.SystemRoot, "System32", "hostname.exe"), join(w.course, "tool.exe"));
  plant(w.course, "tool", w.marker);
  const drive = parse(w.course).root.slice(0, 2);
  const r = assist(w, "--crucible", [w.bin], { LEARN_CRUCIBLE_CMD: JSON.stringify([`${drive}tool`]) });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.equal(existsSync(w.marker), false, "a program planted in the course folder ran");
  assert.equal(existsSync(w.log), false, "nothing may start for a drive-relative name");
  assert.doesNotMatch(r.stdout, /crucible: ran/);
  assert.match(r.stdout, /crucible: crucible was not started \(BAD_PATH\)/);
});

test("control: a peer command named by absolute path inside the course folder still runs", (t) => {
  // Only the PATH lookup drops the course folder. An absolute command is the user's own choice.
  const w = world(t);
  const inside = join(w.root, "COURSE-TOOL-RAN.json");
  const tool = realTool(join(w.course, "node_modules", ".bin"), "tool", inside);
  const r = visualize(w, [w.bin], JSON.stringify([tool]));
  realRan(w, r, ["render"], inside);
  assert.equal(existsSync(w.log), false, "the PATH tool ran instead of the named one");
});

test("control: a venv interpreter named by absolute path inside the course folder still runs", (t) => {
  // The documented way to use a course venv: name its interpreter by absolute path. It still gets
  // -P, and the other Python on PATH does not run.
  const w = world(t);
  const inside = join(w.root, "VENV-PYTHON-RAN.json");
  const python = realTool(venvScripts(w), "python", inside);
  realTool(w.bin, "python", w.log);
  const r = assist(w, "--crucible", [venvScripts(w), w.bin],
    { LEARN_CRUCIBLE_CMD: JSON.stringify([python, "-m", "crucible"]) });
  realRan(w, r, ["-P", "-m", "crucible", "assess", join(w.state, "assist", "crucible-thesis.json")], inside);
  assert.equal(existsSync(w.log), false, "the PATH python ran instead of the named one");
});
