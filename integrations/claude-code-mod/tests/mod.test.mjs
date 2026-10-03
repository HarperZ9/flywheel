import { test } from "node:test";
import assert from "node:assert/strict";
import { boot, holdFailures, HOLD_RUN, PASS_RUN, MISSING_RUN } from "./setup.mjs";
import { verifyChain, inputDigest } from "../hooks/lib/receipt.mjs";
import { register as lazyRegister } from "./fixtures/lazy-mod.mjs";

const RISKY = { tool: "Bash", tool_use_id: "toolu_1", command: "rm -rf build" };
const SAFE = { tool: "Bash", tool_use_id: "toolu_2", command: "ls -la" };

test("false-success control: a monitor hold becomes { deny } and the tool never runs", async () => {
  const b = await boot({ monitor: () => HOLD_RUN });
  const failures = await holdFailures(b, RISKY);
  assert.deepEqual(failures, []);
  assert.equal(b.monitorCalls.length, 1, "the monitor was asked exactly once");
  const { value } = await b.toolCall({ ...RISKY, tool_use_id: "toolu_1b" });
  assert.match(value.deny, /^Flywheel held this call and did not run it: held for owner review/);
  assert.match(value.deny, /flywheel monitor approve h_0123456789abcdef --home \/work\/\.flywheel\/monitor/);
  assert.deepEqual(Object.keys(value), ["deny"]);
});

test("discrimination control: the same hold check fails on a mod that ignores the monitor", async () => {
  const lazy = await boot({ monitor: () => HOLD_RUN, mod: lazyRegister });
  const failures = await holdFailures(lazy, RISKY);
  assert.deepEqual(failures, ["result is not { deny }", "the tool ran after a hold"]);
});

test("a monitor pass calls next(e) and returns core's result object unchanged", async () => {
  const b = await boot({ monitor: () => PASS_RUN });
  const { value, coreResult } = await b.toolCall(RISKY);
  assert.equal(value, coreResult, "same object, so Claude reads what the tool returned");
  assert.equal(b.core.runs.length, 1);
  assert.equal(b.core.runs[0].command, "rm -rf build");
});

test("a call the pre-filter does not flag skips the monitor in screen=rules", async () => {
  const b = await boot({ monitor: () => HOLD_RUN });
  const { value, coreResult } = await b.toolCall(SAFE);
  assert.equal(value, coreResult);
  assert.equal(b.monitorCalls.length, 0);
});

test("screen=all sends an unflagged call to the monitor too", async () => {
  const b = await boot({ options: { screen: "all" }, monitor: () => HOLD_RUN });
  const { value } = await b.toolCall(SAFE);
  assert.equal(typeof value.deny, "string");
  assert.equal(b.monitorCalls.length, 1);
});

test("the monitor gets the PreToolUse event on stdin with the call's arguments", async () => {
  const b = await boot({ options: { monitor_source: "/src/flywheel" }, monitor: () => PASS_RUN });
  await b.toolCall(RISKY);
  const { argv, init } = b.monitorCalls[0];
  assert.deepEqual(argv.slice(0, 4), ["python", "-P", "-E", "-c"]);
  assert.equal(argv[5], "/src/flywheel");
  assert.deepEqual(argv.slice(6, 11), ["claude-code", "--home", "/work/.flywheel/monitor", "--hold-mode", "deny"]);
  const event = JSON.parse(init.stdin);
  assert.deepEqual(event, { hook_event_name: "PreToolUse", tool_name: "Bash", tool_input: { command: "rm -rf build" },
    tool_use_id: "toolu_1", session_id: "sess-1", cwd: "/work" });
  assert.equal("permission_mode" in event, false, "no permission mode, so the monitor never answers ask");
});

test("fail closed: a monitor that cannot start denies with a visible reason", async () => {
  const b = await boot({ monitor: () => { throw new Error("spawn python ENOENT"); } });
  const { value } = await b.toolCall(RISKY);
  assert.match(value.deny, /^Flywheel could not check this call, so it was not run \(the mod fails closed\): could not run python: spawn python ENOENT/);
  assert.equal(b.core.runs.length, 0);
});

test("fail closed: a monitor that is not installed (exit 1) denies", async () => {
  const b = await boot({ monitor: () => MISSING_RUN });
  const { value } = await b.toolCall(RISKY);
  assert.match(value.deny, /monitor exited 1: ModuleNotFoundError: No module named 'harness'/);
  assert.equal(b.core.runs.length, 0);
});

test("fail open only when configured: on_unavailable=pass runs the call and logs why", async () => {
  const b = await boot({ options: { on_unavailable: "pass" }, monitor: () => MISSING_RUN });
  const { value, coreResult } = await b.toolCall(RISKY);
  assert.equal(value, coreResult);
  assert.equal(b.logs.length, 1);
  assert.match(b.logs[0], /^Flywheel monitor unavailable, passing the call on \(on_unavailable=pass\)/);
});

test("fail open does not cover a hold: on_unavailable=pass still denies a held call", async () => {
  const b = await boot({ options: { on_unavailable: "pass" }, monitor: () => HOLD_RUN });
  assert.deepEqual(await holdFailures(b, RISKY), []);
});

test("an unknown on_unavailable value falls back to deny", async () => {
  const b = await boot({ options: { on_unavailable: "yes please" }, monitor: () => MISSING_RUN });
  const { value } = await b.toolCall(RISKY);
  assert.equal(typeof value.deny, "string");
});

test("the .catch handler denies when the guard itself throws", async () => {
  const b = await boot({ monitor: () => PASS_RUN });
  // Make the guard throw before next: a call whose arguments cannot be hashed.
  const bad = { tool: "Bash", tool_use_id: "toolu_x", command: "rm -rf x" };
  b.eng.calls.length = 0;
  const original = globalThis.crypto.subtle.digest;
  globalThis.crypto.subtle.digest = async () => { throw new Error("digest failed"); };
  try {
    const { value } = await b.toolCall(bad);
    assert.match(value.deny, /the Flywheel guard hook failed \(throw\)/);
    assert.equal(b.core.runs.length, 0);
  } finally {
    globalThis.crypto.subtle.digest = original;
  }
});

test("never approves: across every path, a tool.call answer is core's own result or exactly { deny }", async () => {
  const scenarios = [
    { monitor: () => HOLD_RUN }, { monitor: () => PASS_RUN }, { monitor: () => MISSING_RUN },
    { monitor: () => { throw new Error("x"); } }, { options: { on_unavailable: "pass" }, monitor: () => MISSING_RUN },
    { monitor: () => ({ exitCode: 0, stdout: JSON.stringify({ hookSpecificOutput: { permissionDecision: "allow" } }), stderr: "" }) },
    { options: { screen: "all" }, monitor: () => PASS_RUN },
  ];
  const inputs = [RISKY, SAFE,
    { tool: "Write", tool_use_id: "w1", file_path: "/work/.env", content: "A=1" },
    { tool: "Edit", tool_use_id: "e1", file_path: "/work/src/a.js", old_string: "a", new_string: "b" },
    { tool: "PowerShell", tool_use_id: "p1", command: "Remove-Item -Recurse -Force C:/x" }];
  let checked = 0;
  for (const s of scenarios) {
    const b = await boot(s);
    for (const input of inputs) {
      const { value, coreResult } = await b.toolCall(input);
      const isCore = value === coreResult;
      const isDeny = value && Object.keys(value).length === 1 && typeof value.deny === "string";
      assert.ok(isCore || isDeny, `answer for ${input.tool} was neither core's result nor { deny }: ${JSON.stringify(value)}`);
      checked += 1;
    }
    for (const r of b.eng.returns.filter((x) => x.event === "tool.call")) {
      assert.equal(r.value?.decision, undefined, "no { decision } from a tool.call hook");
      assert.ok(r.fromNext || Object.keys(r.value).join() === "deny", "only next's result or { deny }");
    }
    assert.deepEqual([...new Set(b.eng.events())].sort(), ["session.start", "tool.call", "turn.complete", "ui.render"]);
    assert.ok(!b.monitorCalls.some((c) => JSON.parse(c.init.stdin).consent !== undefined));
  }
  assert.equal(checked, scenarios.length * inputs.length);
});

test("turn.complete writes one sealed receipt line that verifies and records the hold", async () => {
  const b = await boot({ monitor: (argv, init) => (JSON.parse(init.stdin).tool_input.command?.includes("rm") ? HOLD_RUN : PASS_RUN) });
  await b.toolCall(RISKY);
  await b.toolCall(SAFE);
  await b.toolCall({ tool: "Write", tool_use_id: "toolu_w", file_path: "/work/notes.md", content: "hello" });
  await b.turnComplete();
  const text = b.fs.files.get("/work/.flywheel/mod-receipts/sess-1.jsonl");
  assert.ok(text, "receipt file exists at the session's path");
  const lines = text.trim().split("\n");
  assert.equal(lines.length, 1);
  const rec = JSON.parse(lines[0]);
  assert.deepEqual(rec.counts, { seen: 3, screened: 1, held: 1, passed: 2, unavailable: 0 });
  assert.equal(rec.calls[0].decision, "held");
  assert.equal(rec.calls[0].monitor.hold_id, "h_0123456789abcdef");
  assert.equal(rec.calls[0].input_sha256, await inputDigest({ command: "rm -rf build" }));
  assert.equal(rec.calls[2].file.before_sha256, null);
  assert.equal(rec.calls[2].file.after_sha256, "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824");
  assert.equal(rec.prev_hash, null);
  assert.deepEqual(await verifyChain(text), { ok: true, count: 1, problems: [] });
});

test("receipts chain across turns and keep subagent calls in their own turn", async () => {
  const b = await boot({ monitor: () => PASS_RUN });
  await b.toolCall({ ...SAFE, agentId: "agent-7" });
  await b.toolCall(SAFE);
  await b.turnComplete({ turnId: "sub-1", agentId: "agent-7" });
  await b.turnComplete({ turnId: "turn-2" });
  const text = b.fs.files.get("/work/.flywheel/mod-receipts/sess-1.jsonl");
  const [sub, main] = text.trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(sub.agent_id, "agent-7");
  assert.equal(sub.calls.length, 1);
  assert.equal(main.agent_id, null);
  assert.equal(main.calls.length, 1);
  assert.equal(main.prev_hash, sub.record_hash);
  assert.equal((await verifyChain(text)).ok, true);
});

test("a receipt with no tool calls is still written for the turn", async () => {
  const b = await boot();
  await b.turnComplete({ turnId: "quiet" });
  const rec = JSON.parse(b.fs.files.get("/work/.flywheel/mod-receipts/sess-1.jsonl"));
  assert.equal(rec.turn_id, "quiet");
  assert.deepEqual(rec.calls, []);
});

test("the band line keeps what later mods draw and shows counts and the receipt hash", async () => {
  const b = await boot({ monitor: () => HOLD_RUN });
  const theirs = { type: "Text", props: { children: "another mod" } };
  const idle = await b.eng.fire("ui.render", { component: "AbovePrompt", props: {}, surface: "terminal", requestId: "x" }, async () => theirs);
  assert.equal(idle, theirs, "nothing to show yet: pass through");
  await b.toolCall(RISKY);
  await b.turnComplete();
  const drawn = await b.eng.fire("ui.render", { component: "AbovePrompt", props: {}, surface: "terminal", requestId: "x" }, async () => theirs);
  assert.equal(drawn.type, "Box");
  const [line, kept] = drawn.props.children;
  assert.equal(kept, theirs);
  assert.match(line.props.children, /^Flywheel {2}held 1 {2}passed 0 {2}·  receipt [0-9a-f]{12}$/);
});

test("status_site=status uses $.ui.status and leaves the band alone", async () => {
  const b = await boot({ options: { status_site: "status" }, monitor: () => HOLD_RUN });
  await b.toolCall(RISKY);
  assert.match(b.statuses.at(-1), /^Flywheel {2}held 1 {2}passed 0/);
  const theirs = { type: "Text", props: {} };
  const drawn = await b.eng.fire("ui.render", { component: "AbovePrompt", props: {} }, async () => theirs);
  assert.equal(drawn, theirs);
});

test("Read and other unguarded tools never reach the guard", async () => {
  const b = await boot({ options: { screen: "all" }, monitor: () => HOLD_RUN });
  const { value, coreResult } = await b.toolCall({ tool: "Read", tool_use_id: "r1", file_path: "/work/.env" });
  assert.equal(value, coreResult);
  assert.equal(b.monitorCalls.length, 0);
});

test("two turns ending at once still produce a linear chain", async () => {
  const b = await boot({ monitor: () => PASS_RUN });
  await b.toolCall({ ...SAFE, agentId: "agent-1" });
  await b.toolCall(SAFE);
  await Promise.all([b.turnComplete({ turnId: "sub", agentId: "agent-1" }), b.turnComplete({ turnId: "main" })]);
  const text = b.fs.files.get("/work/.flywheel/mod-receipts/sess-1.jsonl");
  assert.equal(text.trim().split("\n").length, 2);
  assert.deepEqual(await verifyChain(text), { ok: true, count: 2, problems: [] });
});

test("a resumed session links its first new receipt to the last one on disk", async () => {
  const first = await boot();
  await first.turnComplete({ turnId: "before" });
  const onDisk = first.fs.files.get("/work/.flywheel/mod-receipts/sess-1.jsonl");
  const prior = JSON.parse(onDisk.trim()).record_hash;
  const again = await boot({ files: { "/work/.flywheel/mod-receipts/sess-1.jsonl": onDisk } });
  await again.turnComplete({ turnId: "after" });
  const text = again.fs.files.get("/work/.flywheel/mod-receipts/sess-1.jsonl");
  const lines = text.trim().split("\n").map((l) => JSON.parse(l));
  assert.equal(lines.length, 2);
  assert.equal(lines[1].prev_hash, prior);
  assert.equal((await verifyChain(text)).ok, true);
});

test("an empty monitor_source fails closed and never starts a monitor", async () => {
  const b = await boot({ options: { monitor_source: "", screen: "all" }, monitor: () => PASS_RUN });
  const { value } = await b.toolCall({ tool: "Bash", input: { command: "ls" } });
  assert.equal(typeof value.deny, "string");
  assert.match(value.deny, /monitor_source is not set/);
  assert.equal(b.monitorCalls.length, 0);
  assert.equal(b.core.runs.length, 0);
});
