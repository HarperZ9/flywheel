import { test } from "node:test";
import assert from "node:assert/strict";
import { Ledger } from "../src/accountability/ledger.mjs";

test("append chains hashes and verifies", () => {
  const l = new Ledger();
  l.append({ kind: "step", n: 1 });
  l.append({ kind: "step", n: 2 });
  const v = l.verify();
  assert.equal(v.ok, true);
  assert.equal(l.entries().length, 2);
  assert.equal(l.entries()[1].prevHash, l.entries()[0].hash);
});

test("tampering with a recorded entry is detected", () => {
  const l = new Ledger();
  l.append({ kind: "step", n: 1 });
  l.append({ kind: "step", n: 2 });
  l.entries()[0].entry.n = 999;
  const v = l.verify();
  assert.equal(v.ok, false);
  assert.equal(v.brokenAt, 0);
});

test("fromEntries replays and flags a broken chain", () => {
  const l = new Ledger();
  l.append({ a: 1 });
  const raw = JSON.parse(JSON.stringify(l.entries()));
  raw[0].hash = "deadbeef";
  const replayed = Ledger.fromEntries(raw);
  assert.equal(replayed.verify().ok, false);
});
