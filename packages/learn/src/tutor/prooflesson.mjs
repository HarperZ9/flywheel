// Proof-packet -> lesson. Consumes a proof-surface-style packet JSON and derives a lesson the
// operator studies FROM the packet's own evidence surface: source refs (never bodies), the claim,
// the packet's verdict, an explanation scaffold (prompts for the operator to derive the reasoning,
// never an answer dump), retrieval-practice questions derived from the packet's own fields, and a
// verifier binding (verdict + packet_id + source hashes). For DRIFT / UNVERIFIABLE packets it also
// derives a typed misconception record about WHY the proof attempt failed.
//
// INTEGRITY: the lesson's verdict is copied from the packet's verdict and from nowhere else --
// there is no override path, and the derived lesson is frozen, so a lesson claiming MATCH from a
// DRIFT packet is impossible by construction. A forged verdict enum is rejected up front. Unknown
// wedge-specific packet blocks are treated as opaque: accepted, never copied into the lesson.
import { Ledger } from "../accountability/ledger.mjs";
import { sha256hex } from "../accountability/witness.mjs";

export const PACKET_VERDICTS = ["MATCH", "DRIFT", "UNVERIFIABLE"];

export function validatePacket(packet) {
  if (!packet || typeof packet !== "object" || Array.isArray(packet)) throw new Error("not a packet object");
  if (typeof packet.version !== "string" || !packet.version) throw new Error("packet has no version");
  if (typeof packet.packet_id !== "string" || !packet.packet_id) throw new Error("packet has no packet_id");
  if (typeof packet.claim !== "string" || !packet.claim) throw new Error("packet has no claim");
  const overall = packet.verdicts && packet.verdicts.overall;
  if (typeof overall !== "string") throw new Error("packet has no verdicts.overall");
  if (!PACKET_VERDICTS.includes(overall)) {
    throw new Error(`illegal verdict enum "${overall}" (expected ${PACKET_VERDICTS.join("|")})`);
  }
  if (packet.sources !== undefined && !Array.isArray(packet.sources)) throw new Error("packet sources must be an array");
  for (const s of packet.sources || []) {
    if (!s || typeof s.ref !== "string" || !s.ref) throw new Error("every packet source needs a ref");
  }
  return packet;
}

// Source REFS and content hashes only -- a lesson never carries a source body.
function deriveSources(packet) {
  return (packet.sources || []).map((s) => ({ ref: s.ref, sha256: typeof s.sha256 === "string" ? s.sha256 : null }));
}

function deepFreeze(v) {
  if (v && typeof v === "object" && !Object.isFrozen(v)) {
    for (const k of Object.keys(v)) deepFreeze(v[k]);
    Object.freeze(v);
  }
  return v;
}

// The scaffold: numbered prompts the operator works through to DERIVE the packet's reasoning.
// It quotes the claim/scope/verdict (the study material) but never the packet's decision
// reasoning -- deriving that is the exercise.
function buildScaffold(packet) {
  const refs = deriveSources(packet).map((s) => s.ref);
  const verdict = packet.verdicts.overall;
  const prompts = [
    `Restate, in your own words, exactly what this claim asserts and nothing more: "${packet.claim}"${packet.scope ? ` (scope: ${packet.scope})` : ""}.`,
    refs.length
      ? `Judging by their refs alone (${refs.join(", ")}), predict what each recorded source could contribute as evidence for or against the claim.`
      : "This packet records no sources. Predict what kinds of evidence a verifier would need before it could check this claim at all.",
    `The packet's overall verdict is ${verdict}. Before reading anything else, derive what a ${verdict} verdict must mean about the relationship between the claim and the recorded checks.`,
    "List the checks you would run to reach your own verdict on this claim, then compare your list against what the packet's verdict implies was actually checked.",
  ];
  return prompts.map((prompt, i) => ({ step: i + 1, prompt }));
}

// Retrieval-practice questions, each derived from a named packet field.
function buildQuestions(packet) {
  const qs = [
    { question: `What evidence would falsify this claim: "${packet.claim}"?`, derivedFrom: "claim" },
    { question: "Which recorded source would you re-check first, and what does its content hash let you prove about it?", derivedFrom: "sources" },
    { question: `What does an overall verdict of ${packet.verdicts.overall} entitle you to claim, and what does it not?`, derivedFrom: "verdicts.overall" },
  ];
  if (typeof packet.scope === "string" && packet.scope) {
    qs.push({ question: `The packet's scope is "${packet.scope}". Give one claim that would exceed that scope.`, derivedFrom: "scope" });
  }
  return qs;
}

// proofLesson(packet) -> a frozen lesson object. The verdict is the packet's verdict, copied here
// and nowhere else; there is no parameter that can set or override it.
export function proofLesson(packet) {
  validatePacket(packet);
  const sources = deriveSources(packet);
  return deepFreeze({
    kind: "proof-lesson",
    packet_id: packet.packet_id,
    packet_version: packet.version,
    claim: packet.claim,
    scope: typeof packet.scope === "string" ? packet.scope : "",
    verdict: packet.verdicts.overall,
    sources,
    scaffold: buildScaffold(packet),
    retrievalQuestions: buildQuestions(packet),
    verifierBinding: {
      packet_id: packet.packet_id,
      verdict: packet.verdicts.overall,
      sourceHashes: sources.map((s) => s.sha256).filter(Boolean),
    },
    boundary: "Lesson scaffold only -- prompts for the operator to derive the reasoning; never an answer dump, never a graded-assessment answer.",
  });
}

// For DRIFT / UNVERIFIABLE packets: a typed record of WHY the proof attempt failed, as a prompt
// the operator answers -- classification is derived from the packet's own fields only.
//   DRIFT                         -> contradicted    (the recorded checks came out against the claim)
//   UNVERIFIABLE, sources present -> overclaim       (the claim reached beyond what its evidence establishes)
//   UNVERIFIABLE, no sources      -> missing_evidence (nothing recorded to check the claim against)
export function misconceptionFromPacket(packet) {
  validatePacket(packet);
  const verdict = packet.verdicts.overall;
  if (verdict === "MATCH") return null;
  const sources = deriveSources(packet);
  const misconception_class = verdict === "DRIFT" ? "contradicted" : sources.length ? "overclaim" : "missing_evidence";
  const prompts = {
    contradicted: `This packet's recorded checks came out against the claim "${packet.claim}". Explain why evidence inside the packet's own scope could contradict it, then state what a corrected claim would look like.`,
    overclaim: `The ${sources.length} recorded source(s) could not establish the claim "${packet.claim}" as scoped. Explain why the claim reaches beyond what that evidence can establish, and what narrower claim the same evidence would support.`,
    missing_evidence: `No sources were recorded for the claim "${packet.claim}". Explain why a claim with no recorded evidence cannot re-verify, and list the evidence you would gather first.`,
  };
  return deepFreeze({ packet_id: packet.packet_id, verdict, misconception_class, prompt: prompts[misconception_class] });
}

// Canonical projection of a lesson (stable key order) -- the digest chained into the receipt.
export function lessonProjection(l) {
  const b = l.verifierBinding || {};
  return JSON.stringify({
    kind: l.kind,
    packet_id: l.packet_id,
    packet_version: l.packet_version,
    claim: l.claim,
    scope: l.scope,
    verdict: l.verdict,
    sources: (l.sources || []).map((s) => ({ ref: s.ref, sha256: s.sha256 })),
    scaffold: (l.scaffold || []).map((s) => ({ step: s.step, prompt: s.prompt })),
    retrievalQuestions: (l.retrievalQuestions || []).map((q) => ({ question: q.question, derivedFrom: q.derivedFrom })),
    verifierBinding: { packet_id: b.packet_id, verdict: b.verdict, sourceHashes: [...(b.sourceHashes || [])] },
    boundary: l.boundary,
  });
}

// proofLessonReceipt(packet) -> a hash-chained lesson receipt the existing reverify machinery
// covers: entry 0 binds the packet (id + verdict + claim), one entry per source ref+hash, and a
// final entry chains the canonical lesson digest. Tampering any of it is tamper-evident.
export function proofLessonReceipt(packet) {
  const lesson = proofLesson(packet);
  const misconception = misconceptionFromPacket(packet);
  const ledger = new Ledger();
  ledger.append({ kind: "packet-binding", packet_id: lesson.packet_id, verdict: lesson.verdict, claim: lesson.claim });
  for (const s of lesson.sources) ledger.append({ kind: "source", ref: s.ref, sha256: s.sha256 });
  ledger.append({
    kind: "lesson-digest",
    digest: "sha256:" + sha256hex(lessonProjection(lesson)),
    misconception_class: misconception ? misconception.misconception_class : null,
  });
  return {
    kind: "proof-lesson",
    packet_id: lesson.packet_id,
    verdict: lesson.verdict,
    lesson,
    misconception,
    sourceCount: lesson.sources.length,
    entries: ledger.entries(),
    boundary: "Lesson receipt only -- binds the lesson to its packet's verdict and source hashes; never a graded-assessment answer.",
  };
}

export { reverifyLessonReceipt, proofLessonSelfCheck } from "./prooflessonverify.mjs";
