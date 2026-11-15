// Best-effort demo -- not runtime-verified by author.
//
// Exercises the real workflow-harness-lite API end-to-end:
//   runWorkflow, runTasks, runTask, sanitizeOutput, buildTelosReceipt
//
// Run from the repo root:
//   node examples/demo.mjs

import {
  runWorkflow,
  runTasks,
  runTask,
  sanitizeOutput,
  buildTelosReceipt,
} from "../src/workflow_harness_lite.js";

// 1. A single task.
const single = await runTask(
  { name: "node-version", command: "node --version" },
  { timeoutMs: 5000 },
);
console.log("runTask ->", single.status, single.stdout);

// 2. A batch of tasks run in parallel.
const batch = await runTasks(
  [
    { name: "echo", command: "node -e \"console.log('hi')\"" },
    { name: "empty", command: "" }, // empty command -> status "skip"
    { name: "fails", command: "node -e \"process.exit(3)\"" },
  ],
  { parallel: true, timeoutMs: 5000 },
);
console.log(
  "runTasks ->",
  batch.map((t) => `${t.name}:${t.status}`).join(" "),
);

// 3. A full workflow with a summary report.
const report = await runWorkflow(
  {
    name: "demo-workflow",
    tasks: [
      { name: "ok", command: "node -e \"console.log('ok')\"" },
      { name: "also-ok", command: "node --version" },
    ],
  },
  { parallel: true, timeoutMs: 5000, outputLimit: 200 },
);
console.log(
  "runWorkflow ->",
  `status=${report.status}`,
  `total=${report.total}`,
  `passed=${report.passed}`,
  `failed=${report.failed}`,
  `skipped=${report.skipped}`,
);

const receipt = buildTelosReceipt(
  report,
  {
    name: "demo-workflow",
    tasks: [
      { name: "ok", command: "node -e \"console.log('ok')\"" },
      { name: "also-ok", command: "node --version" },
    ],
  },
  { parallel: true, timeoutMs: 5000, outputLimit: 200 },
);
console.log("buildTelosReceipt ->", receipt.schema, receipt.terminal_status);

// 4. Standalone output sanitisation (redaction + length cap).
console.log("sanitizeOutput ->", sanitizeOutput("token=<demo>"));
console.log(
  "sanitizeOutput (capped) ->",
  sanitizeOutput("x".repeat(100), 40),
);
