// Runs the mod against the real Flywheel pre-action monitor (hook_cli.py from
// Flywheel main), as a subprocess, through a $.process.run built on Node's
// child_process. Needs Python and this repository's harness/ package
// (see README.md). Skips, visibly, when either is missing.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { register } from "../hooks/module.mjs";
import { load } from "./harness.mjs";
import { verifyChain } from "../hooks/lib/receipt.mjs";

// The Flywheel source this folder lives in: integrations/claude-code-mod/tests -> repo root.
const SRC = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..", "..");
const PY = process.env.FLYWHEEL_MOD_PYTHON || "python";
const ready = existsSync(join(SRC, "harness", "preaction", "hook_cli.py")) && spawnSync(PY, ["--version"]).status === 0;

function realApi(project, timings) {
  return {
    "session.cwd": async () => project,
    "session.id": async () => "integration-1",
    "clock.now": async () => Date.now(),
    "clock.sleep": (ms) => new Promise((r) => setTimeout(r, ms)),
    "ui.log": async () => {},
    "fs.exists": async (p) => existsSync(p),
    "fs.read": async (p) => readFileSync(p, "utf8"),
    "fs.write": async (p, text) => { mkdirSync(dirname(p), { recursive: true }); writeFileSync(p, text); },
    "process.run": async (argv, init = {}) => {
      const t0 = Date.now();
      const r = spawnSync(argv[0], argv.slice(1), { cwd: init.cwd, input: init.stdin, timeout: init.timeoutMs, encoding: "utf8" });
      timings.push(Date.now() - t0);
      if (r.error) throw r.error;
      return { exitCode: r.status ?? -1, stdout: r.stdout ?? "", stderr: r.stderr ?? "" };
    },
  };
}

async function bootReal(options) {
  const project = mkdtempSync(join(tmpdir(), "flywheel-mod-it-"));
  const timings = [];
  const eng = load(register, { python: PY, monitor_source: SRC, ...options }, realApi(project, timings));
  await eng.fire("session.start", { cwd: project, surface: "terminal" }, async () => ({}));
  const ran = [];
  const call = (input) => eng.fire("tool.call", input, async (e) => { ran.push(e); return { result: "ok", text: "ok" }; });
  return { project, eng, ran, call, timings };
}

test("real monitor: rm -rf / is held with a hold id; the tool never runs", { skip: !ready && "no Python or no Flywheel source" }, async (t) => {
  const b = await bootReal({});
  const out = await b.call({ tool: "Bash", tool_use_id: "toolu_it1", command: "rm -rf /" });
  assert.match(out.deny, /^Flywheel held this call and did not run it: held for owner review \(hold_id=h_[0-9a-f]{16}\)/);
  assert.equal(b.ran.length, 0);
  t.diagnostic(`monitor run took ${b.timings[0]} ms`);
});

test("real monitor: a plain command passes through to core when screen=all", { skip: !ready && "no Python or no Flywheel source" }, async (t) => {
  const b = await bootReal({ screen: "all" });
  const out = await b.call({ tool: "Bash", tool_use_id: "toolu_it2", command: "git status" });
  assert.deepEqual(out, { result: "ok", text: "ok" });
  assert.equal(b.ran.length, 1);
  t.diagnostic(`monitor run took ${b.timings[0]} ms`);
});

test("real monitor: writing .env is held under the credential rule", { skip: !ready && "no Python or no Flywheel source" }, async () => {
  const b = await bootReal({});
  const out = await b.call({ tool: "Write", tool_use_id: "toolu_it3", file_path: join(b.project, ".env"), content: "TOKEN=x" });
  assert.equal(typeof out.deny, "string");
  assert.equal(b.ran.length, 0);
});

test("real monitor: the receipt's input_sha256 is the monitor's own args digest for the call", { skip: !ready && "no Python or no Flywheel source" }, async () => {
  const b = await bootReal({});
  await b.call({ tool: "Bash", tool_use_id: "toolu_it4", command: "rm -rf /" });
  await b.eng.fire("turn.complete", { turnId: "it-turn", reason: "answer", isAborted: false }, async () => ({ text: "" }));
  const text = readFileSync(join(b.project, ".flywheel", "mod-receipts", "integration-1.jsonl"), "utf8");
  assert.equal((await verifyChain(text)).ok, true);
  const call = JSON.parse(text.trim()).calls[0];
  const records = readFileSync(join(b.project, ".flywheel", "monitor", "records.jsonl"), "utf8")
    .trim().split("\n").map((l) => JSON.parse(l));
  const mine = records.filter((r) => r.tool_use_id === "toolu_it4");
  assert.equal(mine.length, 1, "the monitor recorded the call under the same tool_use_id");
  assert.equal(mine[0].args.sha256, call.input_sha256);
  assert.equal(call.decision, "held");
});

test("real subprocess: a monitor source folder without Flywheel fails closed", { skip: !ready && "no Python" }, async () => {
  const b = await bootReal({ monitor_source: join(tmpdir(), "no-flywheel-here") });
  const out = await b.call({ tool: "Bash", tool_use_id: "toolu_it5", command: "rm -rf build" });
  assert.match(out.deny, /fails closed\): monitor exited 1: .*No module named 'harness/);
  assert.equal(b.ran.length, 0);
});
