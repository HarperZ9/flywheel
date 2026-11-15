#!/usr/bin/env node
// SPDX-License-Identifier: AGPL-3.0-only
//
// EMET -- clean-room third implementation (Node.js).
//
// Derived ONLY from SPEC.md, conformance/vectors.json, and
// conformance/markers.corpus. No reference source (membrane.py / organs.py /
// monitor.py / corpus.py / impl/rust/emet.rs) was consulted at authoring time
// (SPEC s.12). One later fix aligned the marker-count scan to the clarified
// SPEC s.16 (non-overlapping leftmost, occurrence count) after this independent
// reading surfaced that the count semantics were unpinned -- exactly the kind of
// divergence the exercise exists to find.
//
// EMET is an externally-anchored integrity layer: it reports byte/provenance
// FACTS, never authority. The verdict lattice is closed (SPEC s.2): every
// integrity judgement is MATCH, DRIFT, or UNVERIFIABLE; no TRUSTED/APPROVED/SAFE.
//
// Built-in modules ONLY (SPEC s.10, minimal TCB).

"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const process = require("node:process");
const { spawnSync } = require("node:child_process");

// ---------------------------------------------------------------------------
// Exit codes (SPEC s.5, v1.0 -- NORMATIVE)
//   0  -- all MATCH / COHERENT / CORROBORATED / INTACT / no markers / selftest ok
//   1  -- a NEGATIVE FINDING: DRIFT / VIEW_DIFFERS_FROM_SOURCE /
//         QUARANTINE_READ_PATH_DIVERGENCE / BROKEN
//   2  -- UNVERIFIABLE for any stable machine reason code (SPEC s.9)
//   3  -- one or more markers detected (refuse)
//   64 -- usage error
// Precedence over multiple targets (SPEC s.5): exit 1 if ANY produced an exit-1
// verdict, else 2 if ANY was UNVERIFIABLE, else 0.
// ---------------------------------------------------------------------------
const EXIT_OK = 0;
const EXIT_DIFFER = 1;
const EXIT_FAIL = 2; // UNVERIFIABLE
const EXIT_MARKERS = 3;
const EXIT_USAGE = 64;

// --json envelope constants (SPEC s.13/s.14). Byte-identical governed keys
// across conforming implementations for the same input.
const EMET_VERSION = "1.1.0";
const SPEC_VERSION = "1.0.0";

// Set true when a global --json flag is present (SPEC s.13). In JSON mode the
// impl emits EXACTLY ONE canonical-JSON object to stdout and NO human lines.
let JSON_MODE = false;

// Emit a human-grammar line, unless --json mode is active (parity with the
// Python report.say()).
function say(line) {
  if (!JSON_MODE) process.stdout.write(line + "\n");
}

// In --json mode, print one canonical envelope to stdout (SPEC s.13). Governed
// keys command/emet_version/spec_version/exit_code always; verdict when a
// judgement-bearing command (null for selftest, the identity, not a judgement).
// null/undefined-valued fields are dropped so the per-command shape is stable.
function emit(command, verdict, exitCode, fields) {
  if (JSON_MODE) {
    const env = {
      command,
      emet_version: EMET_VERSION,
      spec_version: SPEC_VERSION,
      exit_code: exitCode,
    };
    if (verdict !== null && verdict !== undefined) env.verdict = verdict;
    if (fields) {
      for (const k of Object.keys(fields)) {
        const v = fields[k];
        if (v !== null && v !== undefined) env[k] = v;
      }
    }
    process.stdout.write(canonicalJson(env) + "\n");
  }
  return exitCode;
}

// Implementation-private store paths (SPEC s.15); resolved against cwd so a
// single conformance run's anchor + verify share the same store.
const ANCHOR_STORE = "anchors.json";
const AUDIT_LOG = "membrane_log.jsonl";
const GENESIS_PREV = "0".repeat(64);

// ---------------------------------------------------------------------------
// Identity: SHA-256 over EXACT raw bytes (SPEC s.3). No normalization,
// transcoding, or canonicalization. Read binary, never a text view.
// Returns null when no raw byte channel is available (-> UNVERIFIABLE, s.9).
// ---------------------------------------------------------------------------
function readRawBytes(p) {
  try {
    return fs.readFileSync(p); // Buffer of exact bytes
  } catch (_e) {
    return null;
  }
}

// SPEC s.3/s.9: with no raw byte channel, report UNVERIFIABLE with a STABLE
// MACHINE REASON CODE -- never crash, never substitute a default. Distinguishes
// E_NOT_FOUND (the path does not exist) from E_NO_RAW_CHANNEL (the path exists
// but no raw byte channel is available), instead of collapsing to one code.
// Returns { bytes, err }: on success err === null; on inability bytes === null.
function tryRaw(p) {
  try {
    return { bytes: fs.readFileSync(p), err: null };
  } catch (e) {
    const code = e && e.code;
    if (code === "ENOENT") return { bytes: null, err: "E_NOT_FOUND" };
    return { bytes: null, err: "E_NO_RAW_CHANNEL" };
  }
}

function sha256Hex(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

function hashFileRaw(p) {
  const bytes = readRawBytes(p);
  if (bytes === null) return null;
  return sha256Hex(bytes);
}

// ---------------------------------------------------------------------------
// canonical_json(fact) -- byte-identical to Python json.dumps(fact, sort_keys=True)
// (SPEC s.7): keys sorted ascending by Unicode code point; ", " item separator;
// ": " key/value separator; ensure_ascii escaping (all non-ASCII -> \uXXXX); no
// trailing newline. The resulting string is encoded UTF-8 (equivalently ASCII,
// since the output is pure ASCII) before hashing.
//
// SELF-VERIFIED: canonical_json({path:"a.txt",result:"MATCH"}) is the 36-byte
// {"path": "a.txt", "result": "MATCH"}, which reproduces the audit-intact chain.
// ---------------------------------------------------------------------------
function jsonEscapeAscii(str) {
  let out = '"';
  for (const ch of str) {
    const code = ch.codePointAt(0);
    if (ch === '"') out += '\\"';
    else if (ch === "\\") out += "\\\\";
    else if (ch === "\b") out += "\\b";
    else if (ch === "\f") out += "\\f";
    else if (ch === "\n") out += "\\n";
    else if (ch === "\r") out += "\\r";
    else if (ch === "\t") out += "\\t";
    else if (code < 0x20) out += "\\u" + code.toString(16).padStart(4, "0");
    else if (code < 0x7f) out += ch; // printable ASCII
    else if (code <= 0xffff) out += "\\u" + code.toString(16).padStart(4, "0");
    else {
      // ensure_ascii encodes astral code points as a UTF-16 surrogate pair.
      const c = code - 0x10000;
      const hi = 0xd800 + (c >> 10);
      const lo = 0xdc00 + (c & 0x3ff);
      out +=
        "\\u" + hi.toString(16).padStart(4, "0") +
        "\\u" + lo.toString(16).padStart(4, "0");
    }
  }
  return out + '"';
}

function canonicalJsonValue(v) {
  if (v === null) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return jsonEscapeAscii(v);
  if (Array.isArray(v)) return "[" + v.map(canonicalJsonValue).join(", ") + "]";
  if (typeof v === "object") {
    const keys = Object.keys(v).sort(); // ascending by code point
    const parts = keys.map(
      (k) => jsonEscapeAscii(k) + ": " + canonicalJsonValue(v[k])
    );
    return "{" + parts.join(", ") + "}";
  }
  throw new Error("uncanonicalizable value");
}

function canonicalJson(fact) {
  return canonicalJsonValue(fact);
}

// ---------------------------------------------------------------------------
// Audit chain (SPEC s.7): chain = SHA-256(prev + kind + canonical_json(fact)),
// genesis prev = 64 zeros, each subsequent prev = the prior entry's chain.
// The chain BINDS kind: relabeling an operation is tamper. UTF-8 encode of the
// concatenated string before hashing (immaterial vs ASCII -- output is ASCII).
// ---------------------------------------------------------------------------
function chainHash(prev, kind, fact) {
  const material = prev + kind + canonicalJson(fact);
  return crypto.createHash("sha256").update(material, "utf8").digest("hex");
}

function appendLogEntry(kind, fact) {
  let prev = GENESIS_PREV;
  try {
    const existing = fs.readFileSync(AUDIT_LOG, "utf8");
    const lines = existing.split("\n").filter((l) => l.length > 0);
    if (lines.length > 0) {
      const last = JSON.parse(lines[lines.length - 1]);
      if (typeof last.chain === "string") prev = last.chain;
    }
  } catch (_e) {
    // no log yet -> genesis
  }
  const chain = chainHash(prev, kind, fact);
  const entry = { chain, fact, kind, prev };
  // Store as canonical_json so the on-disk bytes are deterministic. Keys are
  // sorted; this is the implementation-private store form (SPEC s.15).
  fs.appendFileSync(AUDIT_LOG, canonicalJson(entry) + "\n");
}

// ---------------------------------------------------------------------------
// Anchor store (SPEC s.15): implementation-private JSON map path -> sha256.
// ---------------------------------------------------------------------------
function loadAnchors() {
  try {
    return JSON.parse(fs.readFileSync(ANCHOR_STORE, "utf8"));
  } catch (_e) {
    return {};
  }
}

function saveAnchors(anchors) {
  fs.writeFileSync(ANCHOR_STORE, JSON.stringify(anchors, null, 2) + "\n");
}

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

// anchor PATH... -- pin sha256 of raw bytes; append a chained log entry; exit 0.
// Zero actuation on target (boundary 6): never edits/writes/signs the target.
function cmdAnchor(paths) {
  if (paths.length === 0) return EXIT_USAGE;
  const anchors = loadAnchors();
  let anyFail = false;
  const results = [];
  for (const p of paths) {
    const { bytes, err } = tryRaw(p);
    if (err) {
      // No raw byte channel -> UNVERIFIABLE (SPEC s.3/s.9), stable reason code.
      // Continue the batch and persist what anchored (parity with membrane.py),
      // rather than aborting and discarding earlier anchors.
      say(`UNVERIFIABLE ${p} reason=${err}`);
      results.push({ path: p, verdict: "UNVERIFIABLE", reason: err });
      anyFail = true;
      continue;
    }
    const hex = sha256Hex(bytes);
    anchors[p] = { sha256: hex };
    appendLogEntry("anchor", { path: p, sha256: hex });
    say(`ANCHORED ${p}`);
    results.push({ path: p, sha256: hex });
  }
  saveAnchors(anchors);
  // anchor only ever produces UNVERIFIABLE (an unreadable path) or clean; it
  // never drifts. An unreadable target is UNVERIFIABLE, never a silent skip.
  return emit("anchor", null, anyFail ? EXIT_FAIL : EXIT_OK, { results });
}

// verify PATH... -- per path emit MATCH / DRIFT / UNVERIFIABLE vs the anchor.
// Precedence (SPEC s.5 v1.0): exit 1 if ANY path DRIFTed, else 2 if ANY was
// UNVERIFIABLE, else 0. A confirmed difference dominates an inability to check.
function cmdVerify(paths) {
  if (paths.length === 0) return EXIT_USAGE;
  const anchors = loadAnchors();
  let drift = 0;
  let unver = 0;
  const results = [];
  for (const p of paths) {
    const a = anchors[p];
    if (!a || typeof a.sha256 !== "string") {
      say(`UNVERIFIABLE ${p} reason=E_NO_ANCHOR`);
      results.push({ path: p, verdict: "UNVERIFIABLE", reason: "E_NO_ANCHOR" });
      unver++;
      continue;
    }
    const { bytes, err } = tryRaw(p);
    if (err) {
      say(`UNVERIFIABLE ${p} reason=${err}`);
      appendLogEntry("verify", { path: p, result: "UNVERIFIABLE", reason: err });
      results.push({ path: p, verdict: "UNVERIFIABLE", reason: err });
      unver++;
      continue;
    }
    const got = sha256Hex(bytes);
    const want = a.sha256;
    const ok = want === got;
    const v = ok ? "MATCH" : "DRIFT";
    say(`${v} ${p}`);
    appendLogEntry("verify", { path: p, result: v });
    results.push({ path: p, verdict: v, want, got });
    if (!ok) drift++;
  }
  // Precedence (SPEC s.5): a confirmed difference dominates an inability to
  // check. Exit 1 if any path DRIFTed, else 2 if any was UNVERIFIABLE, else 0.
  const dom = drift ? "DRIFT" : unver ? "UNVERIFIABLE" : "MATCH";
  const code = drift ? EXIT_DIFFER : unver ? EXIT_FAIL : EXIT_OK;
  return emit("verify", dom, code, { results });
}

// coherence SOURCE VIEW -- compare exact raw bytes.
// COHERENT when byte-identical; VIEW_DIFFERS_FROM_SOURCE otherwise;
// UNVERIFIABLE when either side cannot be read (SPEC s.3/s.9).
function cmdCoherence(args) {
  if (args.length !== 2) return EXIT_USAGE;
  const [src, view] = args;
  const s = tryRaw(src);
  const vw = tryRaw(view);
  if (s.err || vw.err) {
    const why = s.err ? `source:${s.err}` : `view:${vw.err}`;
    say(`result=UNVERIFIABLE reason=${why}`);
    return emit("coherence", "UNVERIFIABLE", EXIT_FAIL, {
      subject: src,
      reason: why,
    });
  }
  const sh = sha256Hex(s.bytes);
  const vh = sha256Hex(vw.bytes);
  const ok = Buffer.compare(s.bytes, vw.bytes) === 0;
  const res = ok ? "COHERENT" : "VIEW_DIFFERS_FROM_SOURCE";
  say(`result=${res}`);
  return emit("coherence", res, ok ? EXIT_OK : EXIT_DIFFER, {
    subject: src,
    source: sh,
    view: vh,
  });
}

// ---------------------------------------------------------------------------
// Marker corpus (SPEC s.8/s.16). Resolve from EMET_CORPUS env, else a default
// path relative to this implementation. Parse: `# corpus_version: N` header,
// `#` comments and blank lines ignored, one literal marker per remaining line.
// corpus_sha256 = SHA-256 over the WHOLE file bytes.
//
// Returns { version, sha256, markers } or null when the corpus is unresolvable
// (-> UNVERIFIABLE reason=E_NO_CORPUS; never a silent empty denylist).
// ---------------------------------------------------------------------------
function resolveCorpusPath() {
  if (process.env.EMET_CORPUS) return process.env.EMET_CORPUS;
  // Default relative to the implementation: impl/js/emet.js -> ../../conformance.
  return path.join(__dirname, "..", "..", "conformance", "markers.corpus");
}

function loadCorpus() {
  const p = resolveCorpusPath();
  const raw = readRawBytes(p);
  if (raw === null) return null;
  const sha256 = sha256Hex(raw);
  // Treat the file as raw bytes; use latin1 so each byte maps 1:1 to a char,
  // preserving exact byte content for literal substring matching.
  const text = raw.toString("latin1");
  const lines = text.split("\n");
  let version = null;
  const markers = [];
  for (const line of lines) {
    const m = /^#\s*corpus_version:\s*(\d+)\s*$/.exec(line);
    if (m) {
      version = parseInt(m[1], 10);
      continue;
    }
    if (line.length === 0) continue; // blank
    if (line.startsWith("#")) continue; // comment
    markers.push(line); // trailing newline already stripped by split
  }
  return { version, sha256, markers };
}

// ASCII-only case fold of a single byte: lowercase A-Z, leave every other byte
// untouched (non-ASCII bytes are NOT case-folded; SPEC s.8 literal
// ASCII-case-insensitive matching over raw bytes).
function asciiLowerByte(b) {
  return b >= 0x41 && b <= 0x5a ? b + 0x20 : b;
}

// Lowercase each corpus marker (latin1 string -> ascii-lowered Buffer), in
// corpus order, dropping empty lines.
function loweredMarkers(markers) {
  return markers
    .filter((m) => m.length > 0)
    .map((m) => {
      const src = Buffer.from(m, "latin1");
      const out = Buffer.allocUnsafe(src.length);
      for (let j = 0; j < src.length; j++) out[j] = asciiLowerByte(src[j]);
      return out;
    });
}

// True iff lowered marker m matches the raw bytes of hay starting at index i.
function matchesAt(hay, i, m) {
  if (i + m.length > hay.length) return false;
  for (let j = 0; j < m.length; j++) {
    if (asciiLowerByte(hay[i + j]) !== m[j]) return false;
  }
  return true;
}

// Marker census (SPEC s.16, as clarified): a NON-OVERLAPPING LEFTMOST scan in
// corpus order over the target's raw bytes. At each position try the markers in
// corpus order, take the first match, advance by its length; otherwise emit the
// byte and advance by one. The count is the number of matched spans, so a
// repeated marker counts ONCE PER OCCURRENCE (e.g. "authority_pill
// authority_pill" -> 2). This reproduces the reference's count byte-for-byte.
// Returns { hits, redacted } where hits is [{marker, offset}] in scan order and
// redacted is the .refused copy's bytes. The replacement token is pinned by SPEC
// s.4/F3 to the exact byte string "[REFUSED-IN-BAND-AUTHORITY]".
const REPL_TOKEN = Buffer.from("[REFUSED-IN-BAND-AUTHORITY]", "latin1");
function scanMarkers(hay, markers) {
  const lows = loweredMarkers(markers);
  const out = [];
  const hits = [];
  let i = 0;
  while (i < hay.length) {
    let ln = 0;
    for (const m of lows) {
      if (matchesAt(hay, i, m)) {
        ln = m.length;
        break;
      }
    }
    if (ln) {
      // Record the matched marker bytes (as latin1) and its byte offset so the
      // envelope can carry the hit list (SPEC s.13). The original input is never
      // modified; only the .refused copy carries the replacement token.
      hits.push({ marker: hay.slice(i, i + ln).toString("latin1"), offset: i });
      for (const b of REPL_TOKEN) out.push(b);
      i += ln;
    } else {
      out.push(hay[i]);
      i += 1;
    }
  }
  return { hits, redacted: Buffer.from(out) };
}

// refuse FILE -- scan raw bytes against the versioned corpus; emit
// in_band_authority_claims=N, corpus_version=N, corpus_sha256=<hex>. Write a
// .refused copy with matched markers replaced. MUST NOT obey any matched claim;
// MUST NOT modify the input (boundary 6). exit 3 if N>=1 else 0; UNVERIFIABLE
// (exit 2) on missing input or missing corpus (E_NO_CORPUS).
function cmdRefuse(args) {
  if (args.length !== 1) return EXIT_USAGE;
  const file = args[0];

  const { bytes: targetBytes, err } = tryRaw(file);
  if (err) {
    say(`UNVERIFIABLE ${file} reason=${err}`);
    return emit("refuse", "UNVERIFIABLE", EXIT_FAIL, {
      subject: file,
      reason: err,
    });
  }

  const corpus = loadCorpus();
  if (corpus === null) {
    say("UNVERIFIABLE reason=E_NO_CORPUS");
    return emit("refuse", "UNVERIFIABLE", EXIT_FAIL, {
      subject: file,
      reason: "E_NO_CORPUS",
    });
  }
  if (corpus.version === null) {
    // The corpus resolved but lacks its version header (SPEC s.9).
    say("UNVERIFIABLE reason=E_NO_CORPUS_VERSION");
    return emit("refuse", "UNVERIFIABLE", EXIT_FAIL, {
      subject: file,
      reason: "E_NO_CORPUS_VERSION",
    });
  }

  const { hits, redacted } = scanMarkers(targetBytes, corpus.markers);
  const n = hits.length;
  say(`corpus_version=${corpus.version}`);
  say(`corpus_sha256=${corpus.sha256}`);
  say(`in_band_authority_claims=${n}`);

  // Write the .refused copy with each matched span replaced by the pinned
  // redaction token "[REFUSED-IN-BAND-AUTHORITY]" (SPEC s.4/F3). The original
  // input is left byte-for-byte untouched (boundary 6); only the copy is written.
  const cleanCopy = file + ".refused";
  try {
    fs.writeFileSync(cleanCopy, redacted);
  } catch (_e) {
    // A .refused write failure must not be mistaken for a marker verdict; the
    // census (stdout + exit class) is the conformance-pinned output.
  }

  // refuse emits a count, not a lattice verdict; the envelope carries no verdict
  // (parity with the Python reference passing verdict=None).
  return emit("refuse", null, n >= 1 ? EXIT_MARKERS : EXIT_OK, {
    subject: file,
    in_band_authority_claims: n,
    corpus_version: corpus.version,
    corpus_sha256: corpus.sha256,
    hits,
    clean_copy: cleanCopy,
  });
}

// corroborate PATH -- hash the SAME file via DISJOINT read paths and compare.
// Channel 1: raw read (this process). Channel 2: an independent subprocess
// (git hash-object, else a cat-style read). CORROBORATED when channels agree;
// QUARANTINE_READ_PATH_DIVERGENCE when they disagree; UNVERIFIABLE
// (E_NO_SECOND_READ_PATH) when no independent channel is available (SPEC s.4/s.9).
function cmdCorroborate(args) {
  if (args.length !== 1) return EXIT_USAGE;
  const p = args[0];

  const { bytes, err } = tryRaw(p);
  if (err) {
    say(`result=UNVERIFIABLE reason=${err}`);
    return emit("corroborate", "UNVERIFIABLE", EXIT_FAIL, {
      subject: p,
      reason: err,
    });
  }
  const primary = sha256Hex(bytes);

  const secondary = secondReadPathHash(p);
  if (secondary === null) {
    say("result=UNVERIFIABLE reason=E_NO_SECOND_READ_PATH");
    return emit("corroborate", "UNVERIFIABLE", EXIT_FAIL, {
      subject: p,
      reason: "E_NO_SECOND_READ_PATH",
      channels: { open_rb: primary },
    });
  }

  const channels = { open_rb: primary, subproc_read: secondary };
  const agree = secondary === primary;
  const res = agree ? "CORROBORATED" : "QUARANTINE_READ_PATH_DIVERGENCE";
  say(`result=${res}`);
  // git_read_agrees_with_open is a DETAIL field; this impl uses a subprocess
  // read channel rather than a VCS channel (SPEC s.4 makes the channel set
  // implementation-defined), so it reports null (no git channel consulted).
  return emit("corroborate", res, agree ? EXIT_OK : EXIT_DIFFER, {
    subject: p,
    channels,
    read_paths_agree: agree,
    git_read_agrees_with_open: null,
  });
}

// An independent read path: read the same bytes through a subprocess so a
// tampered in-process read channel would diverge. Prefer `git hash-object`
// (which itself emits a sha1, so we re-read raw bytes via node -e through a
// detached child to keep the channel disjoint from the primary readFileSync).
// Returns a sha256 hex over the bytes that channel observed, or null.
function secondReadPathHash(p) {
  // Channel: a child node process that reads the file independently and prints
  // the raw bytes as base64; the parent re-hashes. Disjoint from the parent's
  // own readFileSync (different process, different fd lifecycle).
  const script =
    "const fs=require('node:fs');" +
    "process.stdout.write(fs.readFileSync(process.argv[1]).toString('base64'));";
  try {
    const r = spawnSync(process.execPath, ["-e", script, p], {
      maxBuffer: 1024 * 1024 * 256,
    });
    if (r.status !== 0 || r.error) return null;
    const b64 = r.stdout.toString("utf8");
    const bytes = Buffer.from(b64, "base64");
    return sha256Hex(bytes);
  } catch (_e) {
    return null;
  }
}

// audit -- recompute the hash chain from membrane_log.jsonl bytes actually
// stored. INTACT iff every entry's stored chain equals SHA-256(prev + kind +
// canonical_json(fact)) AND prev-linkage holds (genesis prev = 64 zeros; each
// subsequent prev = the prior entry's stored chain). Any mismatch -> BROKEN.
function cmdAudit(args) {
  if (args.length !== 0) return EXIT_USAGE;
  let raw;
  try {
    raw = fs.readFileSync(AUDIT_LOG, "utf8");
  } catch (_e) {
    // No log: an empty chain is trivially intact (genesis state). Emit the
    // chain= line WITH log_entries=0 (SPEC s.13), not a special-case string.
    say("log_entries=0 chain=INTACT");
    return emit("audit", "INTACT", EXIT_OK, { log_entries: 0 });
  }
  const lines = raw.split("\n").filter((l) => l.length > 0);
  let expectedPrev = GENESIS_PREV;
  let n = 0;
  let ok = true;
  let brokenAt = null;
  for (const line of lines) {
    n++;
    let entry;
    try {
      entry = JSON.parse(line);
    } catch (_e) {
      ok = false;
      brokenAt = n;
      break;
    }
    const { kind, fact, prev, chain } = entry;
    if (typeof kind !== "string" || typeof prev !== "string" ||
        typeof chain !== "string" || fact === undefined) {
      ok = false;
      brokenAt = n;
      break;
    }
    // Linkage: stored prev must equal the prior entry's stored chain
    // (genesis = 64 zeros). Catches a forged-but-self-consistent re-chained suffix.
    if (prev !== expectedPrev) {
      ok = false;
      brokenAt = n;
      break;
    }
    // Recompute this entry's chain from its STORED prev + kind + fact. The chain
    // binds kind, so relabeling an operation alone recomputes to a mismatch.
    if (chainHash(prev, kind, fact) !== chain) {
      ok = false;
      brokenAt = n;
      break;
    }
    expectedPrev = chain;
  }
  const v = ok ? "INTACT" : "BROKEN";
  say(`log_entries=${n} chain=${v}`);
  return emit("audit", v, ok ? EXIT_OK : EXIT_DIFFER, {
    log_entries: n,
    broken_at: brokenAt,
  });
}

// selftest -- emit the SHA-256 of this source file (the artifact-of-record for
// an interpreted implementation, SPEC s.14). Asserts no authority: this reports
// a fact about EMET's own bytes, not a trust claim. Trust-root caveat (s.11): a
// compromised substrate re-derives a compromised hash consistently, so an
// EXTERNAL verifier MUST be the check of record -- EMET is not its own root of trust.
function cmdSelftest(args) {
  if (args.length !== 0) return EXIT_USAGE;
  // Artifact-of-record for a single-file interpreted impl (SPEC s.14): the
  // SHA-256 of this source file's raw bytes (unchanged basis).
  const hex = hashFileRaw(__filename);
  if (hex === null) {
    // Should not happen, but never crash: report inability honestly.
    say("UNVERIFIABLE reason=E_NO_RAW_CHANNEL path=self");
    return emit("selftest", "UNVERIFIABLE", EXIT_FAIL, { reason: "E_NO_RAW_CHANNEL" });
  }
  // SPEC s.14: the canonical token is emet_self_sha256=; the legacy
  // membrane_self_sha256= is emitted through the 1.x window (removed at 2.0),
  // carrying the same hex value.
  const notes = [
    "re-derive this hash from the source files to check this build.",
    "emet reports hashes and verdicts; it grants no permission.",
  ];
  say(`emet_self_sha256=${hex}`);
  say(`membrane_self_sha256=${hex}  (deprecated alias; removed at 2.0)`);
  for (const note of notes) say(`note=${note}`);
  // selftest reports an IDENTITY, not a judgement, so it carries no verdict.
  return emit("selftest", null, EXIT_OK, { self_sha256: hex, notes });
}

// ===========================================================================
// witness_receipt -- SPEC s.17: the portable, offline-verifiable witness receipt.
//
// A receipt is a self-contained JSON object encoding one or more EMET verdicts
// plus the METHOD (hash algorithm, spec version, corpus version) so a DIFFERENT
// party re-derives and checks it on their OWN machine with ZERO shared state,
// zero trust in the producer, and zero network access.
//
// Two independent integrity checks compose, neither a trust decision:
//   1. content-addressing (default): receipt_id = sha256(canonical(receipt minus
//      receipt_id, signature, and the per-implementation witness block, s.17.2)).
//   2. subject re-derivation (--recompute-from-paths): re-hash the subject files'
//      live bytes and compare against the recorded digests.
//
// An optional HMAC-SHA256 signature (crypto.createHmac) over the SAME addressed
// body strengthens integrity only when producer and verifier share a key channel;
// with no key the signature is null and content-addressing stands alone. The
// receipt-level verdict is a member of the closed RECEIPT lattice { RECEIPT_VALID
// | RECEIPT_TAMPERED | RECEIPT_UNVERIFIABLE } and maps to no authority word.
//
// Reuses the existing spine: canonicalJson (s.7 byte form), sha256Hex, readRawBytes
// (subject re-derivation), emit (--json, s.13). The content address is
// byte-identical to the Python and Rust ports for the same subject/verdict/spec/
// issued_at.
// ===========================================================================

const RECEIPT_FORMAT = "emet-witness-receipt/v1";
const RECEIPT_IMPL = "emet-node-reference";
const RECEIPT_SIG_ALGO = "hmac-sha256-optional";
const RECEIPT_REDERIV = "hash";
const RECEIPT_SIGNING_KEY_ENV = "EMET_RECEIPT_SIGNING_KEY";
const RECEIPT_NOTES =
  "EMET emits witness facts only. The receipt preserves the closed verdict " +
  "lattice and carries no authority, permission, or release decision.";

// The artifact-of-record hash for this source file (SPEC s.14): descriptive-only
// (the witness block is NOT part of the content address, s.17.2).
function nodeSelfSha256() {
  const hex = hashFileRaw(__filename);
  return hex === null ? "unknown" : hex;
}

// Re-hash a subject's live bytes from disk; null if unreadable (reported as a
// reason code by the caller, never a throw).
function receiptRecompute(p, baseDir) {
  const full = baseDir == null ? p : path.join(baseDir, p);
  const bytes = readRawBytes(full);
  return bytes === null ? null : sha256Hex(bytes);
}

function subjectEntry(p, digest) {
  if (digest == null) return { path: p, sha256: null, reason: "E_NO_DIGEST" };
  return { path: p, sha256: digest };
}

// Derive the subject list from a parsed command envelope (verify/anchor carry a
// results[] array; coherence carries a single subject). Mirrors Python
// _subjects_from_envelope.
function subjectsFromEnvelope(env, baseDir) {
  const subjects = [];
  const results = env.results;
  if (Array.isArray(results) && results.length > 0) {
    for (const r of results) {
      if (typeof r !== "object" || r === null) continue;
      const p = r.path;
      if (typeof p !== "string") continue;
      let digest = typeof r.got === "string" ? r.got : (typeof r.sha256 === "string" ? r.sha256 : null);
      if (digest == null) digest = receiptRecompute(p, baseDir);
      subjects.push(subjectEntry(p, digest));
    }
    return subjects;
  }
  const p = env.subject;
  if (typeof p === "string") {
    let digest = typeof env.source === "string" ? env.source : null;
    if (digest == null) digest = receiptRecompute(p, baseDir);
    subjects.push(subjectEntry(p, digest));
  }
  return subjects;
}

// Extract governed verdict records from a parsed command envelope. verify carries
// per-path verdicts under results[]; coherence/corroborate carry a single
// top-level verdict; anchor carries none. Mirrors Python _verdict_records.
function verdictRecords(env) {
  const command = typeof env.command === "string" ? env.command : null;
  const records = [];
  const results = env.results;
  if (Array.isArray(results) && results.length > 0) {
    results.forEach((r, i) => {
      if (typeof r !== "object" || r === null) return;
      const v = r.verdict;
      if (typeof v !== "string") return;
      const rec = { subject_index: i, command, verdict: v };
      if (typeof r.want === "string") rec.want = r.want;
      if (typeof r.got === "string") rec.got = r.got;
      records.push(rec);
    });
    return records;
  }
  if (typeof env.verdict === "string") {
    records.push({ subject_index: 0, command, verdict: env.verdict });
  }
  return records;
}

// The addressed body: the receipt object minus receipt_id, signature, and the
// per-implementation witness block (SPEC s.17.2). Canonicalized identically to
// Python/Rust so the content address is byte-identical across implementations.
function receiptAddressedCanonical(receipt) {
  const body = {};
  for (const k of Object.keys(receipt)) {
    if (k === "receipt_id" || k === "signature" || k === "witness") continue;
    body[k] = receipt[k];
  }
  return canonicalJson(body);
}

function receiptIdHash(receipt) {
  return sha256Hex(Buffer.from(receiptAddressedCanonical(receipt), "utf8"));
}

// HMAC-SHA256 over the SAME addressed body the content address covers, hex-encoded.
function signReceipt(receipt, signingKey) {
  return crypto
    .createHmac("sha256", signingKey)
    .update(receiptAddressedCanonical(receipt), "utf8")
    .digest("hex");
}

// Explicit key wins; else the env var (out-of-spec, optional); else null (content
// address alone). Returns a Buffer or null.
function resolveKey(signingKey) {
  if (signingKey != null) return signingKey;
  const e = process.env[RECEIPT_SIGNING_KEY_ENV];
  return e ? Buffer.from(e, "utf8") : null;
}

// Build a portable receipt from a parsed command envelope. Mirrors Python
// emit_receipt field-for-field. `now` is the injected issued_at (the one
// wall-clock field). `signingKey` (Buffer) adds the optional HMAC signature.
function emitReceipt(env, baseDir, now, signingKey) {
  const subjects = subjectsFromEnvelope(env, baseDir);
  const records = verdictRecords(env);
  const receipt = {
    format: RECEIPT_FORMAT,
    issued_at: now,
    witness: {
      implementation: RECEIPT_IMPL,
      spec_version: SPEC_VERSION,
      self_sha256: nodeSelfSha256(),
    },
    subject: subjects,
    verdict_record: records,
    corpus_version: typeof env.corpus_version === "number" ? env.corpus_version : null,
    corpus_sha256: typeof env.corpus_sha256 === "string" ? env.corpus_sha256 : null,
    signature_algorithm: RECEIPT_SIG_ALGO,
    re_derivation_method: RECEIPT_REDERIV,
    notes: RECEIPT_NOTES,
  };
  // Content-address first, then (optionally) sign the SAME body.
  receipt.signature = signingKey ? signReceipt(receipt, signingKey) : null;
  receipt.receipt_id = receiptIdHash(receipt);
  return receipt;
}

// Constant-time hex compare (avoids early-exit timing leak on id/signature).
function ctEqHex(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  try {
    return crypto.timingSafeEqual(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
  } catch (_e) {
    return false;
  }
}

// Load + shallow-validate a receipt JSON file. Throws Error on a malformed file or
// a wrong/absent format tag -- callers turn that into RECEIPT_UNVERIFIABLE, never
// a stack trace.
function loadReceipt(p) {
  let data;
  try {
    data = JSON.parse(fs.readFileSync(p, "utf8"));
  } catch (e) {
    const kind = e && e.code === "ENOENT" ? "OSError" : "ValueError";
    throw new Error("receipt unreadable or malformed: " + kind);
  }
  if (typeof data !== "object" || data === null || data.format !== RECEIPT_FORMAT) {
    throw new Error("not an " + RECEIPT_FORMAT + " receipt");
  }
  return data;
}

// Stateless offline re-verification. Returns { verdict, detail } where verdict is
// a governed RECEIPT token. TAMPERED dominates UNVERIFIABLE (SPEC s.5/s.17).
function checkReceipt(receipt, baseDir, recompute, signingKey) {
  if (typeof receipt !== "object" || receipt === null || receipt.format !== RECEIPT_FORMAT) {
    return { verdict: "RECEIPT_UNVERIFIABLE", detail: "not an " + RECEIPT_FORMAT + " receipt" };
  }
  const storedId = receipt.receipt_id;
  if (typeof storedId !== "string") {
    return { verdict: "RECEIPT_UNVERIFIABLE", detail: "receipt_id absent or malformed" };
  }
  const derived = receiptIdHash(receipt);
  if (!ctEqHex(storedId, derived)) {
    return {
      verdict: "RECEIPT_TAMPERED",
      detail: "receipt_id mismatch: stored " + storedId.slice(0, 16) + " != re-derived " + derived.slice(0, 16),
    };
  }
  // Optional signature check: if signed, a key MUST verify it.
  const sig = receipt.signature;
  const key = resolveKey(signingKey);
  if (sig != null) {
    if (key == null) {
      return {
        verdict: "RECEIPT_UNVERIFIABLE",
        detail: "receipt is signed but no key provided to verify the signature",
      };
    }
    if (!ctEqHex(sig, signReceipt(receipt, key))) {
      return { verdict: "RECEIPT_TAMPERED", detail: "signature does not verify" };
    }
  }
  // Optional subject re-derivation from live bytes. DRIFT dominates unreadable.
  if (recompute) {
    let drift = null;
    let unver = null;
    const subjects = Array.isArray(receipt.subject) ? receipt.subject : [];
    for (const s of subjects) {
      if (typeof s !== "object" || s === null) {
        unver = unver || "malformed subject entry";
        continue;
      }
      const p = s.path;
      const recorded = s.sha256;
      if (typeof p !== "string" || typeof recorded !== "string") {
        unver = unver || "subject with no recorded digest to re-derive";
        continue;
      }
      const actual = receiptRecompute(p, baseDir);
      if (actual === null) unver = unver || "subject unreadable: " + p;
      else if (actual !== recorded) drift = drift || "subject digest diverged: " + p;
    }
    if (drift !== null) return { verdict: "RECEIPT_TAMPERED", detail: drift };
    if (unver !== null) return { verdict: "RECEIPT_UNVERIFIABLE", detail: unver };
  }
  return { verdict: "RECEIPT_VALID", detail: "receipt re-derived" };
}

const RECEIPT_USAGE =
  "usage: emet receipt --from-json <file|->   emit a portable witness receipt\n" +
  "       emet check <receipt.json> [--recompute-from-paths]   offline re-verify\n";

// receipt --from-json <file|-> : read a command envelope (verify/anchor/coherence/
// corroborate --json), print a self-contained content-addressed receipt to stdout.
function cmdReceipt(args) {
  if (args.length >= 2 && args[0] === "--from-json") {
    const src = args[1];
    let raw;
    try {
      raw = src === "-" ? fs.readFileSync(0, "utf8") : fs.readFileSync(src, "utf8");
    } catch (_e) {
      process.stderr.write("emet receipt: cannot read --from-json source (OSError)\n");
      return EXIT_USAGE;
    }
    let env;
    try {
      env = JSON.parse(raw);
    } catch (_e) {
      process.stderr.write("emet receipt: cannot read --from-json source (ValueError)\n");
      return EXIT_USAGE;
    }
    if (typeof env !== "object" || env === null || Array.isArray(env)) {
      process.stderr.write("emet receipt: cannot read --from-json source (ValueError)\n");
      return EXIT_USAGE;
    }
    // issued_at is the one wall-clock field; an injected env value keeps receipts
    // deterministic under test (parity with the Rust EMET_RECEIPT_NOW seam).
    const now = process.env.EMET_RECEIPT_NOW || new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
    const key = resolveKey(null);
    const receipt = emitReceipt(env, process.cwd(), now, key);
    process.stdout.write(canonicalJson(receipt) + "\n");
    return EXIT_OK;
  }
  process.stderr.write(RECEIPT_USAGE);
  return EXIT_USAGE;
}

// check <receipt.json> [--recompute-from-paths] : stateless offline re-verify.
// RECEIPT_VALID->0, RECEIPT_TAMPERED->1, RECEIPT_UNVERIFIABLE->2.
function cmdCheck(args) {
  const recompute = args.includes("--recompute-from-paths");
  const positional = args.filter((a) => !a.startsWith("-"));
  if (positional.length === 0) {
    process.stderr.write(RECEIPT_USAGE);
    return EXIT_USAGE;
  }
  const p = positional[0];
  let receipt;
  try {
    receipt = loadReceipt(p);
  } catch (e) {
    say(`RECEIPT_UNVERIFIABLE ${p} reason=${e.message}`);
    return emit("check", "RECEIPT_UNVERIFIABLE", EXIT_FAIL, { subject: p, reason: e.message });
  }
  // Subjects are recorded relative to the producer cwd; re-derive relative to the
  // receipt file's directory so a portable receipt+subject pair checks in place.
  const base = path.dirname(path.resolve(p)) || ".";
  const { verdict, detail } = checkReceipt(receipt, base, recompute, null);
  say(`result=${verdict} reason=${detail}`);
  const code = verdict === "RECEIPT_VALID" ? EXIT_OK : verdict === "RECEIPT_TAMPERED" ? EXIT_DIFFER : EXIT_FAIL;
  return emit("check", verdict, code, { subject: p, detail, receipt_id: receipt.receipt_id });
}

// ---------------------------------------------------------------------------
// Dispatch
// ---------------------------------------------------------------------------
function main(argv) {
  // Global --json flag (SPEC s.13): accepted before OR after the subcommand.
  // Strip every occurrence from argv and enable JSON envelope mode.
  const filtered = argv.filter((a) => a !== "--json");
  if (filtered.length !== argv.length) JSON_MODE = true;
  const [cmd, ...rest] = filtered;
  switch (cmd) {
    case "anchor":
      return cmdAnchor(rest);
    case "verify":
      return cmdVerify(rest);
    case "coherence":
      return cmdCoherence(rest);
    case "refuse":
      return cmdRefuse(rest);
    case "corroborate":
      return cmdCorroborate(rest);
    case "audit":
      return cmdAudit(rest);
    case "selftest":
      return cmdSelftest(rest);
    case "receipt":
      return cmdReceipt(rest);
    case "check":
      return cmdCheck(rest);
    default:
      process.stderr.write(
        "usage: emet <anchor|verify|coherence|refuse|corroborate|audit|selftest|receipt|check> [args...]\n"
      );
      return EXIT_USAGE;
  }
}

// Run as a CLI only when invoked directly (node emet.js ...); when required by a
// test module, export the receipt seam instead of exiting so the behavior can be
// exercised in-process (SPEC s.17). The conformance runner always invokes this
// file directly, so the CLI path is unchanged.
if (require.main === module) {
  process.exit(main(process.argv.slice(2)));
} else {
  module.exports = {
    emitReceipt,
    checkReceipt,
    receiptIdHash,
    signReceipt,
    subjectsFromEnvelope,
    verdictRecords,
    canonicalJson,
    sha256Hex,
    RECEIPT_FORMAT,
  };
}
