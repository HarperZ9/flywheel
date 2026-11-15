// telos-engine interop — the visualization bridge. Build a math_physics scene-spec REQUEST from a
// concept, and (Task 2) delegate rendering to the telos CLI over a JSON boundary. Rendering is an
// AID: every result is tagged provenance:"aid" and is structurally barred from graded work.
// Zero-dep (node builtins). learn never imports telos internals — it asks over LEARN_TELOS_CMD.
import { resolve } from "node:path";
import { sha256hex } from "../accountability/witness.mjs";
import { parseCommand, runPeer, refusalReason } from "./spawn.mjs";

// Pure: turn a concept descriptor into a scene-spec request. No I/O.
export function toTelosSceneSpec(concept = {}, { lane = "math_physics" } = {}) {
  const spec = {
    schema: "learn.telos.scene-request/v1",
    concept: { title: concept.title ?? "", kind: concept.kind ?? "math.function-plot" },
    spec: { lane, params: concept.params ?? {}, notes: concept.notes ?? "" },
  };
  spec.requestHash = "sha256:" + sha256hex(JSON.stringify({ concept: spec.concept, spec: spec.spec }));
  return spec;
}

// Delegate rendering to the telos CLI. Configure LEARN_TELOS_CMD as a JSON argv array, for
// example ["node", "/abs/path/to/telos/src/cli.mjs"], or the whitespace form with absolute paths
// (assumed contract: `render <specPath>` -> render-result JSON on stdout). The child starts
// through spawn.mjs. ALWAYS fail-closed and ALWAYS tagged provenance:"aid". Never throws.
export async function telosRender(specPath, { cmd = process.env.LEARN_TELOS_CMD } = {}) {
  const unavailable = (reason) => ({ ran: false, verdict: "UNVERIFIABLE", failure: "engine-unavailable", provenance: "aid", reason });
  let argv;
  try {
    argv = parseCommand(cmd);
  } catch (err) {
    return unavailable(refusalReason("LEARN_TELOS_CMD", err));
  }
  if (!argv) return unavailable("no telos command configured (set LEARN_TELOS_CMD)");
  let res;
  try {
    res = await runPeer(argv, ["render", resolve(specPath)]);
  } catch (err) {
    return unavailable(refusalReason("telos", err));
  }
  let out = null; try { out = JSON.parse(res.stdout); } catch {}
  if (!out || typeof out !== "object") return { ran: true, verdict: "UNVERIFIABLE", failure: "bad-render-output", provenance: "aid", code: res.status ?? null, stdout: (res.stdout || "").slice(0, 400) };
  return {
    ran: true, provenance: "aid",
    selected_profile: out.selected_profile ?? null,
    fallback_chain: out.fallback_chain ?? [],
    scene_spec_hash: out.scene_spec_hash ?? null,
    result_hash: out.result_hash ?? null,
    verdict: out.verdict ?? "UNVERIFIABLE",
    evidence_refs: out.evidence_refs ?? [],
    artifactRef: out.artifactRef ?? null,
  };
}

// Pure: the ledger-entry shape for a witnessed aid render. kind "aid-visualization" is deliberately
// distinct from every graded-channel kind, so the receipt can never file it as human assessment.
export function toAidLedgerEntry(render, { concept, seq } = {}) {
  const entry = {
    kind: "aid-visualization",
    provenance: "aid",
    concept: concept?.title ?? (typeof concept === "string" ? concept : null),
    selected_profile: render?.selected_profile ?? null,
    scene_spec_hash: render?.scene_spec_hash ?? null,
    result_hash: render?.result_hash ?? null,
    verdict: render?.verdict ?? "UNVERIFIABLE",
  };
  if (seq !== undefined) entry.seq = seq;
  return entry;
}
