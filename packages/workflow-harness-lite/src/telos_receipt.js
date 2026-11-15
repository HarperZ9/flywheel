import { createHash } from "node:crypto";

const DEFAULT_TIMEOUT_MS = 15000;
const DEFAULT_OUTPUT_LIMIT = 4000;

function sha256(value) {
  return `sha256:${createHash("sha256").update(String(value)).digest("hex")}`;
}

function stableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableJson(item)).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function terminalStatus(report) {
  if (report.status === "pass") {
    return "ok";
  }
  if (report.status === "cancelled") {
    return "cancelled";
  }
  return "error";
}

function taskIdentity(task, index) {
  const command = String(task?.command || "");
  const cwd = task?.cwd ? String(task.cwd) : "";
  return {
    name: task?.name || `task-${index + 1}`,
    task_index: index,
    command_hash: sha256(command),
    cwd_hash: cwd ? sha256(cwd) : null,
    side_effect_class: task?.side_effect_class || task?.sideEffectClass || "unknown",
  };
}

function taskReceipt(result, task, index) {
  return {
    action_identity: taskIdentity(task, index),
    result: {
      status: result?.status || "unknown",
      code: Number.isFinite(result?.code) ? result.code : null,
      duration_ms: Number.isFinite(result?.durationMs) ? result.durationMs : 0,
    },
    output: {
      stdout_hash: sha256(result?.stdout || ""),
      stderr_hash: sha256(result?.stderr || ""),
      raw_output_included: false,
    },
  };
}

export function buildTelosReceipt(report, config = {}, options = {}) {
  const tasks = Array.isArray(config?.tasks) ? config.tasks : [];
  const results = Array.isArray(report?.tasks) ? report.tasks : [];
  const receipt = {
    schema: "project-telos.bounded-run-receipt/v1",
    generated: report?.generated || new Date().toISOString(),
    workflow: {
      name: report?.name || config?.name || "workflow",
      report_hash: sha256(stableJson(report || {})),
    },
    terminal_status: terminalStatus(report || {}),
    bounds: {
      guaranteed_termination: true,
      max_iterations: tasks.length,
      parallel: options.parallel !== false,
      per_task_timeout_ms: Number.isFinite(options.timeoutMs)
        ? options.timeoutMs
        : DEFAULT_TIMEOUT_MS,
      output_limit_chars: Number.isFinite(options.outputLimit)
        ? options.outputLimit
        : DEFAULT_OUTPUT_LIMIT,
    },
    counts: {
      total: Number.isFinite(report?.total) ? report.total : results.length,
      passed: Number.isFinite(report?.passed) ? report.passed : 0,
      failed: Number.isFinite(report?.failed) ? report.failed : 0,
      skipped: Number.isFinite(report?.skipped) ? report.skipped : 0,
    },
    tasks: results.map((result, index) => taskReceipt(result, tasks[index], index)),
    privacy: {
      raw_commands_included: false,
      raw_output_included: false,
      absolute_cwd_included: false,
      output_preview_required_for_interop: false,
    },
    next_actions: [
      "Attach this receipt to telos.loop.ledger or forum.ledger.summary.",
      "Use Crucible to verify any claim derived from task output hashes.",
    ],
  };
  receipt.receipt_hash = sha256(stableJson(receipt));
  return receipt;
}
