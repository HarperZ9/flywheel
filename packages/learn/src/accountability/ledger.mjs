import { sha256hex } from "./witness.mjs";

const GENESIS = "0".repeat(64);
const hashOf = (prevHash, entry) => sha256hex(prevHash + JSON.stringify(entry));

export class Ledger {
  constructor() { this._rows = []; }
  append(entry) {
    const prevHash = this._rows.length ? this._rows[this._rows.length - 1].hash : GENESIS;
    const seq = this._rows.length;
    const hash = hashOf(prevHash, entry);
    const row = { seq, prevHash, hash, entry };
    this._rows.push(row);
    return { seq, hash, prevHash };
  }
  entries() { return this._rows; }
  verify() {
    let prev = GENESIS;
    for (let i = 0; i < this._rows.length; i++) {
      const r = this._rows[i];
      if (r.prevHash !== prev) return { ok: false, brokenAt: i };
      if (r.hash !== hashOf(r.prevHash, r.entry)) return { ok: false, brokenAt: i };
      prev = r.hash;
    }
    return { ok: true, brokenAt: null };
  }
  static fromEntries(rows) {
    const l = new Ledger();
    l._rows = rows.map((r) => ({ seq: r.seq, prevHash: r.prevHash, hash: r.hash, entry: r.entry }));
    return l;
  }
}
