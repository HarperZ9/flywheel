// Flywheel mod: holds risky tool calls with the Flywheel pre-action monitor,
// writes a hash-chained receipt for every turn, and shows one status line.
//
// tool.call  (Bash, PowerShell, Edit, Write, MultiEdit, NotebookEdit):
//            a call the risk pre-filter flags goes to the monitor. A hold
//            becomes { deny }. A pass calls next(e), so Claude Code's own
//            permission check still runs. If the monitor cannot answer, the
//            call is denied with a visible reason unless on_unavailable=pass.
// turn.complete: appends one sealed JSON line per turn under .flywheel/.
// ui.render (AbovePrompt): one line, drawn above whatever later mods draw.
//
// This mod only adds holds. It registers no tool.check hook, never returns
// { decision }, never returns { result } for a tool call, and never sets
// `consent`. Its only answers to tool.call are next(e)'s own result or { deny }.
//
// The host reads on(...) and $.noun.method(...) from source, so they are
// spelled literally, and helpers that take $ are top-level functions here.

import { classify } from "./lib/rules.mjs";
import { monitorArgv, monitorEvent, readMonitorRun, holdText, unavailableText } from "./lib/monitor.mjs";
import { toolArgs, inputDigest, turnRecord, seal, lastHash, sha256Hex } from "./lib/receipt.mjs";
import { normalizeConfig, statusLine, resolveIn, safeName } from "./lib/config.mjs";

const EDIT_TOOLS = new Set(["Edit", "Write", "MultiEdit", "NotebookEdit"]);
const MAX_RECEIPT_BYTES = 3_500_000; // $.fs.write takes at most 4 MiB per file

let cfg = normalizeConfig({});
const st = freshState();

function freshState() {
  return { sessionId: "", cwd: "", counts: { held: 0, passed: 0, unavailable: 0 },
    lastHash: null, part: 0, buckets: new Map(), busy: false };
}

export function register(on, options) {
  cfg = normalizeConfig(options);

  on("session.start", async ($, e, next) => {
    const result = await next(e);
    await startSession($, e);
    return result;
  });

  // Fail closed: if the guard throws or times out, the .catch handler denies.
  on("tool.call", { tool: ["Bash", "PowerShell", "Edit", "Write", "MultiEdit", "NotebookEdit"] }, guard).catch(failed);

  on("turn.complete", async ($, e, next) => {
    const result = await next(e);
    try {
      await writeReceipt($, e);
    } catch (error) {
      $.ui.log(`Flywheel: receipt not written for turn ${e.turnId}: ${String(error?.message ?? error).slice(0, 200)}`);
    }
    return result;
  });

  on("ui.render", { component: "AbovePrompt" }, async ($, e, next) => drawBand($, e, next));
}

// ---- session ---------------------------------------------------------------

async function startSession($, e) {
  Object.assign(st, freshState());
  st.cwd = String((await $.session.cwd()) ?? e.cwd ?? "");
  st.sessionId = String((await $.session.id()) ?? "");
  try {
    // A resumed session continues its chain from the newest part file.
    while (await $.fs.exists(receiptPath(st.part + 1))) st.part += 1;
    const path = receiptPath(st.part);
    if (await $.fs.exists(path)) st.lastHash = lastHash(await $.fs.read(path));
  } catch {
    st.lastHash = null; // an unreadable earlier file starts a new chain, which verify shows
  }
  showStatus($);
}

function receiptPath(part) {
  const name = safeName(st.sessionId) + (part > 0 ? `.${part}` : "") + ".jsonl";
  return resolveIn(st.cwd, cfg.receiptsDir) + "/" + name;
}

// ---- tool.call -------------------------------------------------------------

async function guard($, e, next) {
  if (!st.cwd) st.cwd = String((await $.session.cwd()) ?? "");
  const args = toolArgs(e);
  const risk = classify(e.tool, args, st.cwd);
  const call = {
    tool_use_id: e.tool_use_id ?? "", tool: e.tool, input_sha256: await inputDigest(args),
    screened: risk.screen || cfg.screen === "all", rule_hits: risk.hits.map((h) => h.id),
    decision: "pass", monitor: null, outcome: "pending",
  };
  bucketFor(e.agentId).push(call);

  if (!call.screened) {
    call.decision = "pass-unscreened";
    st.counts.passed += 1;
    return runAndObserve($, e, next, call);
  }
  const verdict = await askMonitor($, e, args);
  call.monitor = { verdict: verdict.verdict, hold_id: verdict.holdId ?? null, reason: verdict.reason ?? null };

  if (verdict.verdict === "held") {
    call.decision = "held";
    call.outcome = "denied-by-mod";
    st.counts.held += 1;
    showStatus($);
    return { deny: holdText(verdict, { ...cfg, monitorHome: resolveIn(st.cwd, cfg.monitorHome) }) };
  }
  if (verdict.verdict === "unavailable") {
    st.counts.unavailable += 1;
    if (cfg.onUnavailable !== "pass") {
      call.decision = "unavailable-deny";
      call.outcome = "denied-by-mod";
      showStatus($);
      return { deny: unavailableText(verdict) };
    }
    call.decision = "unavailable-pass";
    $.ui.log(`Flywheel monitor unavailable, passing the call on (on_unavailable=pass): ${verdict.reason}`);
  } else {
    call.decision = "pass";
  }
  st.counts.passed += 1;
  return runAndObserve($, e, next, call);
}

async function askMonitor($, e, args) {
  const event = monitorEvent({ tool: e.tool, args, toolUseId: e.tool_use_id, sessionId: st.sessionId, cwd: st.cwd });
  const argv = monitorArgv({ ...cfg, monitorHome: resolveIn(st.cwd, cfg.monitorHome) });
  if (!argv) return { verdict: "unavailable", reason: "monitor_source is not set; set it to the folder that holds Flywheel's harness/ package" };
  let run;
  try {
    run = await $.process.run(argv, { cwd: st.cwd || undefined, stdin: JSON.stringify(event), timeoutMs: cfg.monitorTimeoutMs });
  } catch (error) {
    return { verdict: "unavailable", reason: `could not run ${argv[0]}: ${String(error?.message ?? error).slice(0, 200)}` };
  }
  return readMonitorRun(run);
}

// Passes the call on and records what came back. Returns next's result as is.
async function runAndObserve($, e, next, call) {
  const isEdit = EDIT_TOOLS.has(e.tool);
  const file = isEdit ? String(e.file_path ?? e.notebook_path ?? "") : "";
  if (isEdit && file) call.file = { path: file, before_sha256: await fileDigest($, file), after_sha256: null };
  const result = await next(e);
  call.outcome = result?.deny !== undefined ? "denied-downstream" : result?.isError ? "error" : "ran";
  if (call.file) call.file.after_sha256 = await fileDigest($, file);
  showStatus($);
  return result;
}

async function fileDigest($, path) {
  try {
    if (!(await $.fs.exists(path))) return null;
    return await sha256Hex(await $.fs.read(path));
  } catch {
    return "unreadable";
  }
}

async function failed($, e, next) {
  st.counts.unavailable += 1;
  const reason = `the Flywheel guard hook failed (${next.error?.kind ?? "error"})`;
  return { deny: unavailableText({ reason }) };
}

function bucketFor(agentId) {
  const key = agentId ?? "main";
  if (!st.buckets.has(key)) st.buckets.set(key, []);
  return st.buckets.get(key);
}

// ---- turn.complete ---------------------------------------------------------

async function writeReceipt($, e) {
  // A main turn and a subagent turn can end together; one writer at a time
  // keeps the chain linear. The check and the claim have no await between them.
  while (st.busy) await $.clock.sleep(20);
  st.busy = true;
  try {
    await sealAndAppend($, e);
  } finally {
    st.busy = false;
  }
}

async function sealAndAppend($, e) {
  const key = e.agentId ?? "main";
  const calls = st.buckets.get(key) ?? [];
  st.buckets.delete(key);
  const record = turnRecord({ sessionId: st.sessionId, turnId: e.turnId, agentId: e.agentId,
    reason: e.reason, isAborted: e.isAborted, endedAt: await $.clock.now(), calls });
  const sealed = await seal(record, st.lastHash);
  await appendLine($, JSON.stringify(sealed));
  st.lastHash = sealed.record_hash;
  showStatus($);
}

// $.fs.write replaces a file's content, so "append" is read, add one line,
// write. Each session writes its own file, and writeReceipt serializes writes.
async function appendLine($, line) {
  let path = receiptPath(st.part);
  let text = "";
  if (await $.fs.exists(path)) text = await $.fs.read(path);
  if (utf8Length(text) + utf8Length(line) + 1 > MAX_RECEIPT_BYTES) {
    st.part += 1;
    path = receiptPath(st.part);
    text = "";
  }
  try {
    await $.fs.write(path, text + line + "\n");
  } catch (error) {
    // The folder may not exist yet; create it with the configured Python, then retry once.
    const dir = path.slice(0, path.lastIndexOf("/"));
    await $.process.run([cfg.python, "-P", "-E", "-c", "import os,sys; os.makedirs(sys.argv[1], exist_ok=True)", dir], { timeoutMs: 10000 });
    await $.fs.write(path, text + line + "\n");
  }
}

function utf8Length(s) {
  return new TextEncoder().encode(s).length;
}

// ---- status line -----------------------------------------------------------

function showStatus($) {
  if (cfg.statusSite === "status") {
    $.ui.status(statusLine(st.counts, st.lastHash, cfg));
  } else if (cfg.statusSite === "band") {
    $.ui.invalidate("ui.render");
  }
}

async function drawBand($, e, next) {
  const seen = st.counts.held + st.counts.passed + st.counts.unavailable;
  if (cfg.statusSite !== "band" || (seen === 0 && !st.lastHash)) return next(e);
  const { Box, Text } = $.ui.resolve(e);
  const theirs = await next(e);
  const alarm = st.counts.held > 0 || st.counts.unavailable > 0;
  const line = Text({ key: "flywheel-status", color: alarm ? "yellow" : undefined, dimColor: !alarm,
    wrap: "truncate-end", children: statusLine(st.counts, st.lastHash, cfg) });
  return Box({ flexDirection: "column", children: [line, theirs] });
}
