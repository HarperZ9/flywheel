import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, existsSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { main } from "../src/cli.mjs";

const FAKE = fileURLToPath(new URL("./fixtures/fake-telos.mjs", import.meta.url));

function tmp() { return mkdtempSync(join(tmpdir(), "learn-viz-")); }

test("learn visualize writes a witnessed aid receipt when the engine is available", async () => {
  const dir = tmp();
  const conceptPath = join(dir, "concept.json");
  writeFileSync(conceptPath, JSON.stringify({ title: "y = sin(x)", kind: "math.function-plot" }));
  const out = join(dir, "runs");
  mkdirSync(out, { recursive: true });

  process.env.LEARN_TELOS_CMD = "node " + FAKE;
  try {
    const r = await main(["visualize", conceptPath, "--out", out], { dir });
    assert.equal(r.code, 0);
    assert.match(r.out, /MATCH/);
    assert.match(r.out, /aid/i);
  } finally { delete process.env.LEARN_TELOS_CMD; }

  const receipt = JSON.parse(readFileSync(join(out, "scene-request.json"), "utf8"));
  assert.equal(receipt.schema, "learn.telos.scene-request/v1");

  // an aid receipt file exists and is witnessed
  const aidPath = join(out, "y-sin-x.aid.json");
  assert.ok(existsSync(aidPath), "aid receipt written");
  const aid = JSON.parse(readFileSync(aidPath, "utf8"));
  assert.equal(aid.provenance, "aid");
  assert.equal(aid.render.verdict, "MATCH");
  assert.equal(aid.verified, true);
});

test("learn visualize fails closed (no engine) but still returns cleanly", async () => {
  const dir = tmp();
  const conceptPath = join(dir, "concept.json");
  writeFileSync(conceptPath, JSON.stringify({ title: "y = x^2" }));
  const out = join(dir, "runs");
  mkdirSync(out, { recursive: true });

  delete process.env.LEARN_TELOS_CMD;
  const r = await main(["visualize", conceptPath, "--out", out], { dir });
  assert.equal(r.code, 0);
  assert.match(r.out, /UNVERIFIABLE|engine-unavailable/);
  const aid = JSON.parse(readFileSync(join(out, "y-x-2.aid.json"), "utf8"));
  assert.equal(aid.render.verdict, "UNVERIFIABLE");
  assert.equal(aid.provenance, "aid");
});
