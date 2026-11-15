// Clean-room RECEIPT v1.0 checker, JavaScript with BigInt arithmetic.
// Written from WITNESS_FORMAT.md only. Shares no code with core.py or with
// the Python checker in src/second_checker (it is a separate reading of the spec).
//
//   node js/check.mjs SYSTEM.jsonl WITNESS.json [WITNESS.json ...]
//
// Prints one JSON line per witness: {"witness", "verdict", "reason"} and exits
// 0 (all PASS), 1 (any FAIL) or 2 (any MALFORMED or no witnesses).
import { readFileSync } from "node:fs";
import { basename } from "node:path";

class Malformed extends Error {}

const INT_RE = /^\s*-?\d+\s*$/;
function toBig(x, what) {
  if (typeof x === "number" && Number.isInteger(x)) return BigInt(x);
  if (typeof x === "string" && INT_RE.test(x)) return BigInt(x.trim());
  throw new Malformed(`${what}: not an integer`);
}
const mod = (a, p) => ((a % p) + p) % p;

function sparse(obj, p, what) {
  if (obj === null || typeof obj !== "object" || Array.isArray(obj)) throw new Malformed(`${what}: not an object`);
  const out = new Map();
  for (const [k, v] of Object.entries(obj)) {
    const col = toBig(k, `${what} key`).toString();
    const val = mod(toBig(v, `${what} value`), p);
    if (val !== 0n) out.set(col, val);
  }
  return out;
}

function parseWitness(o) {
  if (typeof o.receipt_version !== "string" || o.receipt_version.split(".")[0] !== "1")
    throw new Malformed("unsupported or missing receipt_version");
  for (const k of ["p", "target", "c", "lam"]) if (!(k in o)) throw new Malformed(`missing ${k}`);
  const p = toBig(o.p, "p");
  if (p <= 1n) throw new Malformed("p must be > 1");
  if (!o.target || !("col" in o.target)) throw new Malformed("target.col missing");
  const t = toBig(o.target.col, "target.col").toString();
  const c = sparse(o.c, p, "c");
  const L = o.lam;
  if (!L || !Array.isArray(L.idx) || !Array.isArray(L.val) || !("n_rows" in L)) throw new Malformed("lam malformed");
  if (L.idx.length !== L.val.length) throw new Malformed("lam idx/val length mismatch");
  const n = toBig(L.n_rows, "lam.n_rows");
  const lam = new Map();
  L.idx.forEach((ir, j) => {
    const i = toBig(ir, "lam.idx");
    if (i < 0n || i >= n) throw new Malformed("lam.idx out of range");
    if (lam.has(i)) throw new Malformed("duplicate lam.idx");
    lam.set(i, mod(toBig(L.val[j], "lam.val"), p));
  });
  return { p, t, c, lam, n };
}

function check(rawRows, o) {
  const w = parseWitness(o);
  if (BigInt(rawRows.length) !== w.n) return ["FAIL", "lam n_rows mismatch"];
  const acc = new Map();
  for (const [i, li] of w.lam) {
    if (li === 0n) continue;
    for (const [col, v] of sparse(rawRows[Number(i)], w.p, `row ${i}`)) {
      acc.set(col, mod((acc.get(col) ?? 0n) + li * v, w.p));
    }
  }
  const expect = new Map([[w.t, 1n % w.p]]);
  for (const [m, cm] of w.c) expect.set(m, mod((expect.get(m) ?? 0n) - cm, w.p));
  const nz = (M) => new Map([...M].filter(([, v]) => v !== 0n));
  const a = nz(acc), e = nz(expect);
  if (a.size !== e.size) return ["FAIL", "identity failed"];
  for (const [k, v] of e) if (a.get(k) !== v) return ["FAIL", "identity failed"];
  return ["PASS", ""];
}

const [sysPath, ...wits] = process.argv.slice(2);
const rows = readFileSync(sysPath, "utf8").split(/\r?\n/).filter((l) => l.trim()).map((l) => JSON.parse(l));
let rc = wits.length ? 0 : 2;
for (const path of wits) {
  let verdict, reason;
  try {
    [verdict, reason] = check(rows, JSON.parse(readFileSync(path, "utf8")));
  } catch (e) {
    if (!(e instanceof Malformed) && !(e instanceof SyntaxError)) throw e;
    [verdict, reason] = ["MALFORMED", e.message];
  }
  if (verdict === "MALFORMED") rc = 2;
  else if (verdict === "FAIL" && rc === 0) rc = 1;
  console.log(JSON.stringify({ witness: basename(path), verdict, reason }));
}
process.exit(rc);
