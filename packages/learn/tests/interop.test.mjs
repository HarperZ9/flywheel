import { test } from "node:test";
import assert from "node:assert/strict";
import { assist, assistArtifacts } from "../src/assist/assist.mjs";
import { toCrucibleThesis, crucibleAssess } from "../src/interop/crucible.mjs";
import { toGatherManifest, gatherRun } from "../src/interop/gather.mjs";

const DRAFT = "My engine reduces loop memory 265x. Evidence at https://github.com/HarperZ9/buildlang and https://pypi.org/project/index-graph.";

test("toCrucibleThesis produces a valid crucible thesis from assisted claims", () => {
  const a = assist(DRAFT);
  const thesis = toCrucibleThesis(a, { title: "T" });
  assert.equal(thesis.title, "T");
  assert.equal(thesis.disposition, "publishable");
  assert.ok(Array.isArray(thesis.claims));
  assert.ok(thesis.claims.every((c) => typeof c.text === "string" && "falsification" in c));
  assert.ok(thesis.claims.some((c) => /265x/.test(c.text)));
});

test("toGatherManifest dedupes and lists the operator's cited sources", () => {
  const a = assist(DRAFT);
  const m = toGatherManifest(a);
  assert.ok(m.sources.includes("https://github.com/HarperZ9/buildlang"));
  assert.ok(m.sources.includes("https://pypi.org/project/index-graph"));
  assert.equal(m.sources.length, new Set(m.sources).size);
});

test("assistArtifacts bundles assist + crucible thesis + gather manifest", () => {
  const art = assistArtifacts(DRAFT);
  assert.ok(art.assist && art.crucibleThesis && art.gatherManifest);
  assert.equal(art.crucibleThesis.claims.length, art.assist.claims.length);
});

test("interop shell-outs fail closed with a clear reason when no command is configured", async () => {
  const c = await crucibleAssess("nope.json", { cmd: "" });
  assert.equal(c.ran, false);
  assert.match(c.reason, /crucible command/i);
  const g = await gatherRun(["https://x"], { cmd: "" });
  assert.equal(g.ran, false);
  assert.match(g.reason, /gather command/i);
});
