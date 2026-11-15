// Where learn keeps its state. Released 1.6.0 wrote tutor/ and
// runs/ into whatever folder the server or CLI started in, which for an MCP server is the user's
// project. State now lives in LEARN_HOME when set, else a per-user data folder; the CLI takes
// --dir for a project-local folder. Subprocess tests run the real entry points from a project
// folder with LEARN_HOME pointed at a temporary folder, so no test touches the real user folder.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "src");

function folders() {
  const root = mkdtempSync(join(tmpdir(), "learn-state-"));
  const proj = join(root, "project");
  const state = join(root, "state");
  const other = join(root, "other");
  for (const d of [proj, state, other]) mkdirSync(d);
  return { proj, state, other };
}

const envWith = (extra) => ({ ...process.env, ...extra });

function mcp(cwd, env, messages) {
  const input = messages.map((m) => JSON.stringify(m)).join("\n") + "\n";
  const r = spawnSync(process.execPath, [join(SRC, "mcp.mjs")], { cwd, env, input, encoding: "utf8", timeout: 30000 });
  return { ...r, replies: r.stdout.split("\n").filter(Boolean).map((l) => JSON.parse(l)) };
}

const cli = (cwd, env, args) =>
  spawnSync(process.execPath, [join(SRC, "cli.mjs"), ...args], { cwd, env, encoding: "utf8", timeout: 30000 });

test("MCP server started in a project folder writes its sessions under LEARN_HOME, not into the project", () => {
  const { proj, state } = folders();
  const r = mcp(proj, envWith({ LEARN_HOME: state }), [
    { jsonrpc: "2.0", id: 1, method: "initialize", params: {} },
    { jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "learn_tutor_plan", arguments: { sessionId: "s1", objectives: ["a"] } } },
  ]);
  assert.equal(r.status, 0, r.stderr);
  const plan = r.replies.find((x) => x.id === 2);
  assert.ok(plan && plan.result && !plan.result.isError, JSON.stringify(plan));
  assert.ok(existsSync(join(state, "tutor", "s1.json")), "session saved in LEARN_HOME");
  assert.equal(existsSync(join(proj, "tutor")), false, "nothing written into the caller's folder");
});

test("CLI keeps state under LEARN_HOME by default and in a project folder only when --dir names it", () => {
  const { proj, state, other } = folders();
  const a = cli(proj, envWith({ LEARN_HOME: state }), ["tutor", "plan", "s1", "--objectives", "a"]);
  assert.equal(a.status, 0, a.stdout + a.stderr);
  assert.ok(existsSync(join(state, "tutor", "s1.json")));
  assert.equal(existsSync(join(proj, "tutor")), false);

  const b = cli(other, envWith({ LEARN_HOME: state }), ["tutor", "plan", "s2", "--objectives", "a", "--dir", proj]);
  assert.equal(b.status, 0, b.stdout + b.stderr);
  assert.ok(existsSync(join(proj, "tutor", "s2.json")), "--dir selects a project-local state folder");
  assert.equal(existsSync(join(other, "tutor")), false);
});

test("stateRoot: LEARN_HOME wins, then the platform's per-user data folder", async () => {
  const { stateRoot } = await import("../src/state.mjs");
  assert.deepEqual(stateRoot({ env: { LEARN_HOME: "/srv/learn" }, platform: "linux", home: "/home/u" }), { dir: "/srv/learn", source: "LEARN_HOME" });
  assert.deepEqual(stateRoot({ env: {}, platform: "linux", home: "/home/u" }), { dir: "/home/u/.local/share/learn", source: "default" });
  assert.deepEqual(stateRoot({ env: { XDG_DATA_HOME: "/data" }, platform: "linux", home: "/home/u" }), { dir: "/data/learn", source: "default" });
  assert.deepEqual(stateRoot({ env: { XDG_DATA_HOME: "rel" }, platform: "linux", home: "/home/u" }), { dir: "/home/u/.local/share/learn", source: "default" });
  assert.deepEqual(stateRoot({ env: {}, platform: "darwin", home: "/Users/u" }), { dir: "/Users/u/Library/Application Support/learn", source: "default" });
  assert.deepEqual(stateRoot({ env: { LOCALAPPDATA: "C:\\Users\\u\\AppData\\Local" }, platform: "win32", home: "C:\\Users\\u" }), { dir: "C:\\Users\\u\\AppData\\Local\\learn", source: "default" });
  assert.deepEqual(stateRoot({ env: {}, platform: "win32", home: "C:\\Users\\u" }), { dir: "C:\\Users\\u\\AppData\\Local\\learn", source: "default" });
});

test("status reports the state folder and where it came from", async () => {
  const { status } = await import("../src/status.mjs");
  const { state } = folders();
  const saved = process.env.LEARN_HOME;
  process.env.LEARN_HOME = state;
  try {
    assert.deepEqual(status().state, { dir: state, source: "LEARN_HOME" });
  } finally {
    if (saved === undefined) delete process.env.LEARN_HOME; else process.env.LEARN_HOME = saved;
  }
});

// Found while applying the review: with --dir, `learn status` and learn_status under
// `learn mcp --dir` reported LEARN_HOME while every file went to the --dir folder.
test("status names the folder --dir selected, for the CLI and for learn mcp --dir", () => {
  const { proj, state, other } = folders();
  const env = envWith({ LEARN_HOME: state });
  const c = cli(other, env, ["status", "--dir", proj]);
  assert.equal(c.status, 0, c.stderr);
  assert.deepEqual(JSON.parse(c.stdout).state, { dir: proj, source: "--dir" });

  const input = JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "learn_status", arguments: {} } }) + "\n";
  const m = spawnSync(process.execPath, [join(SRC, "cli.mjs"), "mcp", "--dir", proj], { cwd: other, env, input, encoding: "utf8", timeout: 30000 });
  assert.equal(m.status, 0, m.stderr);
  const reply = JSON.parse(m.stdout.split("\n")[0]);
  assert.deepEqual(JSON.parse(reply.result.content[0].text).state, { dir: proj, source: "--dir" });

  const plain = cli(other, env, ["status"]);
  assert.deepEqual(JSON.parse(plain.stdout).state, { dir: state, source: "LEARN_HOME" }, "without --dir the report is unchanged");
});
