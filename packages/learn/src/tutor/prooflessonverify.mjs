// Proof-lesson receipt re-verification. Recomputes the receipt's own chained evidence instead of
// trusting its stored surface, with the same typed failure codes as tutor/reverify.mjs:
//
//   CHAIN_BROKEN     -- the hash chain does not recompute, or the chain's entry accounting does
//                       not match the lesson it claims to carry (truncated or padded).
//   VERDICT_MISMATCH -- the stored lesson surface (verdict, binding, or content digest) does not
//                       re-derive from the receipt's own chained packet binding.
//
// A receipt without chain evidence, or one carrying an illegal verdict enum, is UNVERIFIED --
// structurally uncheckable, never verified.
import { Ledger } from "../accountability/ledger.mjs";
import { observe, sha256hex } from "../accountability/witness.mjs";
import { PACKET_VERDICTS, proofLesson, proofLessonReceipt, lessonProjection } from "./prooflesson.mjs";

// Same code strings as tutor/reverify.mjs (which re-exports the canon); duplicated here as
// literals to keep the module graph acyclic.
const CHAIN_BROKEN = "CHAIN_BROKEN";
const VERDICT_MISMATCH = "VERDICT_MISMATCH";
const GENESIS_HEAD = "0".repeat(64);

// Structural gaps make a receipt UNVERIFIED (cannot be checked), never verified.
function structuralReasons(receipt) {
  const reasons = [];
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt)) return ["not a receipt object"];
  if (!Array.isArray(receipt.entries)) reasons.push("no hash-chained entries recorded (chainless receipt); chainless receipts are never verified");
  const l = receipt.lesson;
  if (!l || typeof l !== "object" || !l.verifierBinding || typeof l.verifierBinding !== "object") {
    reasons.push("no stored lesson with a verifier binding to re-derive");
    return reasons;
  }
  for (const [label, v] of [["receipt", receipt.verdict], ["lesson", l.verdict], ["verifier binding", l.verifierBinding.verdict]]) {
    if (!PACKET_VERDICTS.includes(v)) reasons.push(`${label} carries an illegal verdict enum "${v}" (expected ${PACKET_VERDICTS.join("|")})`);
  }
  return reasons;
}

// (a) Chain integrity: seq ordering, recomputed hash linkage, and entry accounting
// (1 packet-binding + one entry per lesson source + 1 lesson-digest).
function checkChain(receipt, failures) {
  const rows = receipt.entries;
  for (let i = 0; i < rows.length; i++) {
    if (!rows[i] || rows[i].seq !== i) {
      failures.push({ code: CHAIN_BROKEN, seq: i, hash: (rows[i] && rows[i].hash) || null, detail: `entry at index ${i} carries seq ${rows[i] && rows[i].seq} (expected ${i})` });
      return;
    }
  }
  const v = Ledger.fromEntries(rows).verify();
  if (!v.ok) {
    failures.push({ code: CHAIN_BROKEN, seq: v.brokenAt, hash: rows[v.brokenAt].hash, detail: `hash chain does not recompute at entry seq ${v.brokenAt}` });
    return;
  }
  const expected = (receipt.lesson.sources || []).length + 2;
  if (rows.length !== expected) {
    failures.push({ code: CHAIN_BROKEN, seq: rows.length, hash: null, detail: `chain carries ${rows.length} entr(ies) but the stored lesson implies ${expected} (packet binding + sources + lesson digest; truncated or padded)` });
  }
}

// (b) Binding re-derivation: the stored surface must agree with the chained packet binding, the
// chained source hashes, and the chained canonical lesson digest.
function checkBinding(receipt, failures) {
  const rows = receipt.entries;
  const bindingRow = rows[0] && rows[0].entry;
  if (!bindingRow || bindingRow.kind !== "packet-binding") {
    failures.push({ code: CHAIN_BROKEN, seq: 0, hash: (rows[0] && rows[0].hash) || null, detail: "chain does not begin with a packet-binding entry" });
    return null;
  }
  const l = receipt.lesson;
  const surface = [["receipt verdict", receipt.verdict], ["lesson verdict", l.verdict], ["verifier-binding verdict", l.verifierBinding.verdict]];
  for (const [label, v] of surface) {
    if (v !== bindingRow.verdict) {
      failures.push({ code: VERDICT_MISMATCH, detail: `${label} (${v}) does not re-derive from the chained packet binding (${bindingRow.verdict})`, stored: v, rederived: bindingRow.verdict });
    }
  }
  if (l.verifierBinding.packet_id !== bindingRow.packet_id || receipt.packet_id !== bindingRow.packet_id) {
    failures.push({ code: VERDICT_MISMATCH, detail: `stored packet_id (${receipt.packet_id}) does not re-derive from the chained packet binding (${bindingRow.packet_id})`, stored: receipt.packet_id, rederived: bindingRow.packet_id });
  }
  const chainedHashes = rows.filter((r) => r.entry && r.entry.kind === "source").map((r) => r.entry.sha256).filter(Boolean);
  if (JSON.stringify([...(l.verifierBinding.sourceHashes || [])]) !== JSON.stringify(chainedHashes)) {
    failures.push({ code: VERDICT_MISMATCH, detail: "verifier-binding source hashes do not re-derive from the chained source entries", stored: l.verifierBinding.sourceHashes, rederived: chainedHashes });
  }
  const digestRow = rows.map((r) => r.entry).filter((e) => e && e.kind === "lesson-digest").pop();
  if (digestRow) {
    const recomputed = "sha256:" + sha256hex(lessonProjection(l));
    if (recomputed !== digestRow.digest) {
      failures.push({ code: VERDICT_MISMATCH, detail: "stored lesson content does not re-derive from its chained digest (edited after emission)", stored: digestRow.digest, rederived: recomputed });
    }
  }
  return bindingRow;
}

// reverifyLessonReceipt(receipt) -> {verdict, failures, reasons, summary, witness}, the same
// result shape tutor/reverify.mjs emits, so the CLI/MCP reverify surface covers lesson receipts.
export function reverifyLessonReceipt(receipt) {
  const reasons = structuralReasons(receipt);
  if (reasons.length) return { verdict: "UNVERIFIED", failures: [], reasons, summary: null, witness: null };

  const failures = [];
  checkChain(receipt, failures);
  const bindingRow = checkBinding(receipt, failures);
  const rows = receipt.entries;
  const headHash = rows.length ? rows[rows.length - 1].hash : GENESIS_HEAD;
  const verdict = failures.length ? "FAILED" : "VERIFIED";
  const summary = {
    entries: rows.length,
    headHash,
    storedVerdict: receipt.verdict,
    rederivedVerdict: bindingRow ? bindingRow.verdict : null,
    failures: failures.map((f) => f.code),
  };
  const witness = observe({ organ: "learn.tutor.prooflesson", subject: "head:" + headHash, summary: "prooflesson reverify " + verdict, payload: JSON.stringify(summary), data: summary });
  return { verdict, failures, reasons: [], summary, witness };
}

function probePacket() {
  return {
    version: "proof-packet/self-check",
    packet_id: "prooflesson-probe",
    claim: "probe claim",
    scope: "probe scope",
    sources: [{ ref: "probe/src.md", sha256: "a".repeat(64) }],
    verdicts: { overall: "DRIFT" },
    decision_summary: "probe reasoning that must never be dumped",
  };
}

// Falsifiable self-check for doctor: the lesson pipeline must PASS a clean packet and FAIL each
// known-bad input. A verifier that cannot fail on a known-bad input is not a verifier.
export function proofLessonSelfCheck() {
  const clean = JSON.parse(JSON.stringify(proofLessonReceipt(probePacket())));
  if (reverifyLessonReceipt(clean).verdict !== "VERIFIED") return false;
  if (clean.lesson.verdict !== "DRIFT" || clean.misconception.misconception_class !== "contradicted") return false;
  if (JSON.stringify(clean.lesson.scaffold).includes("probe reasoning that must never be dumped")) return false;

  let forgedRejected = false;
  try { proofLesson({ ...probePacket(), verdicts: { overall: "FORGED" } }); }
  catch { forgedRejected = true; } // the rejection IS the pass condition
  if (!forgedRejected) return false;

  const tampered = JSON.parse(JSON.stringify(clean));
  tampered.entries[1].entry.sha256 = "f".repeat(64);
  const t = reverifyLessonReceipt(tampered);
  if (!(t.verdict === "FAILED" && t.failures.some((f) => f.code === CHAIN_BROKEN))) return false;

  const flipped = JSON.parse(JSON.stringify(clean));
  flipped.verdict = "MATCH"; flipped.lesson.verdict = "MATCH"; flipped.lesson.verifierBinding.verdict = "MATCH";
  const e = reverifyLessonReceipt(flipped);
  if (!(e.verdict === "FAILED" && e.failures.some((f) => f.code === VERDICT_MISMATCH))) return false;

  const chainless = JSON.parse(JSON.stringify(clean));
  delete chainless.entries;
  return reverifyLessonReceipt(chainless).verdict === "UNVERIFIED";
}
