// Tutor-receipt re-verification. Recomputes a receipt's own evidence instead of trusting its
// self-reported booleans, with two typed failure codes:
//
//   CHAIN_BROKEN     -- the hash chain over the receipt's witnessed practice entries does not
//                       recompute (tampered, reordered, or unaccounted-for entry); reported with
//                       the offending entry's seq and stored hash.
//   VERDICT_MISMATCH -- the stored mastery verdict does not re-derive from the receipt's own
//                       recorded practice evidence under the receipt's own recorded policy
//                       (threshold / minAttempts).
//
// INTEGRITY: the verdict here keys off recomputed hashes and a re-derived mastery result ONLY.
// The receipt's own `verified` / `ledgerVerified` fields are author-controlled and deliberately
// ignored. A receipt without chain evidence (no `entries`) re-verifies as UNVERIFIED, never as
// verified. The policy inputs (threshold, minAttempts) are part of the receipt's claim surface:
// re-verification proves the verdict follows from the recorded evidence under the recorded
// policy, not that the policy itself was a good one.
import { readFileSync, existsSync } from "node:fs";
import { sessionPath } from "./tutorstore.mjs";
import { Ledger } from "../accountability/ledger.mjs";
import { observe } from "../accountability/witness.mjs";
import { newSession, recordAttempt, mastery, masteryReceipt } from "./tutor.mjs";
import { reverifyLessonReceipt } from "./prooflessonverify.mjs";

export const CHAIN_BROKEN = "CHAIN_BROKEN";
export const VERDICT_MISMATCH = "VERDICT_MISMATCH";

const GENESIS_HEAD = "0".repeat(64);

// The comparable claim a mastery verdict makes, as a canonical string (stable key order).
function masteryProjection(m) {
  return JSON.stringify({
    ready: m.ready === true,
    weakest: [...(m.weakest || [])],
    perObjective: (m.perObjective || []).map((p) => ({
      objective: p.objective, attempts: p.attempts, correct: p.correct, accuracy: p.accuracy, ready: p.ready === true,
    })),
  });
}

// Structural gaps make a receipt UNVERIFIED (cannot be checked), never verified.
function structuralReasons(receipt) {
  const reasons = [];
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt)) return ["not a receipt object"];
  if (!Array.isArray(receipt.entries)) reasons.push("no hash-chained entries recorded (chainless receipt); chainless receipts are never verified");
  const m = receipt.mastery;
  if (!m || typeof m !== "object" || typeof m.ready !== "boolean") reasons.push("no stored mastery verdict to re-derive");
  else if (!Number.isFinite(m.threshold) || !Number.isFinite(m.minAttempts)) reasons.push("stored mastery verdict lacks its recorded policy (threshold / minAttempts)");
  return reasons;
}

// (a) Chain integrity: seq ordering, recomputed hash linkage, and attempt accounting.
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
  if (typeof receipt.totalAttempts === "number" && receipt.totalAttempts !== rows.length) {
    failures.push({ code: CHAIN_BROKEN, seq: rows.length, hash: null, detail: `chain carries ${rows.length} entr(ies) but the receipt claims totalAttempts ${receipt.totalAttempts} (truncated or padded)` });
  }
}

// (b) Verdict re-derivation: recompute mastery() from the chained practice entries under the
// receipt's recorded policy and compare it to the stored verdict.
function checkVerdict(receipt, failures) {
  const stored = receipt.mastery;
  const attempts = receipt.entries
    .map((r) => r && r.entry)
    .filter((e) => e && e.kind === "practice")
    .map((e) => ({ objective: e.objective, correct: e.correct }));
  const rederived = mastery(
    { topic: receipt.topic, objectives: receipt.objectives || [], attempts },
    { threshold: stored.threshold, minAttempts: stored.minAttempts },
  );
  if (masteryProjection(rederived) !== masteryProjection(stored)) {
    failures.push({
      code: VERDICT_MISMATCH,
      detail: `stored mastery verdict (ready=${stored.ready}) does not re-derive from the receipt's own ${attempts.length} recorded practice entr(ies) (re-derived ready=${rederived.ready})`,
      stored: JSON.parse(masteryProjection(stored)),
      rederived: JSON.parse(masteryProjection(rederived)),
    });
  }
  return rederived;
}

// reverifyReceipt(receipt) -> {verdict, failures, reasons, summary, witness}
// verdict: "VERIFIED" (evidence recomputes clean) | "FAILED" (typed failures) | "UNVERIFIED"
// (structurally uncheckable, e.g. chainless). The witness is a content-addressed digest of the
// re-check summary, so the outcome itself is carried as evidence, not as prose.
export function reverifyReceipt(receipt) {
  // Proof-lesson receipts carry their own binding evidence; same verdicts, same typed codes.
  if (receipt && typeof receipt === "object" && receipt.kind === "proof-lesson") return reverifyLessonReceipt(receipt);
  const reasons = structuralReasons(receipt);
  if (reasons.length) return { verdict: "UNVERIFIED", failures: [], reasons, summary: null, witness: null };

  const failures = [];
  checkChain(receipt, failures);
  const rederived = checkVerdict(receipt, failures);
  const headHash = receipt.entries.length ? receipt.entries[receipt.entries.length - 1].hash : GENESIS_HEAD;
  const verdict = failures.length ? "FAILED" : "VERIFIED";
  const summary = {
    entries: receipt.entries.length,
    headHash,
    storedReady: receipt.mastery.ready,
    rederivedReady: rederived.ready,
    failures: failures.map((f) => f.code),
  };
  const witness = observe({ organ: "learn.tutor.reverify", subject: "head:" + headHash, summary: "reverify " + verdict, payload: JSON.stringify(summary), data: summary });
  return { verdict, failures, reasons: [], summary, witness };
}

// reverifyFiles(dir, id, {file}) -> {ok, results[, error]}. Without --file it re-verifies every
// receipt the CLI emits for a session (tutor/<id>.mastery.json, tutor/<id>.study-receipt.json,
// tutor/<id>.prooflesson.json).
// `ok` is true only when every checked receipt re-verifies as VERIFIED; UNVERIFIED is fail-closed.
export function reverifyFiles(dir, id, { file = null } = {}) {
  const candidates = file
    ? [file]
    : [sessionPath(dir, id, ".mastery.json"), sessionPath(dir, id, ".study-receipt.json"), sessionPath(dir, id, ".prooflesson.json")].filter((p) => existsSync(p));
  if (!candidates.length) {
    return { ok: false, results: [], error: `no tutor receipt found for ${id} (looked for tutor/${id}.mastery.json, tutor/${id}.study-receipt.json, and tutor/${id}.prooflesson.json; run \`learn tutor receipt\`, \`learn tutor study-receipt\`, or \`learn tutor prooflesson\` first)` };
  }
  const results = candidates.map((p) => {
    let receipt;
    try { receipt = JSON.parse(readFileSync(p, "utf8")); }
    catch (e) { return { file: p, verdict: "UNVERIFIED", failures: [], reasons: [`unreadable or malformed receipt file (${(e && (e.code || e.name)) || "error"})`], summary: null, witness: null }; }
    return { file: p, ...reverifyReceipt(receipt) };
  });
  return { ok: results.every((r) => r.verdict === "VERIFIED"), results };
}

// CLI presentation for a reverifyFiles result.
export function formatReverify(r, label) {
  if (r.error) return `tutor reverify ${label}: ${r.error}`;
  const lines = [`tutor reverify ${label}: ${r.ok ? "VERIFIED" : "NOT VERIFIED"} (${r.results.length} receipt(s))`];
  for (const res of r.results) {
    lines.push(`  [${res.verdict}] ${res.file}`);
    for (const f of res.failures) {
      lines.push(`    ${f.code}${f.seq !== undefined ? ` @entry seq=${f.seq}${f.hash ? " hash=" + f.hash : ""}` : ""}: ${f.detail}`);
    }
    for (const why of res.reasons) lines.push(`    ${why}`);
    if (res.verdict === "VERIFIED") {
      const tail = res.summary.rederivedReady !== undefined
        ? `mastery ${res.summary.rederivedReady ? "READY" : "not yet"} re-derived`
        : `lesson verdict ${res.summary.rederivedVerdict} re-derived`;
      lines.push(`    witnessed: ${res.witness.digest} (${res.summary.entries} entr(ies), head ${res.summary.headHash.slice(0, 12)}, ${tail})`);
    }
  }
  return lines.join("\n");
}

// Falsifiable self-check for doctor: the re-verifier must PASS a clean receipt and FAIL each
// known-bad input. A verifier that cannot fail on a known-bad input is not a verifier.
export function reverifySelfCheck() {
  const s = newSession({ topic: "reverify-probe", objectives: ["x"] });
  for (const q of ["q1", "q2", "q3"]) recordAttempt(s, { objective: "x", prompt: q, answer: "a", correct: true });
  const clean = JSON.parse(JSON.stringify(masteryReceipt(s)));
  if (reverifyReceipt(clean).verdict !== "VERIFIED") return false;

  const tampered = JSON.parse(JSON.stringify(clean));
  tampered.entries[1].entry.correct = false;
  const t = reverifyReceipt(tampered);
  if (!(t.verdict === "FAILED" && t.failures.some((f) => f.code === CHAIN_BROKEN && f.seq === 1))) return false;

  const edited = JSON.parse(JSON.stringify(clean));
  edited.mastery.ready = false;
  const e = reverifyReceipt(edited);
  if (!(e.verdict === "FAILED" && e.failures.some((f) => f.code === VERDICT_MISMATCH))) return false;

  const chainless = JSON.parse(JSON.stringify(clean));
  delete chainless.entries;
  return reverifyReceipt(chainless).verdict === "UNVERIFIED";
}
