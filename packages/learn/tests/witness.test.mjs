import { test } from "node:test";
import assert from "node:assert/strict";
import { sha256hex, observe } from "../src/accountability/witness.mjs";

test("sha256hex is deterministic and 64 hex chars", () => {
  const a = sha256hex("hello");
  assert.equal(a, sha256hex("hello"));
  assert.match(a, /^[0-9a-f]{64}$/);
});

test("observe derives the digest from the payload bytes", () => {
  const obs = observe({ organ: "fs", subject: "file://x", summary: "x", payload: "content", data: { size: 7 } });
  assert.equal(obs.digest, "sha256:" + sha256hex("content"));
  assert.equal(obs.data.size, 7);
});

test("any payload change changes the digest", () => {
  const a = observe({ organ: "o", subject: "s", summary: "", payload: "a" });
  const b = observe({ organ: "o", subject: "s", summary: "", payload: "a!" });
  assert.notEqual(a.digest, b.digest);
});
