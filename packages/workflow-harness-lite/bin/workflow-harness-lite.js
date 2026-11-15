#!/usr/bin/env node
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { buildTelosReceipt, runWorkflow } from "../src/workflow_harness_lite.js";

function parseArgs(argv) {
  const options = {
    config: "",
    parallel: true,
    json: false,
    report: "",
    telosReceipt: "",
    timeout: 15000,
    outputLimit: 4000,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const value = argv[i];
    if (value === "--config" && argv[i + 1]) {
      options.config = argv[i + 1];
      i += 1;
    } else if (value === "--no-parallel") {
      options.parallel = false;
    } else if (value === "--json") {
      options.json = true;
    } else if (value === "--report" && argv[i + 1]) {
      options.report = argv[i + 1];
      i += 1;
    } else if (value === "--telos-receipt" && argv[i + 1]) {
      options.telosReceipt = argv[i + 1];
      i += 1;
    } else if (value === "--timeout" && argv[i + 1]) {
      options.timeout = Number.parseInt(argv[i + 1], 10);
      i += 1;
    } else if (value === "--output-limit" && argv[i + 1]) {
      options.outputLimit = Number.parseInt(argv[i + 1], 10);
      i += 1;
    } else if (value === "-h" || value === "--help") {
      console.log("workflow-harness-lite");
      console.log(
        "Usage: workflow-harness-lite [--config path] [--no-parallel] [--timeout ms] [--output-limit chars] [--report path] [--telos-receipt path] [--json]",
      );
      process.exit(0);
    }
  }

  return options;
}

async function loadConfig(configPath) {
  if (!configPath) {
    return {
      name: "default",
      tasks: [
        {
          name: "smoke",
          command: 'node -e "console.log(\'workflow-harness-lite smoke\')"',
        },
      ],
    };
  }

  const text = await fs.readFile(path.resolve(configPath), "utf8");
  return JSON.parse(text.replace(/^\uFEFF/, ""));
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const config = await loadConfig(options.config);

  const runOptions = {
    parallel: options.parallel,
    timeoutMs: options.timeout,
    outputLimit: options.outputLimit,
  };
  const report = await runWorkflow(config, runOptions);

  if (options.report) {
    await fs.writeFile(options.report, JSON.stringify(report, null, 2), "utf8");
  }

  if (options.telosReceipt) {
    const receipt = buildTelosReceipt(report, config, runOptions);
    await fs.writeFile(options.telosReceipt, JSON.stringify(receipt, null, 2), "utf8");
  }

  if (options.json) {
    console.log(JSON.stringify(report, null, 2));
  } else {
    console.log(`workflow=${report.name} status=${report.status} passed=${report.passed} failed=${report.failed}`);
    for (const entry of report.tasks) {
      console.log(`${entry.status.toUpperCase()} ${entry.name}`);
    }
  }

  process.exit(report.status === "pass" ? 0 : 1);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
