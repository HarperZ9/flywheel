import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { runWorkflow, buildTelosReceipt } from "../src/workflow_harness_lite.js";

test("runWorkflow marks pass", async () => {
  const report = await runWorkflow(
    {
      name: "smoke",
      tasks: [
        { name: "ok", command: "node -e \"console.log('ok')\"" },
      ],
    },
    { parallel: true, timeoutMs: 10000 },
  );
  assert.equal(report.status, "pass");
  assert.equal(report.total, 1);
});

test("runWorkflow marks fail", async () => {
  const report = await runWorkflow(
    {
      name: "failing",
      tasks: [
        { name: "bad", command: "node -e \"process.exit(1)\"" },
      ],
    },
    { parallel: true, timeoutMs: 10000 },
  );
  assert.equal(report.status, "fail");
  assert.equal(report.failed, 1);
});

test("runWorkflow redacts secret-shaped stdout", async () => {
  const synthetic = "ghp_" + "A".repeat(36);
  const report = await runWorkflow(
    {
      name: "redaction",
      tasks: [
        { name: "token", command: `node -e "console.log('token=${synthetic}')"` },
      ],
    },
    { parallel: true, timeoutMs: 10000 },
  );

  assert.equal(report.status, "pass");
  assert.match(report.tasks[0].stdout, /<redacted-secret>/);
  assert.doesNotMatch(report.tasks[0].stdout, /ghp_/);
});

test("runWorkflow caps stdout previews", async () => {
  const report = await runWorkflow(
    {
      name: "preview",
      tasks: [
        { name: "long", command: "node -e \"console.log('x'.repeat(200))\"" },
      ],
    },
    { parallel: true, timeoutMs: 10000, outputLimit: 40 },
  );

  assert.equal(report.status, "pass");
  assert.match(report.tasks[0].stdout, /\[truncated\]$/);
  assert.ok(report.tasks[0].stdout.length <= 40);
});

test("buildTelosReceipt emits bounded run metadata without raw commands or output", async () => {
  const config = {
    name: "receipt",
    tasks: [
      { name: "ok", command: "node -e \"console.log('ok')\"" },
      { name: "empty", command: "" },
    ],
  };
  const report = await runWorkflow(config, { parallel: true, timeoutMs: 10000 });
  const receipt = buildTelosReceipt(report, config, {
    parallel: true,
    timeoutMs: 10000,
    outputLimit: 40,
  });
  const serialized = JSON.stringify(receipt);

  assert.equal(receipt.schema, "project-telos.bounded-run-receipt/v1");
  assert.equal(receipt.workflow.name, "receipt");
  assert.equal(receipt.terminal_status, "ok");
  assert.equal(receipt.bounds.guaranteed_termination, true);
  assert.equal(receipt.bounds.max_iterations, 2);
  assert.equal(receipt.bounds.per_task_timeout_ms, 10000);
  assert.equal(receipt.tasks.length, 2);
  assert.equal(receipt.tasks[0].action_identity.name, "ok");
  assert.match(receipt.tasks[0].action_identity.command_hash, /^sha256:/);
  assert.match(receipt.tasks[0].output.stdout_hash, /^sha256:/);
  assert.equal(receipt.tasks[0].output.raw_output_included, false);
  assert.equal(receipt.privacy.raw_commands_included, false);
  assert.equal(receipt.privacy.raw_output_included, false);
  assert.doesNotMatch(serialized, /console\.log/);
  assert.doesNotMatch(serialized, /ok'\)/);
});

test("CLI writes a Telos receipt for failing workflows", () => {
  const root = mkdtempSync(path.join(tmpdir(), "whl-receipt-"));
  const configPath = path.join(root, "workflow.json");
  const receiptPath = path.join(root, "receipt.json");
  writeFileSync(
    configPath,
    JSON.stringify({
      name: "failing-receipt",
      tasks: [{ name: "bad", command: "node -e \"process.exit(3)\"" }],
    }),
    "utf8",
  );

  const result = spawnSync(
    process.execPath,
    [
      "bin/workflow-harness-lite.js",
      "--config",
      configPath,
      "--telos-receipt",
      receiptPath,
      "--json",
    ],
    { cwd: path.resolve("."), encoding: "utf8" },
  );
  const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));

  assert.equal(result.status, 1);
  assert.equal(receipt.schema, "project-telos.bounded-run-receipt/v1");
  assert.equal(receipt.terminal_status, "error");
  assert.equal(receipt.tasks[0].result.status, "fail");
  assert.match(receipt.tasks[0].action_identity.command_hash, /^sha256:/);
});

test("CLI accepts UTF-8 BOM config files", () => {
  const root = mkdtempSync(path.join(tmpdir(), "whl-bom-"));
  const configPath = path.join(root, "workflow.json");
  writeFileSync(
    configPath,
    `\uFEFF${JSON.stringify({
      name: "bom-config",
      tasks: [{ name: "ok", command: "node -e \"console.log('ok')\"" }],
    })}`,
    "utf8",
  );

  const result = spawnSync(
    process.execPath,
    ["bin/workflow-harness-lite.js", "--config", configPath, "--json"],
    { cwd: path.resolve("."), encoding: "utf8" },
  );

  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.equal(JSON.parse(result.stdout).name, "bom-config");
});
