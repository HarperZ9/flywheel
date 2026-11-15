import { test } from "node:test";
import assert from "node:assert/strict";
import { assist } from "../src/assist/assist.mjs";
import { addCredential, renderResumeMarkdown } from "../src/resume/resume.mjs";
import { handle, dispatch } from "../src/mcp.mjs";

test("assist flags claims + sources from the operator's OWN draft, authors nothing", () => {
  const draft = "My compiler reduces build time by 40%. See https://github.com/HarperZ9/buildlang for the code.";
  const r = assist(draft);
  assert.ok(r.claims.length >= 1);                       // the 40% claim flagged to verify
  assert.ok(r.sources.includes("https://github.com/HarperZ9/buildlang"));
  assert.match(r.inputSha256, /^[0-9a-f]{64}$/);
  assert.ok(r.checklist.some((c) => /wrote nothing/i.test(c)));
});

test("resume ingests a receipt and marks provenance when graded work was human-performed", () => {
  const receipt = { course: "Intro Security", certId: "cert:x", verified: true, seal: "sha256:z", humanAssessments: [{ seq: 1 }] };
  const resume = addCredential({ name: "Zain" }, receipt);
  assert.equal(resume.credentials.length, 1);
  assert.equal(resume.credentials[0].provenanceVerified, true);
  assert.match(renderResumeMarkdown(resume), /provenance-verified/);
});

test("resume does NOT mark provenance when there was no human assessment", () => {
  const receipt = { course: "c", certId: "y", verified: true, seal: "s", humanAssessments: [] };
  const resume = addCredential({}, receipt);
  assert.equal(resume.credentials[0].provenanceVerified, false);
});

test("MCP handler: initialize, tools/list, and tools/call(learn_doctor)", async () => {
  const init = await handle({ jsonrpc: "2.0", id: 1, method: "initialize" });
  assert.equal(init.result.serverInfo.name, "learn");
  const list = await handle({ jsonrpc: "2.0", id: 2, method: "tools/list" });
  assert.ok(list.result.tools.some((t) => t.name === "learn_doctor"));
  const call = await handle({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "learn_doctor", arguments: {} } });
  assert.match(call.result.content[0].text, /MATCH/);
});

test("MCP dispatch: status returns invariants", async () => {
  const s = await dispatch("learn_status", {});
  assert.ok(s.integrityInvariants.length >= 4);
});
