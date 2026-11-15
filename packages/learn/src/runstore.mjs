import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { dirname } from "node:path";
import { Ledger } from "./accountability/ledger.mjs";
import { stateFile } from "./state.mjs";
import { notFound } from "./errors.mjs";

// `<dir>/runs/<id><suffix>`, with the same id and containment checks as tutor sessions.
export function runPath(dir, id, suffix = ".json") {
  return stateFile(dir, "runs", id, suffix, "runId");
}

export function writeRunFile(dir, id, suffix, text) {
  const p = runPath(dir, id, suffix);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, text);
  return p;
}

// submissionMode is the mode the run was started with; a resume reads it back and never
// widens it on its own. Files from 1.6.0 carry no mode and resume as "manual".
export function saveRun(dir, id, { workflow, ledger, status, haltedAt, completion, submissionMode = "manual" }) {
  return writeRunFile(dir, id, ".json",
    JSON.stringify({ workflow, status, haltedAt, completion, submissionMode, entries: ledger.entries() }, null, 2));
}

export function loadRun(dir, id) {
  const p = runPath(dir, id);
  if (!existsSync(p)) throw notFound("no saved run has that runId");
  const raw = JSON.parse(readFileSync(p, "utf8"));
  return { ...raw, ledger: Ledger.fromEntries(raw.entries) };
}
