// Path arguments over MCP. Released 1.6.0 read any file named by workflowPath,
// packetPath or file, and a JSON parse failure echoed the first characters of the file back to
// the model ("FAKE_SECRE"...). Paths now resolve inside the state folder, workflows and packets
// can be passed inline, and failures carry a fixed detail with no file bytes and no built path.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs, { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { handle } from "../src/mcp.mjs";

const PLANTED = "FAKE_SECRET_VALUE_0123456789";

function layout() {
  const root = mkdtempSync(join(tmpdir(), "learn-mcp-paths-"));
  const state = join(root, "state");
  mkdirSync(state);
  const secret = join(root, "secret.txt");
  writeFileSync(secret, PLANTED + "\n");
  return { root, state, secret };
}

const call = (name, args, dir, id = 1) =>
  handle({ jsonrpc: "2.0", id, method: "tools/call", params: { name, arguments: args } }, { dir });

function failure(res) {
  assert.equal(res.error, undefined, "a tool failure must not be a JSON-RPC protocol error");
  assert.equal(res.result.isError, true);
  return res.result.structuredContent;
}

// Nothing from the file and no path the server built may reach the model. The content text is
// checked on its own as well: inside the whole reply it is escaped a second time, so a Windows
// path with backslashes would not match there.
function assertNoLeak(res, ...paths) {
  const wires = [JSON.stringify(res), ...(res.result?.content ?? []).map((c) => c.text)];
  for (const wire of wires) {
    assert.ok(!wire.includes("FAKE_SECRE"), "file bytes leaked into the reply");
    for (const p of paths) assert.ok(!wire.includes(JSON.stringify(p).slice(1, -1)), "a built path leaked into the reply");
  }
}

// Every node:fs call whose path argument contains `marker`, while `fn` runs. The functions are
// swapped on the fs object and pushed to the ESM bindings, then restored.
const FS_PATH_CALLS = ["realpathSync", "lstatSync", "statSync", "existsSync", "readFileSync", "openSync", "readlinkSync", "accessSync", "readdirSync", "mkdirSync", "writeFileSync"];
async function fsCallsNaming(marker, fn) {
  const saved = {};
  const seen = [];
  const spy = (orig) => function (p, ...rest) {
    if (String(p).includes(marker)) seen.push(String(p));
    return orig.call(this, p, ...rest);
  };
  for (const n of FS_PATH_CALLS) { saved[n] = fs[n]; fs[n] = spy(saved[n]); }
  fs.realpathSync.native = spy(saved.realpathSync.native);
  syncBuiltinESMExports();
  try {
    return { result: await fn(), seen };
  } finally {
    for (const n of FS_PATH_CALLS) fs[n] = saved[n];
    syncBuiltinESMExports();
  }
}

const WORKFLOW = { adapter: "fake", course: "c", steps: [{ kind: "navigate", target: "x" }, { kind: "assess", label: "q" }] };

test("learn_tutor_prooflesson: packetPath to a text file outside the state folder returns INVALID_ARGUMENT with no file bytes", async () => {
  const { state, secret } = layout();
  const res = await call("learn_tutor_prooflesson", { packetPath: secret }, state);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assertNoLeak(res, secret);
});

test("learn_tutor_prooflesson: a non-JSON file inside the state folder returns a fixed detail with no file bytes", async () => {
  const { state } = layout();
  writeFileSync(join(state, "notes.txt"), PLANTED);
  const res = await call("learn_tutor_prooflesson", { packetPath: "notes.txt" }, state);
  const sc = failure(res);
  assert.equal(sc.code, "INVALID_ARGUMENT");
  assert.match(sc.detail, /not valid JSON/);
  assertNoLeak(res, join(state, "notes.txt"));
});

test("learn_dry_run: workflowPath outside the state folder is refused; inline and inside-folder workflows run", async () => {
  const { root, state, secret } = layout();
  writeFileSync(join(root, "wf.json"), JSON.stringify(WORKFLOW));
  for (const p of [secret, join(root, "wf.json"), "../wf.json"]) {
    const res = await call("learn_dry_run", { workflowPath: p }, state);
    assert.equal(failure(res).code, "INVALID_ARGUMENT", p);
    assertNoLeak(res, p);
  }
  const inline = await call("learn_dry_run", { workflow: WORKFLOW }, state);
  assert.equal(JSON.parse(inline.result.content[0].text).status, "halted-assess");
  mkdirSync(join(state, "workflows"));
  writeFileSync(join(state, "workflows", "wf.json"), JSON.stringify(WORKFLOW));
  const inside = await call("learn_dry_run", { workflowPath: "workflows/wf.json" }, state);
  assert.equal(JSON.parse(inside.result.content[0].text).status, "halted-assess");
});

test("learn_dry_run: a non-JSON workflow file gives a fixed detail, never its first characters", async () => {
  const { state } = layout();
  writeFileSync(join(state, "bad.json"), PLANTED);
  const res = await call("learn_dry_run", { workflowPath: "bad.json" }, state);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assertNoLeak(res, join(state, "bad.json"));
});

test("learn_tutor_reverify: file outside the state folder is refused; a malformed receipt inside yields no file bytes", async () => {
  const { state, secret } = layout();
  const out = await call("learn_tutor_reverify", { sessionId: "s1", file: secret }, state);
  assert.equal(failure(out).code, "INVALID_ARGUMENT");
  assertNoLeak(out, secret);
  writeFileSync(join(state, "r.json"), PLANTED);
  const inside = await call("learn_tutor_reverify", { sessionId: "s1", file: "r.json" }, state);
  assert.equal(inside.result.isError, undefined);
  assert.equal(JSON.parse(inside.result.content[0].text).results[0].verdict, "UNVERIFIED");
  assertNoLeak(inside);
});

test("learn_verify on a missing run returns NOT_FOUND without the path the server built", async () => {
  const { state } = layout();
  const res = await call("learn_verify", { runId: "nosuch" }, state);
  assert.equal(failure(res).code, "NOT_FOUND");
  assertNoLeak(res, join(state, "runs", "nosuch.json"), state);
});

test("an unknown tool is a JSON-RPC -32602 error; a missing session is NOT_FOUND", async () => {
  const { state } = layout();
  const unknown = await call("learn_nope", {}, state);
  assert.equal(unknown.error.code, -32602);
  const missing = await call("learn_tutor_mastery", { sessionId: "nosuch" }, state);
  assert.equal(failure(missing).code, "NOT_FOUND");
});

test("a failure the server did not anticipate is INTERNAL with a fixed detail", async () => {
  const { state } = layout();
  mkdirSync(join(state, "tutor"));
  writeFileSync(join(state, "tutor", "s1.json"), PLANTED); // a corrupted session file
  const res = await call("learn_tutor_mastery", { sessionId: "s1" }, state);
  assert.equal(failure(res).code, "INTERNAL");
  assertNoLeak(res, join(state, "tutor", "s1.json"));
});

// The containment check resolved a caller's path through realpath before refusing it,
// and on Windows resolving \host\share opens an SMB (or WebDAV) connection to that host and
// offers the user's credentials. A path outside the state folder is now refused on its text, so
// no filesystem call ever names it. The hosts here are loopback and the shares do not exist.
test("a path argument outside the state folder is refused before any filesystem call names it (no SMB or WebDAV touch)", async () => {
  const { state } = layout();
  const MARK = "learn-no-such-share";
  const win = (...parts) => "\\\\" + parts.join("\\"); // \\a\b\c
  const paths = process.platform === "win32"
    ? [win("127.0.0.1", MARK, "x.json"), `//127.0.0.1/${MARK}/x.json`, win("127.0.0.1@8765", "DavWWWRoot", MARK + ".json"), win("?", "UNC", "127.0.0.1", MARK, "x.json")]
    : [`//127.0.0.1/${MARK}/x.json`, `/${MARK}/x.json`];
  for (const [tool, key] of [["learn_dry_run", "workflowPath"], ["learn_tutor_prooflesson", "packetPath"], ["learn_tutor_reverify", "file"]]) {
    for (const p of paths) {
      const args = { [key]: p, ...(tool === "learn_tutor_reverify" ? { sessionId: "s1" } : {}) };
      const { result: res, seen } = await fsCallsNaming(MARK, () => call(tool, args, state));
      assert.equal(failure(res).code, "INVALID_ARGUMENT", `${tool} ${p}`);
      assert.deepEqual(seen, [], `${tool} reached the filesystem with ${p} before refusing it`);
    }
  }
  // Control: the spy sees calls. A missing file inside the folder is looked up, then NOT_FOUND.
  const { result: inside, seen } = await fsCallsNaming(MARK, () => call("learn_dry_run", { workflowPath: MARK + ".json" }, state));
  assert.equal(failure(inside).code, "NOT_FOUND");
  assert.ok(seen.length > 0, "the filesystem spy recorded nothing, so the check above proves nothing");
});

// A successful reverify named each receipt by the absolute path the server built.
// Files are now named relative to the state folder, the same form the caller passes in `file`.
test("learn_tutor_reverify names each receipt by its place in the state folder, never by the absolute path", async () => {
  const { state } = layout();
  const { newSession, recordAttempt, masteryReceipt } = await import("../src/tutor/tutor.mjs");
  const s = newSession({ topic: "t", objectives: ["x"] });
  for (const q of ["q1", "q2", "q3"]) recordAttempt(s, { objective: "x", prompt: q, answer: "a", correct: true });
  const receipt = JSON.stringify(masteryReceipt(s));
  mkdirSync(join(state, "tutor"));
  writeFileSync(join(state, "tutor", "s1.mastery.json"), receipt);
  writeFileSync(join(state, "r.json"), receipt);
  const all = await call("learn_tutor_reverify", { sessionId: "s1" }, state);
  const one = await call("learn_tutor_reverify", { sessionId: "s1", file: "r.json" }, state);
  const files = (res) => JSON.parse(res.result.content[0].text).results.map((r) => [r.file, r.verdict]);
  assert.deepEqual(files(all), [["tutor/s1.mastery.json", "VERIFIED"]]);
  assert.deepEqual(files(one), [["r.json", "VERIFIED"]]);
  for (const res of [all, one]) assertNoLeak(res, state);
});
