// Path confinement for every id the MCP server and the CLI turn into a file name.
// Released 1.6.0 joined `sessionId` and `runId` into a path with no check, so an advisory tool
// call could overwrite a project's .claude/settings.json or read a file outside its folder.
// Every fixture here is local: temporary folders, planted files and links made by the test.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, symlinkSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { handle } from "../src/mcp.mjs";
import { main } from "../src/cli.mjs";

const SETTINGS = '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo user-hook"}]}]},"permissions":{"deny":["Bash(rm:*)"]}}';

function project() {
  const root = mkdtempSync(join(tmpdir(), "learn-escape-"));
  const proj = join(root, "project");
  mkdirSync(join(proj, ".claude"), { recursive: true });
  writeFileSync(join(proj, ".claude", "settings.json"), SETTINGS);
  return { root, proj };
}

const call = (name, args, dir) =>
  handle({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }, { dir });

// A tool failure is an MCP result with isError and the closed-code shape, not a JSON-RPC error.
function failure(res) {
  assert.equal(res.error, undefined, "a tool failure must not be a JSON-RPC protocol error");
  assert.equal(res.result.isError, true);
  const sc = res.result.structuredContent;
  assert.deepEqual(Object.keys(sc).sort(), ["code", "detail", "retryable", "setup"]);
  return sc;
}

test("learn_tutor_plan: sessionId '../.claude/settings' returns INVALID_ARGUMENT and the settings file is byte-identical", async () => {
  const { proj } = project();
  const res = await call("learn_tutor_plan", { sessionId: "../.claude/settings", topic: "t", objectives: ["x"] }, proj);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assert.equal(readFileSync(join(proj, ".claude", "settings.json"), "utf8"), SETTINGS);
});

test("learn_tutor_record: a traversing sessionId is refused and the target stays unchanged", async () => {
  const { proj } = project();
  const res = await call("learn_tutor_record", { sessionId: "../.claude/settings", objective: "x", correct: true }, proj);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assert.equal(readFileSync(join(proj, ".claude", "settings.json"), "utf8"), SETTINGS);
});

test("an absolute sessionId never writes outside the state folder", async () => {
  const { root, proj } = project();
  const victim = join(root, "victim");
  const res = await call("learn_tutor_plan", { sessionId: victim, objectives: ["x"] }, proj);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assert.equal(existsSync(victim + ".json"), false);
});

test("learn_verify and learn_receipt: a traversing runId cannot read a run file outside runs/", async () => {
  const { root, proj } = project();
  // A well-formed run file one level above the state folder; 1.6.0 read and verified it.
  writeFileSync(join(root, "outside.json"), JSON.stringify({ workflow: { course: "c", seal: "s" }, entries: [] }));
  for (const tool of ["learn_verify", "learn_receipt"]) {
    const res = await call(tool, { runId: "../../outside" }, proj);
    assert.equal(failure(res).code, "INVALID_ARGUMENT", tool);
  }
});

test("ids: leading dot, device names, over-long and non-string ids are refused; ordinary ids work", async () => {
  const { proj } = project();
  for (const bad of [".hidden", "..", "con", "NUL", "com1", "a/b", "a\\b", "x".repeat(65), "", 5, null]) {
    const res = await call("learn_tutor_plan", { sessionId: bad, objectives: ["x"] }, proj);
    assert.equal(failure(res).code, "INVALID_ARGUMENT", `sessionId ${JSON.stringify(bad)}`);
  }
  const ok = await call("learn_tutor_plan", { sessionId: "Week-1_calc.v2", objectives: ["x"] }, proj);
  assert.equal(ok.result.isError, undefined);
  assert.ok(existsSync(join(proj, "tutor", "Week-1_calc.v2.json")));
});

test("a tutor/ folder linked out of the state folder is refused, and nothing is written through it", async () => {
  const { root, proj } = project();
  const outside = join(root, "elsewhere");
  mkdirSync(outside);
  // A junction needs no privilege on Windows; elsewhere it is an ordinary directory symlink.
  symlinkSync(outside, join(proj, "tutor"), process.platform === "win32" ? "junction" : "dir");
  const res = await call("learn_tutor_plan", { sessionId: "s1", objectives: ["x"] }, proj);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assert.deepEqual(readdirSync(outside), []);
});

test("a session file that is itself a link to an outside file is refused", async (t) => {
  const { root, proj } = project();
  const target = join(root, "target.json");
  writeFileSync(target, "{}");
  mkdirSync(join(proj, "tutor"));
  try { symlinkSync(target, join(proj, "tutor", "s1.json"), "file"); }
  catch (e) { if (e.code === "EPERM") return t.skip("file symlinks need extra privilege on this Windows host"); throw e; }
  const res = await call("learn_tutor_plan", { sessionId: "s1", objectives: ["x"], replace: true }, proj);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assert.equal(readFileSync(target, "utf8"), "{}");
});

test("learn_tutor_plan refuses to overwrite an existing session unless replace is true", async () => {
  const { proj } = project();
  await call("learn_tutor_plan", { sessionId: "s1", objectives: ["x"] }, proj);
  await call("learn_tutor_record", { sessionId: "s1", objective: "x", correct: true }, proj);
  const again = await call("learn_tutor_plan", { sessionId: "s1", objectives: ["y"] }, proj);
  assert.equal(failure(again).code, "CONFLICT");
  const kept = JSON.parse(readFileSync(join(proj, "tutor", "s1.json"), "utf8"));
  assert.equal(kept.attempts.length, 1, "the practice log survives a second plan call");
  const replaced = await call("learn_tutor_plan", { sessionId: "s1", objectives: ["y"], replace: true }, proj);
  assert.equal(replaced.result.isError, undefined);
  assert.deepEqual(JSON.parse(readFileSync(join(proj, "tutor", "s1.json"), "utf8")).objectives, ["y"]);
});

test("CLI: traversing ids are refused for tutor, run and resume, and nothing lands outside", async () => {
  const { root, proj } = project();
  const wf = join(root, "wf.json");
  writeFileSync(wf, JSON.stringify({ adapter: "fake", course: "c", steps: [{ kind: "assess", label: "q" }] }));
  const cases = [
    ["tutor", "plan", "../../evil", "--objectives", "a"],
    ["tutor", "record", "../.claude/settings", "--objective", "a", "--correct", "true"],
    ["run", wf, "--id", "../../evil"],
    ["resume", "../../evil"],
    ["verify", "../outside"],
  ];
  for (const argv of cases) {
    const r = await main(argv, { dir: proj });
    assert.equal(r.code, 1, argv.join(" "));
    assert.match(r.out, /must be 1 to 64|outside the learn state folder/i, argv.join(" "));
  }
  assert.equal(existsSync(join(root, "evil.json")), false);
  assert.equal(readFileSync(join(proj, ".claude", "settings.json"), "utf8"), SETTINGS);
});

test("CLI: tutor plan refuses to overwrite an existing session unless --replace is given", async () => {
  const { proj } = project();
  await main(["tutor", "plan", "s1", "--objectives", "a"], { dir: proj });
  await main(["tutor", "record", "s1", "--objective", "a", "--correct", "true"], { dir: proj });
  const again = await main(["tutor", "plan", "s1", "--objectives", "b"], { dir: proj });
  assert.equal(again.code, 1);
  assert.match(again.out, /already exists/);
  const replaced = await main(["tutor", "plan", "s1", "--objectives", "b", "--replace"], { dir: proj });
  assert.equal(replaced.code, 0);
});

// A link whose target did not exist yet passed the check: realpath failed on it, the
// check fell back to the parent folder, and the write then followed the link and created the
// target outside the state folder. A link that cannot be resolved is now refused.
function danglingFileLink(t, link, target) {
  try { symlinkSync(target, link, "file"); return true; }
  catch (e) { if (e.code === "EPERM") { t.skip("file symlinks need extra privilege on this Windows host"); return false; } throw e; }
}

test("a dangling file link in the state folder is refused on every write path, and nothing is created outside", async (t) => {
  const { root, proj } = project();
  const outside = join(root, "outside");
  mkdirSync(outside);
  mkdirSync(join(proj, "tutor"));
  if (!danglingFileLink(t, join(proj, "tutor", "s1.json"), join(outside, "plan.json"))) return;
  const plan = await call("learn_tutor_plan", { sessionId: "s1", topic: "planted", objectives: ["x"] }, proj);
  assert.equal(failure(plan).code, "INVALID_ARGUMENT", "MCP learn_tutor_plan");

  await main(["tutor", "plan", "s2", "--objectives", "a"], { dir: proj });
  danglingFileLink(t, join(proj, "tutor", "s2.mastery.json"), join(outside, "mastery.json"));
  const tr = await main(["tutor", "receipt", "s2"], { dir: proj });
  assert.equal(tr.code, 1, "CLI tutor receipt");
  assert.match(tr.out, /outside the learn state folder/);

  const wf = join(root, "wf.json");
  writeFileSync(wf, JSON.stringify({ adapter: "fake", course: "c", steps: [{ kind: "navigate", target: "x" }, { kind: "complete" }] }));
  assert.equal((await main(["run", wf, "--id", "r1"], { dir: proj })).code, 0);
  danglingFileLink(t, join(proj, "runs", "r1.receipt.html"), join(outside, "receipt.html"));
  const rr = await main(["receipt", "r1"], { dir: proj });
  assert.equal(rr.code, 1, "CLI receipt");
  assert.equal(existsSync(join(proj, "runs", "r1.receipt.json")), false, "the receipt is refused whole, before any of its files is written");

  assert.deepEqual(readdirSync(outside), [], "nothing was created outside the state folder");
});

test("a tutor/ folder link whose target does not exist is refused with INVALID_ARGUMENT, and the target is never created", async () => {
  const { root, proj } = project();
  mkdirSync(join(root, "outside"));
  const target = join(root, "outside", "newdir");
  symlinkSync(target, join(proj, "tutor"), process.platform === "win32" ? "junction" : "dir");
  const res = await call("learn_tutor_plan", { sessionId: "s1", objectives: ["x"] }, proj);
  assert.equal(failure(res).code, "INVALID_ARGUMENT");
  assert.equal(existsSync(target), false);
});

// An id that starts with a hyphen looks like a flag (`--id --allow-cost`), so
// ids now start with a letter, a digit or an underscore.
test("an id that starts with a hyphen is refused over MCP and on the CLI", async () => {
  const { root, proj } = project();
  for (const bad of ["-x", "--allow-cost"]) {
    const res = await call("learn_tutor_plan", { sessionId: bad, objectives: ["x"] }, proj);
    assert.equal(failure(res).code, "INVALID_ARGUMENT", bad);
  }
  const wf = join(root, "wf.json");
  writeFileSync(wf, JSON.stringify({ adapter: "fake", course: "c", steps: [{ kind: "assess", label: "q" }] }));
  const r = await main(["run", wf, "--id", "--allow-cost"], { dir: proj });
  assert.equal(r.code, 1);
  assert.match(r.out, /must not start with a dot or a hyphen/);
  assert.equal(existsSync(join(proj, "runs")), false, "no run file was written");
});

// The same class for switches: a switch word given as another flag's value is that
// flag's value: `--topic --replace` is a topic, and the existing session is kept.
test("tutor plan --topic --replace keeps the existing session: the word is the topic, not the switch", async () => {
  const { proj } = project();
  await main(["tutor", "plan", "s1", "--objectives", "a"], { dir: proj });
  await main(["tutor", "record", "s1", "--objective", "a", "--correct", "true"], { dir: proj });
  const r = await main(["tutor", "plan", "s1", "--topic", "--replace", "--objectives", "b"], { dir: proj });
  assert.equal(r.code, 1);
  assert.match(r.out, /already exists/);
  assert.equal(JSON.parse(readFileSync(join(proj, "tutor", "s1.json"), "utf8")).attempts.length, 1, "the practice log survives");
});
