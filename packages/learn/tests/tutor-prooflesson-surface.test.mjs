// CLI + MCP + doctor/status wiring for the proof-packet -> lesson surface, per the repo's
// CLI/MCP parity contract: the derivation is advisory and reachable from both; persistence of
// the chained lesson receipt stays on the CLI, where `tutor reverify` covers it.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { main } from "../src/cli.mjs";
import { dispatch, TOOLS } from "../src/mcp.mjs";
import { doctor } from "../src/doctor.mjs";
import { status } from "../src/status.mjs";
import { proofLessonSelfCheck } from "../src/tutor/prooflesson.mjs";
import { matchPacket, driftPacket, forgedVerdictPacket } from "./fixtures/proof-packets.mjs";

function writePacket(dir, name, packet) {
  const p = join(dir, name);
  writeFileSync(p, JSON.stringify(packet, null, 2));
  return p;
}

// ---- CLI ----

test("learn tutor prooflesson <id> --packet: derives the lesson and writes a chained receipt", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const packetPath = writePacket(dir, "drift.packet.json", driftPacket());
  const r = await main(["tutor", "prooflesson", "pl1", "--packet", packetPath], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /DRIFT/);
  assert.match(r.out, /contradicted/);
  const receipt = JSON.parse(readFileSync(join(dir, "tutor", "pl1.prooflesson.json"), "utf8"));
  assert.equal(receipt.kind, "proof-lesson");
  assert.ok(Array.isArray(receipt.entries) && receipt.entries.length > 0);
});

test("learn tutor prooflesson: a forged verdict enum in the packet file exits 1, nothing written", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const packetPath = writePacket(dir, "forged.packet.json", forgedVerdictPacket());
  const r = await main(["tutor", "prooflesson", "pl2", "--packet", packetPath], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /verdict/i);
});

test("learn tutor prooflesson: --packet is required", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const r = await main(["tutor", "prooflesson", "pl3"], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /--packet/);
});

test("learn tutor reverify <id> covers the emitted lesson receipt (clean passes, tampered fails)", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const packetPath = writePacket(dir, "drift.packet.json", driftPacket());
  await main(["tutor", "prooflesson", "pl4", "--packet", packetPath], { dir });
  const clean = await main(["tutor", "reverify", "pl4"], { dir });
  assert.equal(clean.code, 0);
  assert.match(clean.out, /VERIFIED/);

  const p = join(dir, "tutor", "pl4.prooflesson.json");
  const receipt = JSON.parse(readFileSync(p, "utf8"));
  receipt.verdict = "MATCH";
  receipt.lesson.verdict = "MATCH";
  receipt.lesson.verifierBinding.verdict = "MATCH";
  writeFileSync(p, JSON.stringify(receipt, null, 2));
  const bad = await main(["tutor", "reverify", "pl4"], { dir });
  assert.equal(bad.code, 1);
  assert.match(bad.out, /VERDICT_MISMATCH/);
});

test("usage string mentions prooflesson", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const r = await main(["tutor"], { dir });
  assert.equal(r.code, 1);
  assert.match(r.out, /prooflesson/);
});

// ---- MCP ----

test("mcp: learn_tutor_prooflesson is listed as an advisory tool", () => {
  const tool = TOOLS.find((t) => t.name === "learn_tutor_prooflesson");
  assert.ok(tool, "learn_tutor_prooflesson must be in the MCP tool list");
  assert.match(tool.description, /advisory/i);
});

test("mcp learn_tutor_prooflesson: derives lesson + misconception from an inline packet", async () => {
  const out = await dispatch("learn_tutor_prooflesson", { packet: driftPacket() }, { dir: tmpdir() });
  assert.equal(out.lesson.verdict, "DRIFT");
  assert.equal(out.misconception.misconception_class, "contradicted");
});

test("mcp learn_tutor_prooflesson: reads a packet file via packetPath; MATCH yields null misconception", async () => {
  const dir = mkdtempSync(join(tmpdir(), "learn-"));
  const packetPath = writePacket(dir, "match.packet.json", matchPacket());
  const out = await dispatch("learn_tutor_prooflesson", { packetPath }, { dir });
  assert.equal(out.lesson.verdict, "MATCH");
  assert.equal(out.misconception, null);
});

test("mcp learn_tutor_prooflesson: a forged verdict enum is rejected", async () => {
  await assert.rejects(() => dispatch("learn_tutor_prooflesson", { packet: forgedVerdictPacket() }, { dir: tmpdir() }), /verdict/i);
});

// ---- doctor / status ----

test("proofLessonSelfCheck: clean passes and every known-bad input is rejected", () => {
  assert.equal(proofLessonSelfCheck(), true);
});

test("doctor: gains a prooflesson rejects-known-bad check and stays MATCH", async () => {
  const d = await doctor();
  assert.equal(d.status, "MATCH");
  const check = d.checks.find((c) => /prooflesson/.test(c.name));
  assert.ok(check, "doctor must include a prooflesson known-bad rejection check");
  assert.equal(check.status, "MATCH");
});

test("status: describes the proof-lesson capability in the learning loop", () => {
  const s = status();
  assert.match(JSON.stringify(s.learningLoop), /prooflesson|proof.?packet|proof.?lesson/i);
});
