<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/HarperZ9/workflow-harness-lite/main/docs/art/hero-dark.svg">
  <img src="https://raw.githubusercontent.com/HarperZ9/workflow-harness-lite/main/docs/art/hero-light.svg" alt="workflow-harness-lite: Run bounded local command workflows in parallel with compact reports. Bundles of fine lines carry the work through 4 stations, config, run, redact and receipt, along a sweeping path into a bright core." width="100%">
</picture>

# workflow-harness-lite

Run bounded local command workflows in parallel with compact reports.

```
npm test
```

[![version: 0.1.0](https://img.shields.io/badge/version-0.1.0-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/workflow-harness-lite/releases/latest)
[![CI](https://github.com/HarperZ9/workflow-harness-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/workflow-harness-lite/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-e6e1d6?style=flat-square&labelColor=1a1712)](https://github.com/HarperZ9/workflow-harness-lite/blob/main/LICENSE)
![node 18+](https://img.shields.io/badge/node-18%2B-e6e1d6?style=flat-square&labelColor=1a1712)

Workflow Harness Lite is a dependency-free Node CLI for small automation runs. It
accepts a JSON task config, runs independent commands in parallel, redacts output
previews, and can write a bounded-run receipt for unattended agent workflows.

## See it work, step by step

The [animated explainer](https://harperz9.github.io/repo-explainers/workflow-harness-lite.html)
walks through a four-task config run in parallel, a hung task stopped by the timeout, a token redacted from an output preview, and the bounded-run receipt that keeps hashes and no raw text. Every value on it is output from this repository. Its
source is [docs/explainer/index.html](docs/explainer/index.html).

## Walkthrough

Install it, run it once, then use the main feature. Each command below is real, and so is its output.

1. **Get it.** Clone it. Node 18 or newer, no dependencies.

   ```text
   $ git clone https://github.com/HarperZ9/workflow-harness-lite && cd workflow-harness-lite
   $ npm test
   ```

2. **First run: the demo.** Run a two-step workflow and build its receipt.

   ```text
   $ node examples/demo.mjs
   runWorkflow -> status=pass total=2 passed=2 failed=0 skipped=0
   buildTelosReceipt -> project-telos.bounded-run-receipt/v1 ok
   ```

3. **Run your own workflow.** A step that fails makes the run fail.

   ```text
   $ workflow-harness-lite --config wf.json
   workflow=local-checks status=fail passed=2 failed=2
   PASS node-version
   PASS lint
   FAIL flaky
   FAIL hang
   ```

4. **Write a receipt.** Record the bounded run as a receipt.

   ```text
   $ workflow-harness-lite --config wf.json --telos-receipt receipt.json
   schema           project-telos.bounded-run-receipt/v1
   terminal_status  error
   counts           total 4, passed 2, failed 2
   flaky            command_hash sha256:8b0faa47b894b99e...  status fail  code 2
                    stderr_hash  sha256:5e7b8623d7048b91...  raw_output_included false
   privacy          raw_commands_included false, raw_output_included false, absolute_cwd_included false
   receipt_hash     sha256:2ca9c5963543c0cc...
   ```

## Why it matters

Agent and release workflows need a local runner that terminates predictably and
leaves a compact report. This repo gives developers a small harness for repeated
checks without introducing a full CI system.

## Try it

```bash
npm test
node bin/workflow-harness-lite.js --help
node examples/demo.mjs
```

## What to test first

- Run `npm test`.
- Run the demo and inspect the generated task report.
- Generate a Telos receipt with `--telos-receipt receipt.json`.

## Current status

Node 18+ CLI and importable module with tests. It runs local commands only and
keeps raw commands/output out of the interop receipt.

## Existing technical notes

> Lightweight local workflow runner with parallel task execution.

[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![node](https://img.shields.io/badge/node-18%2B-green.svg)
![version](https://img.shields.io/badge/version-0.2.0-informational.svg)
[![CI](https://github.com/HarperZ9/workflow-harness-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/HarperZ9/workflow-harness-lite/actions/workflows/ci.yml)
![deps: none](https://img.shields.io/badge/deps-none-success.svg)
[![part of: AI-accountability toolkit](https://img.shields.io/badge/part_of-AI--accountability_toolkit-7a5cff.svg)](https://harperz9.github.io)

It accepts a JSON config with named command tasks, runs independent entries in
parallel by default, and returns a compact pass/fail report for local automation
or release checks.

It can also emit a Project Telos bounded-run receipt for unattended agent
workflows. The receipt records terminal status, task identities, command hashes,
output hashes, timeout bounds, and privacy gates without exposing raw commands
or raw stdout/stderr.

Built with agentic assistance and manually reviewed for safety.

## Install

No runtime dependencies. Use it from a clone:

```bash
npm test                 # optional: runs the bundled tests
node bin/workflow-harness-lite.js --help
```

## Usage

```bash
echo '{ "name": "local-checks", "tasks": [{"name":"ping","command":"node -e \"console.log(\\"ping\\")\""}] }' > workflow.json
node bin/workflow-harness-lite.js --config workflow.json --telos-receipt receipt.json
```

See [USAGE.md](USAGE.md) for the full flag reference, the importable API
(`runWorkflow`, `runTasks`, `runTask`, `sanitizeOutput`, `buildTelosReceipt`),
and worked examples with expected output. A runnable end-to-end demo lives in
[`examples/demo.mjs`](examples/demo.mjs):

```bash
node examples/demo.mjs
```

## Report

- JSON report includes status, duration, redacted stdout/stderr previews, and
  command outcomes.
- Telos receipt output uses `project-telos.bounded-run-receipt/v1`, maps
  workflow pass/fail to `ok`/`error`, and keeps raw commands/output out of the
  interop artifact.
- Output previews are capped; use `--output-limit` to tune the character limit.
- Exit code is non-zero when any task fails.

---
**Zain Dana Harper** -- small tools with explicit edges.
[Portfolio](https://harperz9.github.io) · [HarperZ9](https://github.com/HarperZ9)
<sub>Built with Claude Code; reviewed, tested, and owned by me.</sub>

## For developers

Keep the public README, package metadata, and examples aligned with current behavior. Before opening a PR or pushing a release, run the local Node verification path.

```bash
npm install
npm test
```

See [AGENTS.md](AGENTS.md) for the repo-specific operating boundary and
[CHANGELOG.md](CHANGELOG.md) for current delivery status.

---

Built by **[Zain Dana Harper](https://harperz9.github.io)** in Seattle: evidence-first tools that leave a re-checkable artifact behind. The full workbench is at [Project Telos](https://harperz9.github.io).
