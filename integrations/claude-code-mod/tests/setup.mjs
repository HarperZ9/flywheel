// Shared setup: boots the mod in the stand-in runtime with a scripted monitor.
import { register } from "../hooks/module.mjs";
import { load, memoryFs } from "./harness.mjs";

export const HOLD_RUN = {
  exitCode: 2,
  stdout: JSON.stringify({ hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny",
    permissionDecisionReason: "held for owner review (hold_id=h_0123456789abcdef); continue with other work or wait" } }),
  stderr: "held for owner review (hold_id=h_0123456789abcdef); continue with other work or wait",
};
export const PASS_RUN = { exitCode: 0, stdout: "", stderr: "" };
export const MISSING_RUN = { exitCode: 1, stdout: "", stderr: "Traceback...\nModuleNotFoundError: No module named 'harness'" };

/**
 * Boots the mod. `monitor(argv, init)` answers $.process.run, or throws to
 * stand for a monitor that cannot start. Returns helpers.
 */
export async function boot({ options = {}, monitor = () => PASS_RUN, files = {}, mod = register } = {}) {
  const fs = memoryFs(files);
  const monitorCalls = [];
  const logs = [];
  const statuses = [];
  const api = {
    ...fs.api,
    "session.cwd": async () => "/work",
    "session.id": async () => "sess-1",
    "clock.now": async () => 1_000,
    "clock.sleep": () => new Promise((r) => setTimeout(r, 1)),
    "ui.log": async (text) => { logs.push(text); },
    "ui.status": async (text) => { statuses.push(text); },
    "process.run": async (argv, init) => {
      monitorCalls.push({ argv, init });
      return monitor(argv, init);
    },
  };
  const eng = load(mod, { monitor_source: "/src/flywheel", ...options }, api);
  await eng.fire("session.start", { cwd: "/work", surface: "terminal" }, async () => ({}));
  const core = { runs: [] };
  async function toolCall(input) {
    const coreResult = { result: "ok", text: "ok", ref: core.runs.length + 1 };
    const value = await eng.fire("tool.call", input, async (e) => {
      core.runs.push(e);
      if (e.tool === "Write") fs.files.set(String(e.file_path), e.content);
      return coreResult;
    });
    return { value, coreResult };
  }
  async function turnComplete(extra = {}) {
    return eng.fire("turn.complete",
      { turnId: "turn-1", answer: "done", durationMs: 5, isAborted: false, reason: "answer", ...extra },
      async () => ({ text: "" }));
  }
  return { eng, fs, core, monitorCalls, logs, statuses, toolCall, turnComplete };
}

/**
 * The hold check the false-success control runs: given a booted mod whose
 * monitor says hold, a risky call must come back as { deny } and must never
 * reach core. Returns a list of failures (empty means the mod held).
 */
export async function holdFailures(booted, input) {
  const failures = [];
  const { value } = await booted.toolCall(input);
  if (!value || typeof value.deny !== "string") failures.push("result is not { deny }");
  if (booted.core.runs.length !== 0) failures.push("the tool ran after a hold");
  return failures;
}
