// Synthetic proof-surface-style packet fixtures for the proof-lesson tests. All hashes are
// synthetic ("a".repeat(64) style); nothing here touches the network or a real packet emitter.
export const hex = (c) => c.repeat(64);

export function matchPacket() {
  return {
    version: "research-claim-proof-packet/v0",
    packet_id: "pkt-match-1",
    claim: "The identity held under a bounded numeric probe (n=1..100).",
    scope: "One arithmetic identity; bounded probe; not a general proof.",
    sources: [
      { ref: "notes/identity.md", sha256: hex("a"), body: "SOURCE BODIES MUST NEVER BE CARRIED" },
      { ref: "probe/log.txt", sha256: hex("b") },
    ],
    verdicts: { overall: "MATCH", per_check: [{ checker: "numeric-probe", status: "MATCH" }] },
    decision_summary: "Every recomputed probe value agreed with the stored claim.",
    wedge_block: { opaque: true, rows: [1, 2, 3] },
  };
}

export function driftPacket() {
  return {
    version: "research-claim-proof-packet/v0",
    packet_id: "pkt-drift-1",
    claim: "The probe confirms the identity for every n in scope.",
    scope: "Bounded numeric probe; n=1..100.",
    sources: [
      { ref: "notes/identity.md", sha256: hex("a") },
      { ref: "probe/log.txt", sha256: hex("b") },
    ],
    verdicts: { overall: "DRIFT", per_check: [{ checker: "numeric-probe", status: "DRIFT" }] },
    decision_summary: "The recomputed probe diverged from the stored claim at n=7.",
    wedge_block: { opaque: true },
  };
}

export function unverifiablePacket({ withSources = true } = {}) {
  return {
    version: "research-claim-proof-packet/v0",
    packet_id: "pkt-unv-1",
    claim: "The map reaches 1 from every positive integer.",
    scope: "Open problem; bounded probe only.",
    sources: withSources ? [{ ref: "notes/openproblem.md", sha256: hex("c") }] : [],
    verdicts: { overall: "UNVERIFIABLE", per_check: [] },
    decision_summary: "No recorded check could establish the claim as scoped.",
  };
}

export function forgedVerdictPacket() {
  const p = matchPacket();
  p.packet_id = "pkt-forged-1";
  p.verdicts.overall = "VERIFIED_SUPREME"; // not a legal verdict enum value
  return p;
}
