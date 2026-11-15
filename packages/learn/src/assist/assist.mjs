// Assist pillar — a STUDY AID, not a ghostwriter. It does not author content. It takes the
// operator's OWN draft and produces an accountability wrapper: a content hash tying output to the
// operator's input, heuristically-extracted factual claims to verify (route to crucible), and cited
// sources (route to gather). The operator writes and owns the work; this makes it checkable.
import { sha256hex } from "../accountability/witness.mjs";

const URL_RE = /\bhttps?:\/\/[^\s)]+/g;
// A rough "this asserts a checkable fact" heuristic: has a number, or a strong assertion verb.
const CLAIM_RE = /\d|\b(is|are|was|were|will|has|have|proves?|shows?|demonstrates?|guarantees?|reduces?|increases?|outperforms?)\b/i;

function sentences(text) {
  return String(text).replace(/\s+/g, " ").split(/(?<=[.!?])\s+/).map((s) => s.trim()).filter(Boolean);
}

export function assist(draft, { sources = [], author = "operator" } = {}) {
  const text = String(draft || "");
  const claims = sentences(text).filter((s) => CLAIM_RE.test(s)).map((s) => ({ text: s.slice(0, 300), verify: true }));
  const foundUrls = (text.match(URL_RE) || []).map((u) => u.replace(/[.,;:!?]+$/, ""));
  const allSources = [...new Set([...sources, ...foundUrls])];
  return {
    author,
    inputSha256: sha256hex(text),
    wordCount: text.split(/\s+/).filter(Boolean).length,
    claims,                       // route each to crucible before submitting
    sources: allSources,          // route each to gather for a source receipt
    checklist: [
      `Verify ${claims.length} factual claim(s) (crucible) before you submit.`,
      `Confirm ${allSources.length} source(s) with receipts (gather).`,
      "This is your own draft; the engine only flagged what to check — it wrote nothing.",
    ],
  };
}

// Optional integration hooks (present-only): route claims/sources to gather & crucible if their
// CLIs are on PATH. Returns the commands to run; does not execute anything by itself.
export function assistPlan(result) {
  return {
    crucible: result.claims.map((c) => `python -m crucible assess  # claim: ${c.text.slice(0, 60)}`),
    gather: result.sources.map((s) => `python -m gather run ${s}`),
  };
}

// Bundle the assist record with the real interop artifacts (crucible thesis + gather manifest).
import { toCrucibleThesis } from "../interop/crucible.mjs";
import { toGatherManifest } from "../interop/gather.mjs";
export function assistArtifacts(draft, opts = {}) {
  const a = assist(draft, opts);
  return { assist: a, crucibleThesis: toCrucibleThesis(a, opts), gatherManifest: toGatherManifest(a) };
}
