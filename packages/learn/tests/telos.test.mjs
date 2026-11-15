import { test } from "node:test";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { toTelosSceneSpec, telosRender, toAidLedgerEntry } from "../src/interop/telos.mjs";
import { Ledger } from "../src/accountability/ledger.mjs";

test("toTelosSceneSpec builds a math_physics scene request with a deterministic hash", () => {
  const concept = { title: "Damped harmonic oscillator", kind: "physics.ode", params: { omega: 2.0, zeta: 0.1 } };
  const a = toTelosSceneSpec(concept);
  assert.equal(a.schema, "learn.telos.scene-request/v1");
  assert.equal(a.concept.title, "Damped harmonic oscillator");
  assert.equal(a.concept.kind, "physics.ode");
  assert.equal(a.spec.lane, "math_physics");
  assert.deepEqual(a.spec.params, { omega: 2.0, zeta: 0.1 });
  assert.match(a.requestHash, /^sha256:[0-9a-f]{64}$/);
  // deterministic
  const b = toTelosSceneSpec(concept);
  assert.equal(a.requestHash, b.requestHash);
});

test("toTelosSceneSpec defaults kind and tolerates a bare concept", () => {
  const a = toTelosSceneSpec({ title: "y = x^2" });
  assert.equal(a.concept.kind, "math.function-plot");
  assert.deepEqual(a.spec.params, {});
});

const FAKE = fileURLToPath(new URL("./fixtures/fake-telos.mjs", import.meta.url));

test("telosRender fails closed when no command is configured", async () => {
  const r = await telosRender("ignored.json", { cmd: "" });
  assert.equal(r.ran, false);
  assert.equal(r.verdict, "UNVERIFIABLE");
  assert.equal(r.failure, "engine-unavailable");
  assert.equal(r.provenance, "aid");
  assert.match(r.reason, /telos command/i);
});

test("telosRender parses the engine result and tags it aid", async () => {
  const r = await telosRender("ignored.json", { cmd: "node " + FAKE });
  assert.equal(r.ran, true);
  assert.equal(r.provenance, "aid");
  assert.equal(r.verdict, "MATCH");
  assert.equal(r.selected_profile, "canvas2d-receipt-renderer");
  assert.equal(r.result_hash, "sha256:" + "b".repeat(64));
  assert.ok(Array.isArray(r.fallback_chain) && r.fallback_chain.length === 3);
});

test("telosRender returns UNVERIFIABLE (never throws) on non-JSON engine output", async () => {
  // `node -e "..."` prints non-JSON; telosRender must degrade, not crash.
  const r = await telosRender("ignored.json", { cmd: 'node -e process.stdout.write("not-json")' });
  assert.equal(r.provenance, "aid");
  assert.equal(r.verdict, "UNVERIFIABLE");
  assert.equal(r.failure, "bad-render-output");
});

test("toAidLedgerEntry produces an aid-visualization entry usable in a hash-chained ledger", async () => {
  const render = await telosRender("ignored.json", { cmd: "node " + FAKE });
  const entry = toAidLedgerEntry(render, { concept: { title: "y = sin(x)" }, seq: 7 });
  assert.equal(entry.kind, "aid-visualization");
  assert.equal(entry.provenance, "aid");
  assert.equal(entry.seq, 7);
  assert.equal(entry.concept, "y = sin(x)");
  assert.equal(entry.result_hash, "sha256:" + "b".repeat(64));
  assert.equal(entry.verdict, "MATCH");

  const l = new Ledger();
  l.append(entry);
  assert.equal(l.verify().ok, true);
  assert.equal(l.entries()[0].entry.kind, "aid-visualization");
});
