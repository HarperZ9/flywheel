#!/usr/bin/env node
// Zero-dependency MCP stdio server (JSON-RPC 2.0, newline-delimited). Read tools plus two that
// write: learn_tutor_plan and learn_tutor_record save session files inside the learn state folder
// (LEARN_HOME, else a per-user data folder). No tool drives a browser; actuation (real runs)
// stays on the operator-driven CLI. Ids and paths are confined to the state folder, and a tool
// failure is an isError result with a closed code and a fixed detail (src/errors.mjs).
import path from "node:path";
import { doctor } from "./doctor.mjs";
import { version } from "./index.mjs";
import { isMain } from "./entry.mjs";
import { status } from "./status.mjs";
import { loadRun } from "./runstore.mjs";
import { buildReceipt } from "./receipt/receipt.mjs";
import { run } from "./runtime/runner.mjs";
import { loadWorkflow } from "./workflow/schema.mjs";
import { FakeDriver } from "./actuation/driver.mjs";
import { newSession, newSessionWithFSRS, recordAttempt, recordAttemptWithGrade, mastery } from "./tutor/tutor.mjs";
import { saveSession, loadSession, sessionExists } from "./tutor/tutorstore.mjs";
import { stateRoot, confinedPath, readJson, checkId } from "./state.mjs";
import { LearnError, invalid, notFound, conflict } from "./errors.mjs";
import { due } from "./tutor/schedule.mjs";
import { misconceptions } from "./tutor/misconception.mjs";
import { studyPlan } from "./tutor/study.mjs";
import { reverifyFiles } from "./tutor/reverify.mjs";
import "./adapters/fake.mjs";
import "./adapters/generic.mjs";
import "./adapters/lms.mjs";

export const TOOLS = [
  { name: "learn_doctor", description: "Run the integrity self-check; returns MATCH/DEGRADED with per-invariant results.", inputSchema: { type: "object", properties: {} } },
  { name: "learn_status", description: "Report engine version, capabilities, and the integrity rules it enforces.", inputSchema: { type: "object", properties: {} } },
  { name: "learn_verify", description: "Verify a saved run's hash-chained ledger is intact (tamper-evident).", inputSchema: { type: "object", properties: { runId: { type: "string" } }, required: ["runId"] } },
  { name: "learn_receipt", description: "Return the credential-provenance receipt (logistics vs human-assessment split) for a saved run.", inputSchema: { type: "object", properties: { runId: { type: "string" } }, required: ["runId"] } },
  { name: "learn_dry_run", description: "Preview a workflow with the Fake driver (no real browser): where it halts for the operator, without touching a live site. Pass the workflow inline as `workflow`, or `workflowPath` naming a JSON file inside the learn state folder (relative paths resolve there).", inputSchema: { type: "object", properties: { workflow: { type: "object" }, workflowPath: { type: "string" } } } },
  { name: "learn_tutor_plan", description: "Create a tutor study session with learning objectives (the teach-you loop). Writes tutor/<sessionId>.json inside the learn state folder and refuses to overwrite an existing session unless replace is true. Set enableFsrs to seed per-item FSRS spaced-repetition scheduling state (opt-in).", inputSchema: { type: "object", properties: { sessionId: { type: "string" }, topic: { type: "string" }, objectives: { type: "array", items: { type: "string" } }, enableFsrs: { type: "boolean" }, replace: { type: "boolean" } }, required: ["sessionId"] } },
  { name: "learn_tutor_record", description: "Writes to the session file inside the learn state folder. Record the operator's answer to a PRACTICE question (NOT the graded assessment) and whether it was correct. Optionally pass grade (0-4: fail/slip/lapse/review/easy) + now (ISO/epoch ms) to also update the per-item FSRS scheduling state.", inputSchema: { type: "object", properties: { sessionId: { type: "string" }, objective: { type: "string" }, prompt: { type: "string" }, answer: { type: "string" }, correct: { type: "boolean" }, feedback: { type: "string" }, grade: { type: "number" }, now: { type: ["string", "number"] } }, required: ["sessionId", "objective"] } },
  { name: "learn_tutor_mastery", description: "Check the mastery-gate: has the operator demonstrated readiness for the real assessment?", inputSchema: { type: "object", properties: { sessionId: { type: "string" } }, required: ["sessionId"] } },
  { name: "learn_visualize_dry_run", description: "Return the telos scene-spec request that WOULD be sent to render a math/physics concept (advisory; renders nothing, actuation stays on the CLI).", inputSchema: { type: "object", properties: { concept: { type: "object" } }, required: ["concept"] } },
  { name: "learn_tutor_due", description: "Advisory, read-only: list objectives due for spaced-repetition review in a saved tutor session, most-overdue first. Set useFsrs (with an FSRS-enabled session) for retrievability-based due dates against desiredRetention.", inputSchema: { type: "object", properties: { sessionId: { type: "string" }, now: { type: ["string", "number"] }, asOf: { type: ["string", "number"] }, useFsrs: { type: "boolean" }, desiredRetention: { type: "number" } }, required: ["sessionId", "now"] } },
  { name: "learn_tutor_studyplan", description: "Advisory, read-only: return the composed study plan for a saved tutor session (due list, ranked misconceptions, study order, prerequisite readiness, mastery-gate verdict). Set useFsrs (with an FSRS-enabled session) to rank study order by retrievability (most-at-risk first) against desiredRetention.", inputSchema: { type: "object", properties: { sessionId: { type: "string" }, now: { type: ["string", "number"] }, seed: { type: ["string", "number"] }, useFsrs: { type: "boolean" }, desiredRetention: { type: "number" } }, required: ["sessionId", "now"] } },
  { name: "learn_tutor_misconceptions", description: "Advisory, read-only: return the ranked misconception aggregation (wrong attempts + the operator's own feedback) for a saved tutor session.", inputSchema: { type: "object", properties: { sessionId: { type: "string" } }, required: ["sessionId"] } },
  { name: "learn_tutor_reverify", description: "Advisory, read-only: re-verify a session's emitted tutor receipts from their own recorded evidence (recomputed hash chain + re-derived mastery verdict). Failures are typed CHAIN_BROKEN / VERDICT_MISMATCH, and a receipt without a hash chain reads UNVERIFIED. `file` names one receipt inside the learn state folder.", inputSchema: { type: "object", properties: { sessionId: { type: "string" }, file: { type: "string" } }, required: ["sessionId"] } },
  { name: "learn_tutor_derive_schedule", description: "Advisory, read-only: re-derive the FSRS scheduling state PURELY from the session's witnessed graded attempt log and compare it to the cached itemState hint. Returns a MATCH/DRIFT/NO_FSRS_LOG verdict plus a hash-chained ledger over the graded attempts; the log-derived state is authoritative, so a stale or tampered cache is flagged as DRIFT with a per-field diff. Set optimize to seed the derivation with a per-learner initial-difficulty prior fitted from the learner's own accuracy. It reads the log only: grades, attempts and the mastery gate stay as they are.", inputSchema: { type: "object", properties: { sessionId: { type: "string" }, optimize: { type: "boolean" } }, required: ["sessionId"] } },
  { name: "learn_tutor_prooflesson", description: "Advisory, read-only: derive a lesson from a proof packet (source refs, claim, verdict, explanation scaffold, retrieval questions, verifier binding) plus a typed misconception record for DRIFT/UNVERIFIABLE packets. The lesson verdict always equals the packet verdict; a forged verdict enum is rejected; nothing is written. Pass the packet inline as `packet`, or `packetPath` naming a JSON file inside the learn state folder.", inputSchema: { type: "object", properties: { packet: { type: "object" }, packetPath: { type: "string" } } } },
];

// MCP tool annotations. A hint describes the tool to the client and grants
// nothing. Only the two tutor writers change files, and only inside the learn
// state folder; tutor_plan can replace a session when asked to.
const hints = (title, { readOnly = true, destructive = false, idempotent = true } = {}) => ({
  title, readOnlyHint: readOnly, destructiveHint: destructive, idempotentHint: idempotent, openWorldHint: false,
});
export const TOOL_ANNOTATIONS = {
  learn_doctor: hints("Learn integrity check"),
  learn_status: hints("Learn status"),
  learn_verify: hints("Verify a run ledger"),
  learn_receipt: hints("Credential provenance receipt"),
  learn_dry_run: hints("Preview a workflow"),
  learn_tutor_plan: hints("Create a study session", { readOnly: false, destructive: true, idempotent: false }),
  learn_tutor_record: hints("Record a practice answer", { readOnly: false, idempotent: false }),
  learn_tutor_mastery: hints("Check the mastery gate"),
  learn_visualize_dry_run: hints("Preview a concept render request"),
  learn_tutor_due: hints("List reviews that are due"),
  learn_tutor_studyplan: hints("Build a study plan"),
  learn_tutor_misconceptions: hints("Rank misconceptions"),
  learn_tutor_reverify: hints("Re-verify tutor receipts"),
  learn_tutor_derive_schedule: hints("Re-derive the review schedule"),
  learn_tutor_prooflesson: hints("Derive a lesson from a proof"),
};
for (const tool of TOOLS) {
  tool.title = TOOL_ANNOTATIONS[tool.name].title;
  tool.annotations = { ...TOOL_ANNOTATIONS[tool.name] };
}


function argsObject(args) {
  if (args === undefined || args === null) return {};
  if (typeof args !== "object" || Array.isArray(args)) throw invalid("arguments must be a JSON object");
  return args;
}

function needSession(dir, id) {
  const s = loadSession(dir, id);
  if (!s) throw notFound("no tutor session has that sessionId");
  return s;
}

// An inline object, or a JSON file inside the state folder named by `pathArg`.
function inlineOrFile(dir, value, pathValue, pathArg) {
  if (value !== undefined && value !== null) return value;
  if (pathValue === undefined || pathValue === null) return null;
  return readJson(confinedPath(dir, pathValue, pathArg), pathArg);
}

// ctx.state is { dir, source } from serve(); a library caller may pass ctx.dir alone, which is
// reported as a --dir choice. Without either, the state folder is LEARN_HOME or the default.
export async function dispatch(name, rawArgs = {}, ctx = {}) {
  const state = ctx.state ?? (ctx.dir ? { dir: ctx.dir, source: "--dir" } : stateRoot());
  const dir = state.dir;
  const args = argsObject(rawArgs);
  switch (name) {
    case "learn_doctor": return await doctor();
    case "learn_status": return status({ state });
    case "learn_verify": { const r = loadRun(dir, args.runId); return { runId: args.runId, ...r.ledger.verify() }; }
    case "learn_receipt": { const r = loadRun(dir, args.runId); return buildReceipt({ workflow: r.workflow, ledger: r.ledger, completion: r.completion }).json; }
    case "learn_dry_run": {
      const source = inlineOrFile(dir, args.workflow, args.workflowPath, "workflowPath");
      if (!source) throw invalid("learn_dry_run needs workflow (an object) or workflowPath (a file inside the learn state folder)");
      const wf = loadWorkflow(source);
      const driver = new FakeDriver();
      const res = await run(wf, { driver });
      return { status: res.status, haltedAt: res.haltedAt, steps: res.ledger.entries().map((e) => e.entry.kind) };
    }
    case "learn_tutor_plan": {
      if (sessionExists(dir, args.sessionId) && args.replace !== true) {
        throw conflict("a tutor session with that sessionId already exists; pass replace: true to start it over");
      }
      const opts = { topic: args.topic || "", objectives: args.objectives || [] };
      const s = args.enableFsrs ? newSessionWithFSRS(opts) : newSession(opts);
      saveSession(dir, args.sessionId, s);
      return { sessionId: args.sessionId, objectives: s.objectives, fsrs: !!args.enableFsrs };
    }
    case "learn_tutor_record": {
      const s = needSession(dir, args.sessionId);
      const common = { objective: args.objective, prompt: args.prompt || "", answer: args.answer || "", feedback: args.feedback || "" };
      // grade (0-4) + now routes through the FSRS-aware path (updates per-item scheduling state too).
      if (args.grade !== undefined && args.grade !== null) {
        if (args.now === undefined || args.now === null) throw invalid("learn_tutor_record: now is required when grade is given");
        recordAttemptWithGrade(s, { ...common, grade: args.grade, correct: args.correct, now: args.now });
      } else {
        recordAttempt(s, { ...common, correct: args.correct });
      }
      saveSession(dir, args.sessionId, s);
      return { sessionId: args.sessionId, attempts: s.attempts.length };
    }
    case "learn_tutor_mastery": return mastery(needSession(dir, args.sessionId));
    case "learn_visualize_dry_run": {
      const { toTelosSceneSpec } = await import("./interop/telos.mjs");
      return toTelosSceneSpec(args.concept || {});
    }
    case "learn_tutor_due": {
      const s = needSession(dir, args.sessionId);
      return { sessionId: args.sessionId, due: due(s, { now: args.now, asOf: args.asOf, useFSRS: !!args.useFsrs, desiredRetention: args.desiredRetention ?? 0.9 }) };
    }
    case "learn_tutor_studyplan": {
      const s = needSession(dir, args.sessionId);
      return { sessionId: args.sessionId, ...studyPlan(s, { now: args.now, seed: args.seed, useFSRS: !!args.useFsrs, desiredRetention: args.desiredRetention ?? 0.9 }) };
    }
    case "learn_tutor_misconceptions": {
      const s = needSession(dir, args.sessionId);
      return { sessionId: args.sessionId, misconceptions: misconceptions(s) };
    }
    case "learn_tutor_reverify": {
      checkId(args.sessionId, "sessionId");
      const file = args.file === undefined || args.file === null ? null : confinedPath(dir, args.file, "file");
      const r = reverifyFiles(dir, args.sessionId, { file });
      // Each receipt is named by its place inside the state folder, the form `file` takes, and
      // never by the absolute path the server built.
      const results = r.results.map((x) => ({ ...x, file: path.relative(dir, x.file).split(path.sep).join("/") }));
      return { sessionId: args.sessionId, ...r, results };
    }
    case "learn_tutor_prooflesson": {
      const { proofLesson, misconceptionFromPacket } = await import("./tutor/prooflesson.mjs");
      const packet = inlineOrFile(dir, args.packet, args.packetPath, "packetPath");
      if (!packet) throw invalid("learn_tutor_prooflesson needs packet (an object) or packetPath (a file inside the learn state folder)");
      return { lesson: proofLesson(packet), misconception: misconceptionFromPacket(packet) };
    }
    case "learn_tutor_derive_schedule": {
      const s = needSession(dir, args.sessionId);
      const { deriveScheduleReceipt } = await import("./tutor/fsrsderive.mjs");
      return { sessionId: args.sessionId, ...deriveScheduleReceipt(s, { optimize: !!args.optimize }) };
    }
    default: throw invalid("unknown tool");
  }
}

// Map any failure to the closed shape. learn's own validation errors (plain Error, no system
// code) carry learn-authored text about the caller's own arguments; anything else is INTERNAL
// with a fixed detail, so no file bytes, built paths or stack text reach the model.
export function toolError(err, name) {
  if (err instanceof LearnError) return err;
  if (err && err.constructor === Error && err.code === undefined) return invalid(String(err.message).slice(0, 300));
  process.stderr.write(`learn mcp: ${name} failed (${(err && (err.code || err.name)) || "unknown"})\n`);
  return new LearnError("INTERNAL", "the tool failed with an internal error");
}

// Pure JSON-RPC handler (unit-testable). Returns a response object, or null for notifications.
export async function handle(msg, ctx = {}) {
  const reply = (result) => ({ jsonrpc: "2.0", id: msg.id, result });
  const fail = (code, message) => ({ jsonrpc: "2.0", id: msg.id, error: { code, message } });
  if (msg.method === "initialize") {
    return reply({ protocolVersion: "2024-11-05", serverInfo: { name: "learn", version }, capabilities: { tools: {} } });
  }
  if (msg.method === "notifications/initialized") return null;
  if (msg.method === "tools/list") return reply({ tools: TOOLS });
  if (msg.method === "tools/call") {
    const name = msg.params?.name;
    if (!TOOLS.some((t) => t.name === name)) return fail(-32602, "unknown tool");
    try {
      const out = await dispatch(name, msg.params?.arguments, ctx);
      return reply({ content: [{ type: "text", text: JSON.stringify(out, null, 2) }] });
    } catch (e) {
      const err = toolError(e, name);
      return reply({ isError: true, content: [{ type: "text", text: JSON.stringify(err) }], structuredContent: err.toJSON() });
    }
  }
  if (msg.id === undefined) return null; // unknown notification
  return fail(-32601, `method not found: ${msg.method}`);
}

// stdio loop: newline-delimited JSON-RPC. `dir` is the folder `learn mcp --dir` named.
export function serve({ dir } = {}) {
  const state = dir ? { dir, source: "--dir" } : stateRoot();
  let buf = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", async (chunk) => {
    buf += chunk;
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
      if (!line) continue;
      let msg; try { msg = JSON.parse(line); } catch { continue; }
      const res = await handle(msg, { state });
      if (res) process.stdout.write(JSON.stringify(res) + "\n");
    }
  });
}

// Program start: `learn-mcp` through npm's bin, or `node src/mcp.mjs`.
if (isMain(import.meta.url)) serve();
