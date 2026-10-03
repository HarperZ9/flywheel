#!/usr/bin/env node
// rederive: check a session's turn receipts against the session transcript.
//
//   node scripts/rederive.mjs <receipts.jsonl> <transcript.jsonl> [--json]
//
// For each receipt line: the hash chain recomputes; every call's tool_use_id
// exists in the transcript with the same tool name; the SHA-256 of the
// transcript's tool input equals the receipt's input_sha256; a call the mod
// held has a tool result carrying the mod's hold text, and a call it passed
// does not. Exit 0 on MATCH, 1 on DRIFT.
//
// A DRIFT on input_sha256 can also mean a mod earlier in the chain rewrote the
// call before this mod saw it: the transcript keeps what the model asked for.

import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { verifyChain, inputDigest } from "../hooks/lib/receipt.mjs";

const HELD = /^Flywheel (held this call|could not check this call)/;
const GUARDED = new Set(["Bash", "PowerShell", "Edit", "Write", "MultiEdit", "NotebookEdit"]);

function resultText(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) return content.map((c) => (typeof c === "string" ? c : c?.text ?? "")).join("");
  return "";
}

/** tool_use id -> { name, input, resultText, isError }, from a Claude Code transcript. */
export function readTranscript(text) {
  const uses = new Map();
  for (const line of String(text).split("\n")) {
    if (!line.trim()) continue;
    let row;
    try { row = JSON.parse(line); } catch { continue; }
    const content = row?.message?.content;
    if (!Array.isArray(content)) continue;
    for (const block of content) {
      if (block?.type === "tool_use") {
        uses.set(block.id, { ...(uses.get(block.id) ?? {}), name: block.name, input: block.input ?? {} });
      } else if (block?.type === "tool_result") {
        const prev = uses.get(block.tool_use_id) ?? {};
        uses.set(block.tool_use_id, { ...prev, resultText: resultText(block.content), isError: Boolean(block.is_error) });
      }
    }
  }
  return uses;
}

/** Compares receipts with a transcript. */
export async function rederive(receiptsText, transcriptText) {
  const chain = await verifyChain(receiptsText);
  const uses = readTranscript(transcriptText);
  const problems = chain.problems.map((p) => ({ kind: "chain", ...p }));
  const receipted = new Set();
  let calls = 0;
  const lines = String(receiptsText).split("\n").filter((l) => l.trim());
  for (const [i, line] of lines.entries()) {
    let rec;
    try { rec = JSON.parse(line); } catch { continue; }
    for (const c of rec.calls ?? []) {
      calls += 1;
      receipted.add(c.tool_use_id);
      const where = { line: i + 1, tool_use_id: c.tool_use_id };
      const u = uses.get(c.tool_use_id);
      if (!u || u.name === undefined) { problems.push({ kind: "missing-in-transcript", ...where }); continue; }
      if (u.name !== c.tool) problems.push({ kind: "tool-name", ...where, receipt: c.tool, transcript: u.name });
      const digest = await inputDigest(u.input);
      if (digest !== c.input_sha256) problems.push({ kind: "input-digest", ...where });
      const denied = c.decision === "held" || c.decision === "unavailable-deny";
      const sawHold = HELD.test(u.resultText ?? "");
      if (u.resultText !== undefined && denied !== sawHold) {
        problems.push({ kind: "decision", ...where, receipt: c.decision, transcriptShowsHold: sawHold });
      }
    }
  }
  const unreceipted = [...uses.entries()].filter(([id, u]) => GUARDED.has(u.name) && !receipted.has(id)).map(([id]) => id);
  return {
    verdict: problems.length === 0 ? "MATCH" : "DRIFT",
    receipts: lines.length,
    calls,
    problems,
    // Guarded calls with no receipt: turns before the mod loaded, or calls the mod never saw.
    unreceipted,
  };
}

async function main(argv) {
  const json = argv.includes("--json");
  const [receipts, transcript] = argv.filter((a) => a !== "--json");
  if (!receipts || !transcript) {
    process.stderr.write("usage: rederive <receipts.jsonl> <transcript.jsonl> [--json]\n");
    return 2;
  }
  const report = await rederive(readFileSync(receipts, "utf8"), readFileSync(transcript, "utf8"));
  if (json) process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  else {
    process.stdout.write(`${report.verdict}: ${report.receipts} receipt(s), ${report.calls} call(s), ${report.problems.length} problem(s), ${report.unreceipted.length} guarded call(s) with no receipt\n`);
    for (const p of report.problems) process.stdout.write(`  ${JSON.stringify(p)}\n`);
  }
  return report.verdict === "MATCH" ? 0 : 1;
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) main(process.argv.slice(2)).then((c) => { process.exitCode = c; });
