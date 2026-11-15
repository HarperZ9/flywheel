import { test } from "node:test";
import assert from "node:assert/strict";
import { TOOLS, dispatch, handle } from "../src/mcp.mjs";

test("learn_visualize_dry_run is registered as an advisory tool", () => {
  const t = TOOLS.find((x) => x.name === "learn_visualize_dry_run");
  assert.ok(t, "tool present");
  assert.match(t.description, /scene-spec|render/i);
});

test("learn_visualize_dry_run returns the scene-spec request and renders nothing", async () => {
  const out = await dispatch("learn_visualize_dry_run", { concept: { title: "y = x^2", kind: "math.function-plot" } });
  assert.equal(out.schema, "learn.telos.scene-request/v1");
  assert.equal(out.concept.title, "y = x^2");
  assert.match(out.requestHash, /^sha256:/);
  // advisory: no render fields (no verdict/result_hash) — it did not actuate
  assert.equal(out.verdict, undefined);
  assert.equal(out.result_hash, undefined);
});

test("tools/call routes learn_visualize_dry_run", async () => {
  const res = await handle({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "learn_visualize_dry_run", arguments: { concept: { title: "t" } } } });
  assert.ok(res.result.content[0].text.includes("scene-request"));
});
