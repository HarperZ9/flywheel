"use strict";
// A second, INDEPENDENT implementation of the coherence-membrane read-gate's
// inert compute -- the part the conformance corpus pins. If this re-derives the
// same frozen values as the Python reference from conformance/vectors.json, then
// the observation/drift contract is re-derivable rather than asserted: a witness
// two independent implementations agree on is a proof, not a claim.
//
// Node built-ins only (crypto, zlib) -- no npm, nothing third-party in the path,
// mirroring the Python "stdlib-only trust path" discipline. 64-bit hashes are
// carried as BigInt because a JS Number is only 53-bit-safe.
//
// Faithful ports of: observation.sha256_hex, pngview.decode_png, phash
// (_to_grayscale/_downscale/_dhash_bits/perceptual_hash/hamming/compare_drift),
// organs.structured.canonical_json_bytes, region.compare_region_drift, and
// receipt.WitnessReceipt.anchor.

const crypto = require("crypto");
const zlib = require("zlib");

// --- identity --------------------------------------------------------------

function sha256Hex(buf) {
  return crypto.createHash("sha256").update(buf).digest("hex");
}

// --- minimal PNG decode (mirrors pngview.py) -------------------------------

const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const CHANNELS = { 0: 1, 2: 3, 4: 2, 6: 4 };

function isPng(buf) {
  return buf.length >= 8 && buf.subarray(0, 8).equals(PNG_SIG);
}

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  if (pb <= pc) return b;
  return c;
}

function defilter(raw, width, height, channels) {
  const stride = width * channels;
  const bpp = channels; // 8-bit: bytes-per-pixel == channels
  if (raw.length < (stride + 1) * height) throw new Error("decompressed data shorter than expected");
  const out = Buffer.alloc(stride * height);
  let prev = Buffer.alloc(stride);
  let pos = 0;
  for (let row = 0; row < height; row++) {
    const ftype = raw[pos]; pos += 1;
    const line = Buffer.from(raw.subarray(pos, pos + stride)); pos += stride;
    if (ftype === 0) { /* None */
    } else if (ftype === 1) { // Sub
      for (let i = 0; i < stride; i++) { const left = i >= bpp ? line[i - bpp] : 0; line[i] = (line[i] + left) & 0xff; }
    } else if (ftype === 2) { // Up
      for (let i = 0; i < stride; i++) line[i] = (line[i] + prev[i]) & 0xff;
    } else if (ftype === 3) { // Average
      for (let i = 0; i < stride; i++) { const left = i >= bpp ? line[i - bpp] : 0; line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xff; }
    } else if (ftype === 4) { // Paeth
      for (let i = 0; i < stride; i++) { const left = i >= bpp ? line[i - bpp] : 0; const upLeft = i >= bpp ? prev[i - bpp] : 0; line[i] = (line[i] + paeth(left, prev[i], upLeft)) & 0xff; }
    } else {
      throw new Error("unknown filter type " + ftype);
    }
    line.copy(out, row * stride);
    prev = line;
  }
  return out;
}

function decodePng(buf) {
  if (!isPng(buf)) throw new Error("not a PNG (bad signature)");
  let width = -1, height = -1, bitDepth = -1, colorType = -1, interlace = -1;
  const idat = [];
  let sawIhdr = false, sawIend = false;
  let offset = 8;
  const n = buf.length;
  while (offset + 8 <= n) {
    const length = buf.readUInt32BE(offset);
    const ctype = buf.toString("latin1", offset + 4, offset + 8);
    const start = offset + 8;
    const end = start + length;
    if (end + 4 > n) throw new Error("truncated chunk");
    const data = buf.subarray(start, end);
    if (ctype === "IHDR") {
      if (length !== 13) throw new Error("bad IHDR length");
      width = data.readUInt32BE(0); height = data.readUInt32BE(4);
      bitDepth = data[8]; colorType = data[9]; interlace = data[12];
      sawIhdr = true;
    } else if (ctype === "IDAT") {
      idat.push(Buffer.from(data));
    } else if (ctype === "IEND") {
      sawIend = true; break;
    }
    offset = end + 4; // skip the 4-byte CRC
  }
  if (!sawIhdr) throw new Error("missing IHDR");
  if (!sawIend) throw new Error("missing IEND");
  if (bitDepth !== 8) throw new Error("unsupported bit depth " + bitDepth);
  if (interlace !== 0) throw new Error("interlaced PNG not supported");
  if (!(colorType in CHANNELS)) throw new Error("unsupported colour type " + colorType);
  if (width <= 0 || height <= 0) throw new Error("non-positive dimensions");
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const channels = CHANNELS[colorType];
  const pixels = defilter(raw, width, height, channels);
  return { width, height, channels, colorType, pixels };
}

// --- perceptual hash (mirrors phash.py) ------------------------------------

const HASH_W = 8, HASH_H = 8;

function toGrayscale(img) {
  const px = img.pixels, ch = img.channels, n = img.width * img.height;
  const gray = new Array(n);
  if (ch === 1) { for (let i = 0; i < n; i++) gray[i] = px[i]; }
  else if (ch === 2) { for (let i = 0; i < n; i++) gray[i] = px[i * 2]; }
  else { for (let i = 0; i < n; i++) { const b = i * ch; gray[i] = Math.floor((px[b] * 299 + px[b + 1] * 587 + px[b + 2] * 114) / 1000); } }
  return gray;
}

function downscale(gray, w, h, tw, th) {
  const out = new Array(tw * th);
  for (let ty = 0; ty < th; ty++) {
    const y0 = Math.floor((ty * h) / th);
    const y1 = Math.max(y0 + 1, Math.floor(((ty + 1) * h) / th));
    for (let tx = 0; tx < tw; tx++) {
      const x0 = Math.floor((tx * w) / tw);
      const x1 = Math.max(x0 + 1, Math.floor(((tx + 1) * w) / tw));
      let total = 0, count = 0;
      for (let yy = y0; yy < y1; yy++) { const row = yy * w; for (let xx = x0; xx < x1; xx++) { total += gray[row + xx]; count++; } }
      out[ty * tw + tx] = count ? Math.floor(total / count) : 0;
    }
  }
  return out;
}

function dhashBits(gray, w, h) {
  const small = downscale(gray, w, h, HASH_W + 1, HASH_H);
  let bits = 0n;
  for (let y = 0; y < HASH_H; y++) {
    const row = y * (HASH_W + 1);
    for (let x = 0; x < HASH_W; x++) { bits <<= 1n; if (small[row + x] > small[row + x + 1]) bits |= 1n; }
  }
  return bits;
}

function perceptualHash(img) { return dhashBits(toGrayscale(img), img.width, img.height); }
function phashHex(img) { return perceptualHash(img).toString(16).padStart(16, "0"); }

function hamming(a, b) {
  let x = BigInt(a) ^ BigInt(b);
  let count = 0;
  while (x > 0n) { count += Number(x & 1n); x >>= 1n; }
  return count;
}

// --- drift lattice (mirrors phash.compare_drift) ---------------------------

function compareDrift(baselineSha, currentSha, baselinePhash, currentPhash) {
  if (!baselineSha || !currentSha) return { verdict: "UNVERIFIABLE", distance: null };
  if (baselineSha === currentSha) return { verdict: "MATCH", distance: 0 };
  if (baselinePhash == null || currentPhash == null) return { verdict: "UNVERIFIABLE", distance: null };
  return { verdict: "DRIFT", distance: hamming(baselinePhash, currentPhash) };
}

// --- canonical JSON (mirrors organs.structured.canonical_json_bytes) -------
// Sorted keys, compact separators, ensure_ascii. Byte-identical to Python's
// json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True,
// allow_nan=False) for strings, bools, null, arrays, objects, and SAFE INTEGERS
// (|n| <= 2**53 - 1).
//
// Number fidelity boundary (honest): JS cannot match Python's float repr, and a
// JSON float literal like 1.0 parses to the integer 1 in JS (Python keeps 1.0).
// Rather than silently diverge, canonical() THROWS on any non-safe-integer
// number -- floats and integers beyond 2**53 are out of the JS core's contract.
// (The conformance corpus uses only safe integers, so this never fires there.)

function encodeString(s) {
  let out = '"';
  for (const chStr of s) {
    const c = chStr.codePointAt(0);
    if (chStr === '"') out += '\\"';
    else if (chStr === "\\") out += "\\\\";
    else if (c === 0x08) out += "\\b";
    else if (c === 0x09) out += "\\t";
    else if (c === 0x0a) out += "\\n";
    else if (c === 0x0c) out += "\\f";
    else if (c === 0x0d) out += "\\r";
    else if (c < 0x20) out += "\\u" + c.toString(16).padStart(4, "0");
    else if (c >= 0x20 && c <= 0x7e) out += chStr;
    else if (c > 0xffff) {
      const cc = c - 0x10000;
      const hi = 0xd800 + (cc >> 10), lo = 0xdc00 + (cc & 0x3ff);
      out += "\\u" + hi.toString(16).padStart(4, "0") + "\\u" + lo.toString(16).padStart(4, "0");
    } else out += "\\u" + c.toString(16).padStart(4, "0");
  }
  return out + '"';
}

function canonical(obj) {
  if (obj === null) return "null";
  const t = typeof obj;
  if (t === "boolean") return obj ? "true" : "false";
  if (t === "number") {
    if (!Number.isFinite(obj)) throw new Error("non-finite number not allowed (allow_nan=False)");
    if (!Number.isSafeInteger(obj)) {
      throw new Error("canonical JSON supports only safe integers; floats and "
        + "integers beyond 2**53 are out of contract (would diverge from Python json)");
    }
    return String(obj);
  }
  if (t === "string") return encodeString(obj);
  if (Array.isArray(obj)) return "[" + obj.map(canonical).join(",") + "]";
  if (t === "object") {
    const keys = Object.keys(obj).sort();
    return "{" + keys.map((k) => encodeString(k) + ":" + canonical(obj[k])).join(",") + "}";
  }
  throw new Error("unserializable type: " + t);
}

function canonicalJsonBytes(obj) { return Buffer.from(canonical(obj), "ascii"); }
function canonicalSha256(obj) { return sha256Hex(canonicalJsonBytes(obj)); }

// --- region drift (mirrors region.compare_region_drift) --------------------

function compareRegionDrift(baseline, current, rows, cols, threshold = 0) {
  const n = rows * cols;
  // Mirror Python's falsy-list guard ([] is falsy in Python) and size check.
  if (!baseline || !current || baseline.length === 0 || current.length === 0
      || baseline.length !== n || current.length !== n) {
    return { verdict: "UNVERIFIABLE", changed_regions: [], max_distance: null };
  }
  let distances;
  try {
    distances = baseline.map((b, i) => hamming(BigInt("0x" + b), BigInt("0x" + current[i])));
  } catch (e) {
    // a non-hex / empty tile hash -> fail closed (mirrors Python's except branch)
    return { verdict: "UNVERIFIABLE", changed_regions: [], max_distance: null };
  }
  const changed = [];
  for (let i = 0; i < distances.length; i++) if (distances[i] > threshold) changed.push(i);
  // reduce (not Math.max spread): empty-safe and no stack limit on large grids.
  const maxd = distances.reduce((m, d) => (d > m ? d : m), 0);
  return changed.length
    ? { verdict: "DRIFT", changed_regions: changed, max_distance: maxd }
    : { verdict: "MATCH", changed_regions: [], max_distance: maxd };
}

// --- receipt anchor (mirrors receipt.WitnessReceipt.anchor) ----------------

// Python WitnessReceipt.from_dict str()-coerces the 6 scalar fields and defaults
// facts to {} ONLY when the key is ABSENT (dict.get semantics -- a present
// facts:null stays null). We mirror that: String() the scalars (matching Python
// str() for the string/integer values the real Provenance path produces) and
// default facts only on absence. Exotic scalar types (bool/null/float) do not
// occur in the real path and are not guaranteed byte-identical to Python str().
function receiptAnchor(receipt) {
  const r = receipt || {};
  const facts = ("facts" in r) ? r.facts : {};  // default only when absent (dict.get)
  const body = {
    receipt_version: String(r.receipt_version),
    organ: String(r.organ),
    subject: String(r.subject),
    digest: String(r.digest),
    timestamp: String(r.timestamp),
    confidence: String(r.confidence),
    facts: facts,
  };
  return canonicalSha256(body);
}

module.exports = {
  sha256Hex, isPng, decodePng, toGrayscale, dhashBits, perceptualHash, phashHex,
  hamming, compareDrift, canonical, canonicalJsonBytes, canonicalSha256,
  compareRegionDrift, receiptAnchor,
};
