// Interop: learn's credential receipts as organ-bundle interchange entries.
//
// The organ bundle is the shared spine gather, crucible, index, forum, and
// learn compose on. This module maps learn's completion receipts and tutor
// mastery verdicts into that entry shape, so a learn receipt can compose into
// the cross-tool receipt spine.
//
// Entry shape matches the proof-surface organ-bundle contract:
// (entry_id, organ_id, receipt_kind, status, payload_sha256, summary, payload_ref).

import { createHash } from "node:crypto";

export const ORGAN = "learn";
export const SPINE_KIND = "learn-receipt";
export const STATUSES = new Set([
  "pass", "fail", "unverified", "warn", "needs-human", "not-applicable", "unknown",
]);

const HEX64 = /^[0-9a-f]{64}$/;

function _entry(entryId, status, payloadSha256, summary, ref) {
  return {
    entry_id: entryId,
    organ_id: ORGAN,
    receipt_kind: SPINE_KIND,
    status,
    payload_sha256: payloadSha256,
    summary: String(summary).slice(0, 160),
    payload_ref: ref,
  };
}

export function receiptEntry(receipt, { entryId = "learn-receipt-1", ref = "learn://receipt" } = {}) {
  const verified = receipt.verified;
  const course = receipt.course || "unknown";
  const seal = receipt.seal || "";
  const autoSteps = receipt.automatedLogistics || 0;
  const humanSteps = (receipt.humanAssessments || []).length;
  const cert = receipt.certId;

  const status = verified ? "pass" : "fail";
  const summary = `course ${course}: ${autoSteps} auto, ${humanSteps} human, cert=${cert || "(none)"}`;
  return _entry(entryId, status, seal || _hash(summary), summary, ref);
}

export function masteryEntry(mastery, { entryId = "learn-mastery-1", ref = "learn://mastery" } = {}) {
  const ready = mastery.mastery?.ready ?? false;
  const attempts = mastery.totalAttempts || 0;
  const status = ready ? "pass" : "needs-human";
  const summary = `mastery: ${ready ? "READY" : "not yet"}, ${attempts} attempts`;
  const sha = _hash(JSON.stringify(mastery));
  return _entry(entryId, status, sha, summary, ref);
}

export function ledgerEntry(row, { entryId = "learn-ledger-1", ref = "learn://ledger" } = {}) {
  const kind = row.entry?.kind || "unknown";
  const seq = row.seq ?? 0;
  const statusMap = {
    "step": "pass",
    "human-assessment": "needs-human",
    "human-gate": "needs-human",
    "aid-visualization": "unverified",
    "assess": "needs-human",
  };
  const status = statusMap[kind] || "unverified";
  const summary = `seq ${seq}: ${kind}`;
  return _entry(entryId, status, row.hash || _hash(summary), summary, ref);
}

export function validateEntry(entry) {
  if (!entry || typeof entry !== "object") return false;
  const fields = ["entry_id", "organ_id", "receipt_kind", "status", "payload_sha256", "summary", "payload_ref"];
  if (JSON.stringify(Object.keys(entry).sort()) !== JSON.stringify(fields.sort())) return false;
  if (entry.organ_id !== ORGAN) return false;
  if (entry.receipt_kind !== SPINE_KIND) return false;
  if (!STATUSES.has(entry.status)) return false;
  if (!HEX64.test(entry.payload_sha256 || "")) return false;
  return true;
}

function _hash(s) {
  return createHash("sha256").update(String(s)).digest("hex");
}
