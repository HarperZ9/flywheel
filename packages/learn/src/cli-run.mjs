// learn run | resume | verify | receipt: the credential engine on the command line.
//
// Grants are given per invocation and never implied:
//   --submit witnessed-auto   the engine may perform `submit` steps; on `run` it is recorded as
//                             the run's mode, which a later resume keeps
//   --submit manual           this resume halts at submit steps whatever the recorded mode
//   --allow-cost              the engine may perform steps flagged `cost` or `irreversible`; it
//                             is never recorded, so each invocation that should pay says so
// The ledger entry of every step a grant allowed names the grant (authorizedBy for a submit,
// costAuthorizedBy for a cost step), so the receipt shows who authorized what. Grants are read
// from one parse of the argv (src/argv.mjs), so a grant word given as another flag's value, such
// as `--attest --allow-cost`, is that flag's value and grants nothing.
import { readFileSync } from "node:fs";
import { arg, has } from "./argv.mjs";
import { loadWorkflow } from "./workflow/schema.mjs";
import { run, resume } from "./runtime/runner.mjs";
import { FakeDriver } from "./actuation/driver.mjs";
import { saveRun, loadRun, runPath, writeRunFile } from "./runstore.mjs";
import { buildReceipt } from "./receipt/receipt.mjs";
import { invalid } from "./errors.mjs";
import "./adapters/fake.mjs";
import "./adapters/generic.mjs";
import "./adapters/lms.mjs";

const MODES = new Set(["manual", "witnessed-auto"]);

function submitFlag(argv) {
  if (!has(argv, "--submit")) return null;
  const value = arg(argv, "--submit");
  if (!MODES.has(value)) throw invalid("--submit takes manual or witnessed-auto");
  return value;
}

const at = (r) => (r.haltedAt != null ? " @step " + r.haltedAt : "");

// FakeDriver by default (offline/deterministic). `--native` attaches to the operator's real
// browser via native-control (imported lazily so the CLI + tests never require it otherwise).
async function makeDriver(argv) {
  if (has(argv, "--native")) {
    const { NativeDriver } = await import("./actuation/native-driver.mjs");
    return NativeDriver.open(arg(argv, "--url") || "", { match: arg(argv, "--match") || undefined });
  }
  return new FakeDriver();
}

async function runCmd(argv, dir) {
  const wf = loadWorkflow(JSON.parse(readFileSync(argv[1], "utf8")));
  const id = arg(argv, "--id") || "run";
  runPath(dir, id); // check the id before anything is actuated
  const submissionMode = submitFlag(argv) ?? "manual";
  const r = await run(wf, { driver: await makeDriver(argv), submissionMode, allowCost: has(argv, "--allow-cost"),
    authorizedBy: "run --submit witnessed-auto", costAuthorizedBy: "run --allow-cost" });
  saveRun(dir, id, { workflow: wf, submissionMode, ...r });
  return { code: 0, out: `run ${id}: ${r.status}${at(r)}` };
}

async function resumeCmd(argv, dir) {
  const id = argv[1];
  const prev = loadRun(dir, id);
  if (prev.status === "completed" || prev.status === "denied") {
    return { code: 1, out: `resume ${id}: the run is ${prev.status}; there is nothing to resume` };
  }
  const recorded = prev.submissionMode === "witnessed-auto" ? "witnessed-auto" : "manual";
  const flag = submitFlag(argv);
  const attest = arg(argv, "--attest");
  const r = await resume(prev.workflow, {
    driver: await makeDriver(argv), ledger: prev.ledger, haltedAt: prev.haltedAt,
    submissionMode: flag ?? recorded,
    authorizedBy: flag ? `resume --submit ${flag}` : `run --submit ${recorded} (recorded)`,
    allowCost: has(argv, "--allow-cost"), costAuthorizedBy: "resume --allow-cost",
    humanAttest: attest ? { seq: prev.haltedAt, note: attest, at: new Date().toISOString() } : null,
  });
  saveRun(dir, id, { workflow: prev.workflow, submissionMode: recorded, ...r });
  return { code: 0, out: `resume ${id}: ${r.status}${at(r)}` };
}

export async function runCommand(cmd, argv, dir) {
  if (cmd === "run") return runCmd(argv, dir);
  if (cmd === "resume") return resumeCmd(argv, dir);
  if (cmd === "verify") {
    const v = loadRun(dir, argv[1]).ledger.verify();
    return { code: v.ok ? 0 : 1, out: v.ok ? "chain ok" : `chain BROKEN at ${v.brokenAt}` };
  }
  if (cmd === "receipt") {
    const id = argv[1];
    const prev = loadRun(dir, id);
    // Check all three files first, so a refused name leaves no partial receipt behind.
    for (const suffix of [".receipt.json", ".receipt.md", ".receipt.html"]) runPath(dir, id, suffix);
    const { json, markdown, html } = buildReceipt({ workflow: prev.workflow, ledger: prev.ledger, completion: prev.completion });
    writeRunFile(dir, id, ".receipt.json", JSON.stringify(json, null, 2));
    writeRunFile(dir, id, ".receipt.md", markdown);
    writeRunFile(dir, id, ".receipt.html", html);
    return { code: 0, out: `receipt written: runs/${id}.receipt.json + .md + .html (print .html for PDF)` };
  }
  return null;
}
