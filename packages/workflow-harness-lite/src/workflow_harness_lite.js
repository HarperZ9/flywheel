import { exec as execCallback } from "node:child_process";
import { promisify } from "node:util";
export { buildTelosReceipt } from "./telos_receipt.js";
const exec = promisify(execCallback);
const OUTPUT_PREVIEW_LIMIT = 4000;
const SECRET_REPLACEMENTS = [
  [/-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----/g, "<redacted-secret>"],
  [/\bAKIA[0-9A-Z]{16}\b/g, "<redacted-secret>"],
  [/\bASIA[0-9A-Z]{16}\b/g, "<redacted-secret>"],
  [/\bghp_[A-Za-z0-9_]{20,}\b/g, "<redacted-secret>"],
  [/\bgithub_pat_[A-Za-z0-9_]{20,}\b/g, "<redacted-secret>"],
  [/\bsk-[A-Za-z0-9_-]{20,}\b/g, "<redacted-secret>"],
  [/\b(bearer|token|api[_-]?key|password|secret)\s*[:=]\s*\S+/gi, "$1=<redacted-secret>"],
];

export function sanitizeOutput(value, limit = OUTPUT_PREVIEW_LIMIT) {
  const maxLength = Number.isFinite(limit) ? Math.max(0, limit) : OUTPUT_PREVIEW_LIMIT;
  let text = String(value || "").replace(/\0/g, " ");
  for (const [pattern, replacement] of SECRET_REPLACEMENTS) {
    text = text.replace(pattern, replacement);
  }
  text = text.trim();
  if (text.length <= maxLength) {
    return text;
  }
  const suffix = "\n[truncated]";
  return text.slice(0, Math.max(0, maxLength - suffix.length)).trimEnd() + suffix;
}

export async function runTask(task, options = {}) {
  const command = String(task?.command || "").trim();
  const cwd = task?.cwd;
  const timeout = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 15000;
  const outputLimit = Number.isFinite(options.outputLimit)
    ? options.outputLimit
    : OUTPUT_PREVIEW_LIMIT;

  if (!command) {
    return {
      name: task?.name || "unnamed",
      status: "skip",
      code: 0,
      durationMs: 0,
      stdout: "",
      stderr: "empty command",
    };
  }

  const start = Date.now();
  try {
    const result = await exec(command, {
      cwd: cwd || process.cwd(),
      timeout,
      shell: true,
      maxBuffer: 1024 * 1024,
      windowsHide: true,
    });

    return {
      name: task.name || "unnamed",
      status: "pass",
      code: 0,
      durationMs: Date.now() - start,
      stdout: sanitizeOutput(result.stdout, outputLimit),
      stderr: sanitizeOutput(result.stderr, outputLimit),
    };
  } catch (error) {
    return {
      name: task.name || "unnamed",
      status: "fail",
      code: error.code || 1,
      durationMs: Date.now() - start,
      stdout: sanitizeOutput(error.stdout, outputLimit),
      stderr: sanitizeOutput(error.stderr || error.message, outputLimit),
    };
  }
}

export async function runTasks(tasks, options = {}) {
  if (options.parallel) {
    return Promise.all(tasks.map((task) => runTask(task, options)));
  }

  const results = [];
  for (const task of tasks) {
    results.push(await runTask(task, options));
  }
  return results;
}

export async function runWorkflow(config, options = {}) {
  const tasks = Array.isArray(config?.tasks) ? config.tasks : [];
  const started = Date.now();
  const taskResults = await runTasks(tasks, options);
  const passed = taskResults.filter((entry) => entry.status === "pass").length;
  const failed = taskResults.filter((entry) => entry.status === "fail").length;

  return {
    name: config?.name || "workflow",
    status: failed === 0 ? "pass" : "fail",
    generated: new Date().toISOString(),
    durationMs: Date.now() - started,
    total: taskResults.length,
    passed,
    failed,
    skipped: taskResults.filter((entry) => entry.status === "skip").length,
    tasks: taskResults,
  };
}
