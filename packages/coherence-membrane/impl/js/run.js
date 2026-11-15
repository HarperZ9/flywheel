"use strict";
// Cross-implementation conformance harness (the JS side).
//
// Loads the SAME frozen corpus the Python reference pins (conformance/vectors.json)
// and re-derives every case through this independent JS implementation. If all
// cases match the expected values, re-derivability is demonstrated for the
// contract corpus -- two implementations that share no code agree, value-for-value,
// on every case in it. (The corpus is the contract; see membrane.js for the
// number-fidelity boundary that keeps the two impls honest beyond it.)
//
//     node impl/js/run.js     # exit 0 if all pass, 1 on any mismatch
//
// Node built-ins only.

const fs = require("fs");
const path = require("path");
const M = require("./membrane.js");

const VECTORS = path.resolve(__dirname, "..", "..", "conformance", "vectors.json");

function bytesIn(inp) {
  if ("utf8" in inp) return Buffer.from(inp.utf8, "utf8");
  if ("hex" in inp) return Buffer.from(inp.hex, "hex");
  throw new Error("case input has no 'utf8' or 'hex' byte source");
}

function optBig(v) {
  return (v === null || v === undefined || v === "") ? null : BigInt("0x" + v);
}

function runCase(c) {
  const fn = c.fn, inp = c.input;
  switch (fn) {
    case "sha256_hex":
      return M.sha256Hex(bytesIn(inp));
    case "hamming":
      return M.hamming(BigInt("0x" + inp.a), BigInt("0x" + inp.b));
    case "perceptual_hash":
      return M.phashHex(M.decodePng(Buffer.from(inp.png_hex, "hex")));
    case "compare_drift": {
      const v = M.compareDrift(inp.baseline_sha256, inp.current_sha256, optBig(inp.baseline_phash), optBig(inp.current_phash));
      return { verdict: v.verdict, distance: v.distance };
    }
    case "canonical_sha256":
      return M.canonicalSha256(inp.json);
    case "region_drift": {
      const r = M.compareRegionDrift(inp.baseline, inp.current, inp.rows, inp.cols, inp.threshold || 0);
      return { verdict: r.verdict, changed_regions: r.changed_regions, max_distance: r.max_distance };
    }
    case "receipt_anchor":
      return M.receiptAnchor(inp.receipt);
    default:
      throw new Error("unknown conformance fn: " + fn);
  }
}

function deepEqual(a, b) {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== "object" || typeof b !== "object") return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const ka = Object.keys(a), kb = Object.keys(b);
  if (ka.length !== kb.length) return false;
  for (const k of ka) { if (!Object.prototype.hasOwnProperty.call(b, k)) return false; if (!deepEqual(a[k], b[k])) return false; }
  return true;
}

function main() {
  const vectors = JSON.parse(fs.readFileSync(VECTORS, "utf8"));
  const cases = vectors.cases;
  const failures = [];
  for (const c of cases) {
    let got;
    try { got = runCase(c); }
    catch (e) { failures.push([c.id, c.expected, "ERROR: " + e.message]); continue; }
    if (!deepEqual(got, c.expected)) failures.push([c.id, c.expected, got]);
  }
  for (const [id, exp, got] of failures) {
    process.stderr.write("FAIL " + id + ": expected " + JSON.stringify(exp) + " got " + JSON.stringify(got) + "\n");
  }
  process.stdout.write(JSON.stringify({ impl: "js", cases: cases.length, passed: cases.length - failures.length, failed: failures.length }) + "\n");
  return failures.length ? 1 : 0;
}

if (require.main === module) process.exit(main());
module.exports = { runCase, deepEqual };
