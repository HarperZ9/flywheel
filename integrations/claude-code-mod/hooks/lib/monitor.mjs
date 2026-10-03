// Talking to the Flywheel pre-action monitor (harness/preaction/hook_cli.py).
//
// The mod runs the monitor's own Claude Code hook adapter as a subprocess and
// hands it the same PreToolUse JSON a settings hook would receive on stdin.
// The adapter's contract (hook_cli.py on Flywheel main, read 2026-10-02):
//   exit 0, empty stdout      -> no decision; the call goes on to Claude Code
//   exit 2, permissionDecision -> held or blocked, with a reason on stdout/stderr
//   any other exit            -> not a monitor answer; this mod treats it as
//                                "monitor unavailable"
// The mod sends no permission_mode, so the adapter treats the call as one with
// nobody to ask and answers a hold with deny (it never answers "ask").
//
// Pure: builds argv and stdin, reads a finished run. No `$`, no I/O.

/** One-line Python bootstrap that imports the monitor from a source folder
 * given as argv[1], with -P -E so the working folder and PYTHON* variables
 * cannot shadow the import. The folder arrives as an argument, never as code. */
export const BOOT =
  "import sys,runpy; sys.path.insert(0, sys.argv.pop(1)); " +
  "runpy.run_module('harness.preaction.hook_cli', run_name='__main__')";

/** The monitor's argv for this config, or null when monitor_source is empty.
 * Importing `harness.preaction` from whatever Python finds first could load an
 * unrelated package named `harness`, so the source folder is required. */
export function monitorArgv(cfg) {
  if (!cfg.monitorSource) return null;
  const tail = ["claude-code", "--home", cfg.monitorHome, "--hold-mode", "deny",
    "--deadline", String(cfg.monitorDeadlineSeconds)];
  if (cfg.monitorOwnerConfig) tail.push("--owner-config", cfg.monitorOwnerConfig);
  return [cfg.python, "-P", "-E", "-c", BOOT, cfg.monitorSource, ...tail];
}

/** The PreToolUse event the adapter reads on stdin. */
export function monitorEvent({ tool, args, toolUseId, sessionId, cwd }) {
  return {
    hook_event_name: "PreToolUse",
    tool_name: tool,
    tool_input: args,
    tool_use_id: toolUseId ?? "",
    session_id: sessionId ?? "",
    cwd: cwd ?? "",
  };
}

function parseDecision(stdout) {
  const text = String(stdout ?? "").trim();
  if (!text) return null;
  try {
    const out = JSON.parse(text.split("\n")[0]);
    const h = out?.hookSpecificOutput;
    if (h && typeof h.permissionDecision === "string") {
      return { decision: h.permissionDecision, reason: String(h.permissionDecisionReason ?? "") };
    }
  } catch {
    // The adapter printed something other than its JSON: not a decision.
  }
  return { decision: "unparsed", reason: text.slice(0, 300) };
}

/**
 * Reads a finished run. Returns one of:
 *   { verdict: "pass" }
 *   { verdict: "held", reason, holdId }
 *   { verdict: "unavailable", reason }
 * A monitor "allow" is read as "pass": the mod then calls next(e), and Claude
 * Code's own permission check still runs. The mod never turns it into an
 * approval.
 */
export function readMonitorRun(run) {
  if (!run || typeof run.exitCode !== "number") {
    return { verdict: "unavailable", reason: "the monitor returned no exit code" };
  }
  const parsed = parseDecision(run.stdout);
  const stderr = String(run.stderr ?? "").trim();
  if (run.exitCode === 0 && parsed === null) return { verdict: "pass" };
  if (run.exitCode === 0 && parsed.decision === "allow") return { verdict: "pass" };
  if ((run.exitCode === 0 || run.exitCode === 2) && parsed && (parsed.decision === "deny" || parsed.decision === "ask")) {
    return held(parsed.reason || stderr);
  }
  if (run.exitCode === 2) return held((parsed && parsed.reason) || stderr || "held by the monitor");
  const why = stderr.split("\n").filter(Boolean).pop() || (parsed && parsed.reason) || "";
  return { verdict: "unavailable", reason: `monitor exited ${run.exitCode}${why ? ": " + why.slice(0, 240) : ""}` };
}

function held(reason) {
  const text = String(reason || "held by the monitor").slice(0, 600);
  const m = /hold_id=(h_[0-9a-f]+)/.exec(text);
  return { verdict: "held", reason: text, holdId: m ? m[1] : null };
}

/** The text Claude reads when a call is held. */
export function holdText(verdict, cfg) {
  const how = verdict.holdId
    ? ` Tell the user; they can decide it in their own terminal with: flywheel monitor approve ${verdict.holdId} --home ${cfg.monitorHome} .`
    : " Tell the user.";
  const reason = String(verdict.reason).replace(/[.\s]+$/, "");
  return `Flywheel held this call and did not run it: ${reason}.${how} Do not retry it or work around it unless the user asks you to.`;
}

/** The text Claude reads when the monitor could not answer and the mod fails closed. */
export function unavailableText(verdict) {
  return `Flywheel could not check this call, so it was not run (the mod fails closed): ${verdict.reason}. ` +
    "Tell the user the Flywheel monitor is unavailable. Do not retry it or work around it unless the user asks you to.";
}
