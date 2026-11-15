# Usage Guide

`workflow-harness-lite` is a dependency-free Node.js (>=18) workflow runner. It
reads a JSON config of named command tasks, runs them (in parallel by default),
redacts credential-shaped output, emits a compact pass/fail report, and can
write a Project Telos bounded-run receipt.

This package is distributed as ES modules (`"type": "module"`).

## Install

The package is not published to a registry yet. Use it from a clone:

```bash
git clone https://github.com/HarperZ9/workflow-harness-lite.git
cd workflow-harness-lite
npm test                 # optional: runs the bundled tests (node --test)
node bin/workflow-harness-lite.js --help
```

There are no runtime dependencies to install.

## CLI

```text
Usage: workflow-harness-lite [--config path] [--no-parallel] [--timeout ms] [--output-limit chars] [--report path] [--telos-receipt path] [--json]
```

| Flag | Default | Effect |
| --- | --- | --- |
| `--config <path>` | built-in `default` workflow (single `smoke` task) | Path to a JSON workflow config. |
| `--no-parallel` | parallel **on** | Run tasks serially instead of concurrently. |
| `--timeout <ms>` | `15000` | Per-task timeout in milliseconds. |
| `--output-limit <chars>` | `4000` | Max characters kept per stdout/stderr preview before `[truncated]`. |
| `--report <path>` | none | Also write the full JSON report to this file (written even when tasks fail). |
| `--telos-receipt <path>` | none | Also write a `project-telos.bounded-run-receipt/v1` artifact. |
| `--json` | off | Print the full JSON report to stdout instead of the compact summary. |
| `-h`, `--help` | -- | Print usage and exit `0`. |

The process exit code is `0` when the workflow status is `pass` and `1`
otherwise (any task with status `fail`). Tasks with an empty command are
recorded as `skip` and do not fail the workflow.

### Config shape

```json
{
  "name": "local-checks",
  "tasks": [
    { "name": "node-version", "command": "node --version" },
    { "name": "lint", "command": "npm run lint", "cwd": "./packages/app" }
  ]
}
```

- `name` (optional, string) -- workflow label; defaults to `"workflow"`.
- `tasks` (array) -- each task has a `name`, a `command` string, and an optional
  `cwd`. A missing or empty `command` yields a `skip` result.

## Importable API

The module exports `runWorkflow`, `runTasks`, `runTask`, `sanitizeOutput`, and
`buildTelosReceipt`. Import it by relative path from a clone (the package does
not declare a `main` or `exports` entry, so import-by-package-name is not
supported):

```js
import {
  runWorkflow,
  runTasks,
  runTask,
  sanitizeOutput,
  buildTelosReceipt,
} from "./src/workflow_harness_lite.js";
```

| Export | Signature | Returns |
| --- | --- | --- |
| `runWorkflow` | `runWorkflow(config, options?)` | `Promise<report>` -- workflow summary plus per-task results. |
| `runTasks` | `runTasks(tasks, options?)` | `Promise<taskResult[]>`. |
| `runTask` | `runTask(task, options?)` | `Promise<taskResult>`. |
| `buildTelosReceipt` | `buildTelosReceipt(report, config, options?)` | Telos bounded-run receipt without raw commands or raw output. |
| `sanitizeOutput` | `sanitizeOutput(value, limit?)` | `string` -- redacted, trimmed, length-capped text. |

`options`: `{ parallel?: boolean, timeoutMs?: number (default 15000), outputLimit?: number (default 4000) }`.

---

## Worked examples

> Output blocks below were captured from a real run on Node `v25.2.1`; durations
> and the `generated` timestamp will differ on your machine. Output marked
> *illustrative* is shown for shape, not byte-for-byte reproduction.

### 1. Default run (no config)

```bash
node bin/workflow-harness-lite.js
```

Expected output:

```text
workflow=default status=pass passed=1 failed=0
PASS smoke
```

Exit code: `0`.

### 2. Run a multi-task config (compact summary)

`workflow.json`:

```json
{
  "name": "local-checks",
  "tasks": [
    { "name": "node-version", "command": "node --version" },
    { "name": "say-hello", "command": "node -e \"console.log('hello from task')\"" },
    { "name": "missing", "command": "node -e \"process.exit(2)\"" }
  ]
}
```

```bash
node bin/workflow-harness-lite.js --config workflow.json
```

Expected output (one failing task -> non-zero exit):

```text
workflow=local-checks status=fail passed=2 failed=1
PASS node-version
PASS say-hello
FAIL missing
```

Exit code: `1`.

### 3. Full JSON report (`--json`)

```bash
node bin/workflow-harness-lite.js --config workflow.json --json
```

Expected output (*illustrative* -- `durationMs`/`generated` vary):

```json
{
  "name": "local-checks",
  "status": "fail",
  "generated": "2026-06-18T17:16:28.273Z",
  "durationMs": 75,
  "total": 3,
  "passed": 2,
  "failed": 1,
  "skipped": 0,
  "tasks": [
    {
      "name": "node-version",
      "status": "pass",
      "code": 0,
      "durationMs": 46,
      "stdout": "v25.2.1",
      "stderr": ""
    },
    {
      "name": "say-hello",
      "status": "pass",
      "code": 0,
      "durationMs": 66,
      "stdout": "hello from task",
      "stderr": ""
    },
    {
      "name": "missing",
      "status": "fail",
      "code": 2,
      "durationMs": 58,
      "stdout": "",
      "stderr": "Command failed: node -e \"process.exit(2)\""
    }
  ]
}
```

Write the same report to a file (works even when the run fails):

```bash
node bin/workflow-harness-lite.js --config workflow.json --report report.json
```

Write a Telos bounded-run receipt as well:

```bash
node bin/workflow-harness-lite.js --config workflow.json --telos-receipt receipt.json
```

The receipt maps workflow `pass` to terminal status `ok` and failed workflows
to `error`. It includes task names, task indexes, command hashes, optional cwd
hashes, exit codes, durations, stdout/stderr hashes, timeout bounds, and
privacy fields. It does not include raw commands or raw stdout/stderr; use the
JSON report when a human needs the redacted previews.

### 4. Programmatic use + secret redaction

```js
import {
  runWorkflow,
  buildTelosReceipt,
  sanitizeOutput,
} from "./src/workflow_harness_lite.js";

const report = await runWorkflow(
  {
    name: "demo",
    tasks: [
      { name: "echo", command: "node -e \"console.log(42)\"" },
      { name: "empty", command: "" },
    ],
  },
  { parallel: true, timeoutMs: 5000 },
);

console.log(report.status, report.total, report.passed, report.skipped);
console.log(buildTelosReceipt(report, { name: "demo", tasks: [] }).schema);
console.log(sanitizeOutput("api_key=supersecret123"));
```

Expected output:

```text
pass 2 1 1
project-telos.bounded-run-receipt/v1
api_key=<redacted-secret>
```

The empty-command task is recorded as `skip`, so the workflow still passes.
`sanitizeOutput` redacts credential-shaped substrings (private keys, AWS access
keys, GitHub/OpenAI-style tokens, and `key=value` secret pairs).
