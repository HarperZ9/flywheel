// Turn receipts: one JSON line per turn, hash-chained, re-derivable from the
// transcript.
//
// Canonical JSON matches Flywheel's contract.canonical_json (sorted keys, no
// spaces, non-ASCII kept as UTF-8), so a call's `input_sha256` here equals the
// monitor's `args_sha256` for the same call, and the receipt links to the
// monitor's own record of it.
//
// Pure: no `$`. Uses Web Crypto, which a hooks module has.

export const SCHEMA = "flywheel.mod-turn-receipt/v1";
const RESERVED = new Set(["tool", "tool_use_id", "agentId", "consent"]);

/** Canonical JSON text: sorted keys, no whitespace, undefined fields dropped. */
export function canonicalJson(value) {
  if (value === null || typeof value !== "object") {
    return value === undefined ? "null" : JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return "[" + value.map((v) => (v === undefined ? "null" : canonicalJson(v))).join(",") + "]";
  }
  const keys = Object.keys(value).filter((k) => value[k] !== undefined).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonicalJson(value[k])).join(",") + "}";
}

/** Hex SHA-256 of a string's UTF-8 bytes. */
export async function sha256Hex(text) {
  const bytes = new TextEncoder().encode(String(text));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** The tool's own arguments: the event minus the fields the engine reserves. */
export function toolArgs(e) {
  const out = {};
  for (const k of Object.keys(e)) if (!RESERVED.has(k)) out[k] = e[k];
  return out;
}

/** Digest of a call's arguments, the same value Flywheel's args_sha256 gives.
 * Flywheel hashes empty arguments as zero bytes; so does this. */
export async function inputDigest(args) {
  const empty = !args || Object.keys(args).length === 0;
  return sha256Hex(empty ? "" : canonicalJson(args));
}

/** The record for one turn, before it is sealed into the chain. */
export function turnRecord({ sessionId, turnId, agentId, reason, isAborted, endedAt, calls }) {
  const counts = { seen: calls.length, screened: 0, held: 0, passed: 0, unavailable: 0 };
  for (const c of calls) {
    if (c.screened) counts.screened += 1;
    if (c.decision === "held") counts.held += 1;
    else if (c.decision === "unavailable-deny") counts.unavailable += 1;
    else counts.passed += 1;
  }
  return {
    schema: SCHEMA,
    session_id: sessionId ?? "",
    turn_id: turnId ?? "",
    agent_id: agentId ?? null,
    reason: reason ?? "",
    is_aborted: Boolean(isAborted),
    ended_at_ms: endedAt ?? null,
    counts,
    calls,
  };
}

/** Adds the link to the previous record and this record's own hash. */
export async function seal(record, prevHash) {
  const linked = { ...record, prev_hash: prevHash ?? null };
  return { ...linked, record_hash: await sha256Hex(canonicalJson(linked)) };
}

/** The `record_hash` of the last line of a receipts file, or null. */
export function lastHash(text) {
  const lines = String(text ?? "").split("\n").filter((l) => l.trim() !== "");
  if (lines.length === 0) return null;
  try {
    return JSON.parse(lines[lines.length - 1]).record_hash ?? null;
  } catch {
    return null;
  }
}

/**
 * Re-walks a receipts file: every line's hash recomputes and links to the line
 * before it. Returns { ok, count, problems }. A broken or edited line shows as
 * a problem; a deleted middle line shows as a broken link.
 */
export async function verifyChain(text, firstPrev = null) {
  const lines = String(text ?? "").split("\n").filter((l) => l.trim() !== "");
  const problems = [];
  let prev = firstPrev;
  for (let i = 0; i < lines.length; i += 1) {
    let rec;
    try {
      rec = JSON.parse(lines[i]);
    } catch {
      problems.push({ line: i + 1, problem: "not JSON" });
      prev = null;
      continue;
    }
    const { record_hash: claimed, ...body } = rec;
    const recomputed = await sha256Hex(canonicalJson(body));
    if (recomputed !== claimed) problems.push({ line: i + 1, problem: "record_hash does not recompute" });
    if ((rec.prev_hash ?? null) !== prev) problems.push({ line: i + 1, problem: "prev_hash does not link to the line before" });
    prev = claimed ?? null;
  }
  return { ok: problems.length === 0, count: lines.length, problems };
}
